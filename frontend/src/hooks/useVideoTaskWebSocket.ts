/**
 * WebSocket hook for real-time video inference preview.
 *
 * Connects to the backend WS endpoint during inference, accumulates
 * per-frame detection results, and tracks HLS segment readiness so
 * the UI can render a live preview player.
 */

import { useEffect, useRef, useState, useCallback } from 'react';
import { modelService } from '../services';
import type {
  VideoTaskProgress,
  VideoTaskResult,
  FrameDetectionResult,
} from '../services';

interface UseVideoTaskWebSocketReturn {
  /** Incrementally built result (partial frame_results) */
  partialResult: VideoTaskResult | null;
  /** HLS playlist URL from the WS connected message (MinIO VOD) */
  hlsUrl: string | null;
  /** SRS live HLS URL (available only during processing) */
  srsHlsUrl: string | null;
  /** Original HLS URL (available after task_completed) */
  originalHlsUrl: string | null;
  /** True once the first HLS segment has been confirmed */
  hlsReady: boolean;
  /** WebSocket is currently open */
  wsConnected: boolean;
}

const ACTIVE_STATUSES = new Set(['processing', 'rendering']);
const MAX_RETRIES = 3;
const FLUSH_DEBOUNCE_MS = 300;

export function useVideoTaskWebSocket(
  modelId: string | undefined,
  taskId: string | null,
  videoProgress: VideoTaskProgress | null,
): UseVideoTaskWebSocketReturn {
  const [partialResult, setPartialResult] = useState<VideoTaskResult | null>(null);
  const [hlsUrl, setHlsUrl] = useState<string | null>(null);
  const [srsHlsUrl, setSrsHlsUrl] = useState<string | null>(null);
  const [originalHlsUrl, setOriginalHlsUrl] = useState<string | null>(null);
  const [hlsReady, setHlsReady] = useState(false);
  const [wsConnected, setWsConnected] = useState(false);

  // Refs for mutable state that doesn't need re-renders
  const wsRef = useRef<WebSocket | null>(null);
  const frameMapRef = useRef<Map<number, FrameDetectionResult>>(new Map());
  const flushTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const retryCountRef = useRef(0);
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const progressRef = useRef(videoProgress);
  // Track if we intentionally closed (to prevent reconnects)
  const intentionalCloseRef = useRef(false);

  // Keep progressRef in sync without triggering effect re-runs
  useEffect(() => {
    progressRef.current = videoProgress;
  }, [videoProgress]);

  /** Convert the accumulated frame map into a VideoTaskResult */
  const flushPartialResult = useCallback(() => {
    const prog = progressRef.current;
    if (!prog) return;

    const map = frameMapRef.current;
    const totalFrames = prog.total_frames || 0;
    const fps = prog.fps || 30;
    const duration = prog.duration_seconds || 0;

    // Build a dense array — fill gaps with empty detections
    const maxIndex = totalFrames > 0
      ? totalFrames
      : map.size > 0
        ? Math.max(...map.keys()) + 1
        : 0;

    const frameResults: FrameDetectionResult[] = new Array(maxIndex);
    for (let i = 0; i < maxIndex; i++) {
      const existing = map.get(i);
      if (existing) {
        frameResults[i] = existing;
      } else {
        frameResults[i] = {
          frame_index: i,
          timestamp_ms: (i / fps) * 1000,
          boxes: [],
          scores: [],
          labels: [],
          class_names: [],
        };
      }
    }

    setPartialResult({
      task_id: prog.task_id,
      model_id: prog.model_id,
      total_frames: totalFrames,
      fps,
      duration_seconds: duration,
      class_colors: null,
      video_info: {},
      frame_results: frameResults,
    });
  }, []);

  /** Schedule a debounced flush */
  const scheduleFlush = useCallback(() => {
    if (flushTimerRef.current) clearTimeout(flushTimerRef.current);
    flushTimerRef.current = setTimeout(flushPartialResult, FLUSH_DEBOUNCE_MS);
  }, [flushPartialResult]);

  /** Clean up WebSocket and timers */
  const cleanup = useCallback(() => {
    intentionalCloseRef.current = true;
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    if (flushTimerRef.current) {
      clearTimeout(flushTimerRef.current);
      flushTimerRef.current = null;
    }
    if (retryTimerRef.current) {
      clearTimeout(retryTimerRef.current);
      retryTimerRef.current = null;
    }
    setWsConnected(false);
  }, []);

  /** Connect to the WebSocket */
  const connect = useCallback(() => {
    if (!modelId || !taskId) return;
    if (wsRef.current && wsRef.current.readyState <= WebSocket.OPEN) return;

    intentionalCloseRef.current = false;

    let ws: WebSocket;
    try {
      ws = modelService.createVideoTaskWebSocket(modelId, taskId);
    } catch {
      return;
    }
    wsRef.current = ws;

    ws.onopen = () => {
      setWsConnected(true);
      retryCountRef.current = 0;
    };

    ws.onmessage = (event) => {
      let data: Record<string, unknown>;
      try {
        data = JSON.parse(event.data);
      } catch {
        return;
      }

      const type = data.type as string;

      switch (type) {
        case 'connected':
          if (data.hls_url) setHlsUrl(data.hls_url as string);
          if (data.srs_hls_url) setSrsHlsUrl(data.srs_hls_url as string);
          // If task already has processed frames, HLS segments likely exist
          // (handles late-connecting WS that missed earlier hls_segment events)
          if (
            progressRef.current &&
            (progressRef.current.processed_frames ?? 0) > 0
          ) {
            setHlsReady(true);
          }
          break;

        case 'frame_result': {
          const frame: FrameDetectionResult = {
            frame_index: data.frame_index as number,
            timestamp_ms: data.timestamp_ms as number,
            boxes: (data.boxes as number[][]) || [],
            scores: (data.scores as number[]) || [],
            labels: (data.labels as number[]) || [],
            class_names: (data.class_names as string[]) || [],
            track_ids: (data.track_ids as (number | null)[]) || null,
          };
          frameMapRef.current.set(frame.frame_index, frame);
          scheduleFlush();
          break;
        }

        case 'hls_segment':
          if (!hlsReady) setHlsReady(true);
          break;

        case 'hls_manifest_final':
          if (data.hls_url) setHlsUrl(data.hls_url as string);
          break;

        case 'task_completed':
          if (data.hls_url) setHlsUrl(data.hls_url as string);
          setSrsHlsUrl(null); // Live stream ended
          if (data.original_hls_url) setOriginalHlsUrl(data.original_hls_url as string);
          // Flush remaining frames immediately
          flushPartialResult();
          cleanup();
          break;

        case 'error':
          console.warn('[VideoTaskWS] Server error:', data.message);
          break;
      }
    };

    ws.onclose = () => {
      setWsConnected(false);
      wsRef.current = null;

      // Reconnect if not intentionally closed and task still active
      if (
        !intentionalCloseRef.current &&
        retryCountRef.current < MAX_RETRIES &&
        progressRef.current &&
        ACTIVE_STATUSES.has(progressRef.current.status)
      ) {
        const delay = 1000 * Math.pow(2, retryCountRef.current);
        retryCountRef.current++;
        retryTimerRef.current = setTimeout(connect, delay);
      }
    };

    ws.onerror = () => {
      // onclose will fire after onerror — reconnect logic lives there
    };
  }, [modelId, taskId, scheduleFlush, flushPartialResult, cleanup, hlsReady]);

  // Main effect: connect/disconnect based on task status
  useEffect(() => {
    const status = videoProgress?.status;
    const shouldConnect = !!modelId && !!taskId && !!status && ACTIVE_STATUSES.has(status);

    if (shouldConnect) {
      connect();
    } else {
      cleanup();
    }

    return cleanup;
  }, [modelId, taskId, videoProgress?.status, connect, cleanup]);

  // Reset state when taskId changes (new inference started)
  useEffect(() => {
    frameMapRef.current.clear();
    setPartialResult(null);
    setHlsUrl(null);
    setSrsHlsUrl(null);
    setOriginalHlsUrl(null);
    setHlsReady(false);
    setWsConnected(false);
    retryCountRef.current = 0;
  }, [taskId]);

  return { partialResult, hlsUrl, srsHlsUrl, originalHlsUrl, hlsReady, wsConnected };
}
