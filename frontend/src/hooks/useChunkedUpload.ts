/**
 * useChunkedUpload – React hook for resumable chunked video upload.
 *
 * Features:
 *  - Splits a File into 5 MB chunks and uploads them in parallel (concurrency=3).
 *  - Persists progress to localStorage so a page refresh can resume.
 *  - Automatic per-chunk retry with exponential back-off (3 attempts).
 *  - AbortController-based cancellation.
 */

import { useCallback, useRef, useState } from 'react';
import { uploadService } from '../services/upload';
import type { VideoTaskCreate } from '../services/model';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const DEFAULT_CHUNK_SIZE = 5 * 1024 * 1024; // 5 MB
const MAX_CONCURRENCY = 3;
const MAX_RETRIES = 3;
const RATE_WINDOW_MS = 3000; // sliding window for upload rate

// ---------------------------------------------------------------------------
// localStorage helpers
// ---------------------------------------------------------------------------

export interface PersistedUpload {
  uploadId: string;
  modelId: string;
  filename: string;
  fileSize: number;
  fingerprint: string;
  totalChunks: number;
  chunkSize: number;
  uploadedChunks: number[]; // chunk indices that have been confirmed
  inferParams?: InferParams; // inference parameters (text_prompts, etc.)
}

function storageKey(modelId: string) {
  return `chunked_upload_${modelId}`;
}

function loadPersisted(modelId: string): PersistedUpload | null {
  try {
    const raw = localStorage.getItem(storageKey(modelId));
    return raw ? (JSON.parse(raw) as PersistedUpload) : null;
  } catch {
    return null;
  }
}

function savePersisted(modelId: string, data: PersistedUpload) {
  localStorage.setItem(storageKey(modelId), JSON.stringify(data));
}

function clearPersisted(modelId: string) {
  localStorage.removeItem(storageKey(modelId));
}

// ---------------------------------------------------------------------------
// File fingerprint (name + size + lastModified)
// ---------------------------------------------------------------------------

