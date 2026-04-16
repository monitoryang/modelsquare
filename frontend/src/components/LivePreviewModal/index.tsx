/**
 * LivePreviewModal - Real-time video inference preview in a modal.
 *
 * Connects to WebSocket for live frame results and HLS streaming.
 * Used in both Profile (test records) and ModelDetail pages.
 */

import React, { useMemo } from 'react';
import {
  Modal,
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

interface LivePreviewModalProps {
  open: boolean;
  onClose: () => void;
  modelId: string;
  taskId: string;
  /** VideoTaskProgress from polling or parent state */
  videoProgress: VideoTaskProgress | null;
  title?: string;
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

const LivePreviewModal: React.FC<LivePreviewModalProps> = ({
  open,
  onClose,
  modelId,
  taskId,
  videoProgress,
  title,
}) => {
  const {
    partialResult,
    hlsUrl: wsHlsUrl,
    hlsReady,
    wsConnected,
  } = useVideoTaskWebSocket(
    open ? modelId : undefined,
    open ? taskId : null,
    open ? videoProgress : null,
  );

  const hlsAvailable = hlsReady || !!videoProgress?.hls_url;
  const effectiveHlsUrl = wsHlsUrl || videoProgress?.hls_url || undefined;

  // Use partialResult when available; fall back to an empty result so
  // the player can still show the rendered HLS stream (which already
  // contains detection boxes).
  const emptyResult = useMemo(() => buildEmptyResult(videoProgress), [videoProgress]);
  const playerResult = partialResult || emptyResult;

  // Count detections from partial result
  const detectionCount = partialResult
    ? partialResult.frame_results.reduce((sum, f) => sum + f.boxes.length, 0)
    : 0;
  const frameCount = partialResult?.frame_results.filter(f => f.boxes.length > 0).length || 0;

  return (
    <Modal
      title={title || '实时推理预览'}
      open={open}
      onCancel={onClose}
      footer={null}
      width="80%"
      destroyOnClose
      styles={{ body: { padding: '12px 0' } }}
    >
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
    </Modal>
  );
};

export default LivePreviewModal;
