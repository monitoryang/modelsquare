/**
 * LivePreviewModal - Real-time video inference preview in a modal.
 *
 * Thin wrapper around LivePreviewContent that adds a Modal shell.
 * Used in Profile (test records) page.
 */

import React from 'react';
import { Modal } from 'antd';
import LivePreviewContent from '../LivePreviewContent';
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
}) => {
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
      <LivePreviewContent
        modelId={modelId}
        taskId={taskId}
        videoProgress={videoProgress}
      />
    </Modal>
  );
};

export default LivePreviewModal;