function fileFingerprint(file: File): string {
  return `${file.name}_${file.size}_${file.lastModified}`;
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type UploadPhase = 'idle' | 'uploading' | 'merging' | 'complete' | 'error';

export interface InferParams {
  confThreshold: number;
  iouThreshold: number;
  sampleFps?: number;
  textPrompts?: string;
  owlVariant?: string;
}

export interface ChunkedUploadState {
  phase: UploadPhase;
  /** Overall upload progress 0–100 */
  progress: number;
  /** Bytes per second (smoothed) */
  uploadRate: number;
  /** Current upload session id */
  uploadId: string | null;
  /** Total bytes to upload */
  totalBytes: number;
  /** Bytes uploaded so far */
  uploadedBytes: number;
  /** Error message if phase === 'error' */
  error: string | null;
}

export interface UseChunkedUploadReturn extends ChunkedUploadState {
  /** Start a fresh upload. Resolves with task_id when inference starts. */
  startUpload: (file: File, modelId: string, params: InferParams) => Promise<VideoTaskCreate | null>;
  /** Resume a previously interrupted upload. User must supply the same File. */
  resumeUpload: (file: File, modelId: string) => Promise<VideoTaskCreate | null>;
  /** Cancel the in-progress upload. */
  cancelUpload: (modelId: string) => Promise<void>;
  /** Check if there is a persisted upload for a model. */
  getPersistedUpload: (modelId: string) => PersistedUpload | null;
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useChunkedUpload(): UseChunkedUploadReturn {
  const [phase, setPhase] = useState<UploadPhase>('idle');
  const [progress, setProgress] = useState(0);
  const [uploadRate, setUploadRate] = useState(0);
  const [uploadId, setUploadId] = useState<string | null>(null);
  const [totalBytes, setTotalBytes] = useState(0);
  const [uploadedBytes, setUploadedBytes] = useState(0);
  const [error, setError] = useState<string | null>(null);

  // AbortController for cancellation
  const abortRef = useRef<AbortController | null>(null);
  // Track bytes for rate calculation
  const rateTracker = useRef<{ t: number; b: number }[]>([]);

  // ----- internal: upload missing chunks with concurrency control -----

  const uploadChunks = useCallback(
    async (
      file: File,
      uid: string,
      modelId: string,
      chunkSize: number,
      totalChunks: number,
      alreadyDone: Set<number>,
      inferParams?: InferParams,
    ) => {
      const pending = Array.from({ length: totalChunks }, (_, i) => i).filter(
        (i) => !alreadyDone.has(i),
      );

      let completedCount = alreadyDone.size;
      const totalSize = file.size;
      let bytesUploaded = Array.from(alreadyDone).reduce((sum, idx) => {
        const start = idx * chunkSize;
        const end = Math.min(start + chunkSize, totalSize);
        return sum + (end - start);
      }, 0);
      setUploadedBytes(bytesUploaded);
      setProgress(totalChunks > 0 ? Math.round((completedCount / totalChunks) * 100) : 0);

      // Persisted state init
      const persisted: PersistedUpload = {
        uploadId: uid,
        modelId,
        filename: file.name,
        fileSize: file.size,
        fingerprint: fileFingerprint(file),
        totalChunks,
        chunkSize,
        uploadedChunks: Array.from(alreadyDone),
        inferParams,
      };
      savePersisted(modelId, persisted);

      // Rate tracking reset
      rateTracker.current = [{ t: Date.now(), b: bytesUploaded }];

      // Process with bounded concurrency
      let idx = 0;
      const errors: Error[] = [];

      async function worker() {
        while (idx < pending.length) {
          if (abortRef.current?.signal.aborted) return;
          const chunkIdx = pending[idx++];
          const start = chunkIdx * chunkSize;
          const end = Math.min(start + chunkSize, totalSize);
          const blob = file.slice(start, end);
          const buf = await blob.arrayBuffer();

          let success = false;
          for (let attempt = 0; attempt < MAX_RETRIES; attempt++) {
            if (abortRef.current?.signal.aborted) return;
            try {
              await uploadService.uploadChunk(uid, chunkIdx, buf, abortRef.current?.signal);
              success = true;
              break;
            } catch {
              if (abortRef.current?.signal.aborted) return;
              // exponential backoff
              const delay = Math.min(1000 * 2 ** attempt, 8000);
              await new Promise((r) => setTimeout(r, delay));
            }
          }

          if (!success) {
            errors.push(new Error(`Failed to upload chunk ${chunkIdx} after ${MAX_RETRIES} retries`));
            return;
          }

          completedCount++;
          bytesUploaded += end - start;
          setUploadedBytes(bytesUploaded);
          setProgress(Math.round((completedCount / totalChunks) * 100));

          // Rate
          const now = Date.now();
          rateTracker.current.push({ t: now, b: bytesUploaded });
          rateTracker.current = rateTracker.current.filter((e) => now - e.t < RATE_WINDOW_MS);
          if (rateTracker.current.length >= 2) {
            const first = rateTracker.current[0];
            const dt = (now - first.t) / 1000;
            setUploadRate(dt > 0 ? (bytesUploaded - first.b) / dt : 0);
          }

          // Persist
          persisted.uploadedChunks = [...new Set([...persisted.uploadedChunks, chunkIdx])];
          savePersisted(modelId, persisted);
        }
      }

      const workers = Array.from({ length: Math.min(MAX_CONCURRENCY, pending.length) }, () => worker());
      await Promise.all(workers);

      if (errors.length > 0) {
        throw errors[0];
      }
    },
    [],
  );

  // ----- startUpload -----

  const startUpload = useCallback(
    async (file: File, modelId: string, params: InferParams): Promise<VideoTaskCreate | null> => {
      try {
        setPhase('uploading');
        setError(null);
        setProgress(0);
        setUploadRate(0);
        setTotalBytes(file.size);
        setUploadedBytes(0);

        abortRef.current = new AbortController();

        const chunkSize = DEFAULT_CHUNK_SIZE;
        const fp = fileFingerprint(file);

        const initResp = await uploadService.initUpload({
          model_id: modelId,
          filename: file.name,
          file_size: file.size,
          chunk_size: chunkSize,
          file_fingerprint: fp,
          conf_threshold: params.confThreshold,
          iou_threshold: params.iouThreshold,
          sample_fps: params.sampleFps,
          text_prompts: params.textPrompts,
          owl_variant: params.owlVariant,
        });

        setUploadId(initResp.upload_id);

        await uploadChunks(
          file,
          initResp.upload_id,
          modelId,
          chunkSize,
          initResp.total_chunks,
          new Set<number>(),
          params,
        );

        if (abortRef.current?.signal.aborted) return null;

        // Merge + start inference
        setPhase('merging');
        const taskCreate = await uploadService.completeUpload(initResp.upload_id);
        clearPersisted(modelId);
        setPhase('complete');
        return taskCreate as VideoTaskCreate;
      } catch (err: unknown) {
        if (abortRef.current?.signal.aborted) return null;
        const msg = err instanceof Error ? err.message : String(err);
        setError(msg);
        setPhase('error');
        return null;
      }
    },
    [uploadChunks],
  );

  // ----- resumeUpload -----

  const resumeUpload = useCallback(
    async (file: File, modelId: string): Promise<VideoTaskCreate | null> => {
      try {
        const persisted = loadPersisted(modelId);
        if (!persisted) {
          throw new Error('No persisted upload found');
        }

        // Verify file fingerprint
        if (fileFingerprint(file) !== persisted.fingerprint) {
          throw new Error('File fingerprint mismatch – please select the same file');
        }

        setPhase('uploading');
        setError(null);
        setTotalBytes(file.size);
        setUploadId(persisted.uploadId);

        abortRef.current = new AbortController();

        // Ask server which chunks it actually has (authoritative)
        let serverStatus;
        try {
          serverStatus = await uploadService.getUploadStatus(persisted.uploadId);
        } catch {
          // Session expired on server
          clearPersisted(modelId);
          throw new Error('Upload session expired on server. Please start a new upload.');
        }

        if (serverStatus.status !== 'uploading') {
          clearPersisted(modelId);
          throw new Error(`Upload session is in '${serverStatus.status}' state`);
        }

        const alreadyDone = new Set(serverStatus.uploaded_chunk_indices);

        await uploadChunks(
          file,
          persisted.uploadId,
          modelId,
          persisted.chunkSize,
          persisted.totalChunks,
          alreadyDone,
          persisted.inferParams,
        );

        if (abortRef.current?.signal.aborted) return null;

        setPhase('merging');
        const taskCreate = await uploadService.completeUpload(persisted.uploadId);
        clearPersisted(modelId);
        setPhase('complete');
        return taskCreate as VideoTaskCreate;
      } catch (err: unknown) {
        if (abortRef.current?.signal.aborted) return null;
        const msg = err instanceof Error ? err.message : String(err);
        setError(msg);
        setPhase('error');
        return null;
      }
    },
    [uploadChunks],
  );

  // ----- cancelUpload -----

  const cancelUploadFn = useCallback(async (modelId: string) => {
    // Abort in-flight requests
    abortRef.current?.abort();

    const persisted = loadPersisted(modelId);
    if (persisted) {
      try {
        await uploadService.cancelUpload(persisted.uploadId);
      } catch {
        // best-effort server cleanup
      }
      clearPersisted(modelId);
    }

    setPhase('idle');
    setProgress(0);
    setUploadRate(0);
    setUploadId(null);
    setUploadedBytes(0);
    setTotalBytes(0);
    setError(null);
  }, []);

  // ----- getPersistedUpload -----

  const getPersistedUpload = useCallback((modelId: string) => {
    return loadPersisted(modelId);
  }, []);

  return {
    phase,
    progress,
    uploadRate,
    uploadId,
    totalBytes,
    uploadedBytes,
    error,
    startUpload,
    resumeUpload,
    cancelUpload: cancelUploadFn,
    getPersistedUpload,
  };
}
