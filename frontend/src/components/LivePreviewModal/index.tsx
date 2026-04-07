/**
 * LivePreviewModal - Modal wrapper around LivePreviewPlayer.
 *
 * Provides a modal shell for real-time video inference preview.
 * All preview logic (WebSocket, status UI, VideoPlayer) is delegated
 * to the shared LivePreviewPlayer component.
 */

import React from 'react';
import { Modal } from 'antd';
import LivePreviewPlayer from '../LivePreviewPlayer';
import type { VideoTaskProgress } from '../../services';

interface LivePreviewModalProps {
  open: boolean;
  onClose: () => void;
  modelId: string;
  taskId: string;
  /** VideoTaskProgress from polling or parent state */
  videoProgress: VideoTaskProgress | null;
  title?: string;
}

const LivePreviewModal: React.FC<LivePreviewModalProps> = ({
  open,
  onClose,
  modelId,
  taskId,
  videoProgress,
  title,
}) => (
  <Modal
    title={title || '实时推理预览'}
    open={open}
    onCancel={onClose}
    footer={null}
    width="80%"
    destroyOnClose
    styles={{ body: { padding: '12px 0' } }}
  >
    <LivePreviewPlayer
      modelId={modelId}
      taskId={taskId}
      videoProgress={videoProgress}
    />
  </Modal>
);

export default LivePreviewModal;
