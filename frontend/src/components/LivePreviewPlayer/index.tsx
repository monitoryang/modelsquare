/**
 * LivePreviewPlayer - Shared live video inference preview component.
 *
 * Encapsulates WebSocket connection, status UI, and VideoPlayer rendering
 * for real-time inference preview.  Used by both ModelDetail (inline) and
 * LivePreviewModal (inside a Modal wrapper).
 *
 * Key design choice: during live preview we only feed the *rendered* HLS
 * stream (which has detection boxes baked in and grows incrementally) to
 * VideoPlayer.  We deliberately do NOT pass `originalHlsUrl` because:
 *   1. The original HLS is a full VOD — users could seek past the inference
 *      progress, seeing un-processed content.
 *   2. Canvas overlay requires frame-level detection data for every displayed
 *      frame.  When connecting mid-inference the WebSocket does not replay
 *      historical frame results, so early frames would have no boxes.
 *
 * After the task completes, the caller switches to a regular VideoPlayer
 * with `originalHlsUrl` for full canvas overlay + class filtering.
 */

import React, { useMemo } from 'react';
import {
  Space,
  Typography,
  Progress,
  Tag,
  Spin,
} from 'antd';
import {
  LoadingOutlined,
  PlayCircleOutlined,
} from '@ant-design/icons';
import { useVideoTaskWebSocket } from '../../hooks/useVideoTaskWebSocket';
import VideoPlayer from '../VideoPlayer';
import type { VideoTaskProgress, VideoTaskResult } from '../../services';

const { Text } = Typography;

interface LivePreviewPlayerProps {
  modelId: string;
  taskId: string;
  videoProgress: VideoTaskProgress | null;
}

/** Build a minimal VideoTaskResult so VideoPlayer can render without errors */
const buildEmptyResult = (progress: VideoTaskProgress | null): VideoTaskResult => ({
  task_id: progress?.task_id || '',
  model_id: progress?.model_id || '',
  total_frames: progress?.total_frames || 0,
  fps: progress?.fps || 30,
  duration_seconds: progress?.duration_seconds || 0,
  class_colors: null,
  video_info: {},
  frame_results: [],
});

const LivePreviewPlayer: React.FC<LivePreviewPlayerProps> = ({
  modelId,
  taskId,
  videoProgress,
}) => {
  const {
    partialResult,
    hlsUrl: wsHlsUrl,
    hlsReady,
    wsConnected,
  } = useVideoTaskWebSocket(modelId, taskId, videoProgress);

  const hlsAvailable = hlsReady || !!videoProgress?.hls_url;
  const effectiveHlsUrl = wsHlsUrl || videoProgress?.hls_url || undefined;

  const emptyResult = useMemo(() => buildEmptyResult(videoProgress), [videoProgress]);
  const playerResult = partialResult || emptyResult;

  // Detection stats (informational — boxes are baked into rendered HLS)
  const detectionCount = partialResult
    ? partialResult.frame_results.reduce((sum, f) => sum + f.boxes.length, 0)
    : 0;
  const frameCount = partialResult?.frame_results.filter(f => f.boxes.length > 0).length || 0;

  return (
    <div>
      {/* Connection & Progress Status */}
      <div style={{ padding: '0 12px', marginBottom: 12 }}>
        <Space size="middle" wrap>
          <Tag
            color={wsConnected ? 'green' : 'orange'}
            icon={wsConnected
              ? <span style={{ display: 'inline-block', width: 6, height: 6, borderRadius: '50%', background: '#52c41a', marginRight: 4, animation: 'pulse 1.5s infinite' }} />
              : <LoadingOutlined style={{ marginRight: 4 }} />
            }
          >
            {wsConnected ? '已连接' : '连接中...'}
          </Tag>

          {videoProgress && (
            <>
              <Text type="secondary">
                {videoProgress.current_stage === 'inferring' ? '推理中' :
                 videoProgress.current_stage === 'rendering' ? '渲染中' :
                 videoProgress.current_stage === 'decoding' ? '解码中' :
                 videoProgress.current_stage}
              </Text>
              <Text type="secondary">
                {videoProgress.processed_frames} / {videoProgress.total_frames} 帧
              </Text>
              {videoProgress.eta_seconds != null && (
                <Text type="secondary">
                  预计剩余 {Math.ceil(videoProgress.eta_seconds)}s
                </Text>
              )}
            </>
          )}

          {partialResult && detectionCount > 0 && (
            <Tag color="blue">
              {frameCount} 帧含检测 / 共 {detectionCount} 个目标
            </Tag>
          )}
        </Space>

        {videoProgress && (
          <Progress
            percent={Math.round(videoProgress.progress_percent)}
            size="small"
            status="active"
            style={{ marginTop: 8, marginBottom: 0 }}
          />
        )}
      </div>

      {/* Video Player or Placeholder */}
      {hlsAvailable ? (
        <VideoPlayer
          isPreview
          hlsUrl={effectiveHlsUrl}
          result={playerResult}
          classColors={playerResult.class_colors || {}}
          modelId={modelId}
          taskId={taskId}
        />
      ) : (
        <div style={{ textAlign: 'center', padding: '40px 0' }}>
          {wsConnected ? (
            <>
              <PlayCircleOutlined style={{ fontSize: 48, color: '#1890ff', marginBottom: 16 }} />
              <div>
                <Text type="secondary" style={{ fontSize: 14 }}>
                  正在等待 HLS 视频流就绪...
                </Text>
              </div>
              {partialResult && (
                <div style={{ marginTop: 8 }}>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    已接收 {partialResult.frame_results.filter(f => f.boxes.length > 0).length} 帧检测结果，等待视频编码...
                  </Text>
                </div>
              )}
            </>
          ) : (
            <>
              <Spin indicator={<LoadingOutlined style={{ fontSize: 36 }} />} />
              <div style={{ marginTop: 16 }}>
                <Text type="secondary">正在连接推理预览服务...</Text>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
};

export default LivePreviewPlayer;
