/**
 * Chunked upload API service.
 *
 * Provides thin wrappers around the /api/v1/upload endpoints and the
 * TypeScript types that match the backend Pydantic schemas.
 */

import { api } from './api';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ChunkedUploadInitParams {
  model_id: string;
  filename: string;
  file_size: number;
  chunk_size?: number; // default 5MB on server
  content_type?: string;
  file_fingerprint: string;
  conf_threshold?: number;
  iou_threshold?: number;
  sample_fps?: number;
  text_prompts?: string;
  owl_variant?: string;
}

export interface ChunkedUploadInitResponse {
  upload_id: string;
  total_chunks: number;
  chunk_size: number;
  expires_at: string;
}

export interface ChunkUploadResponse {
  chunk_index: number;
  uploaded_chunks: number;
  total_chunks: number;
}

export interface ChunkedUploadStatus {
  upload_id: string;
  model_id: string;
  filename: string;
  file_size: number;
  file_fingerprint: string;
  chunk_size: number;
  total_chunks: number;
  uploaded_chunk_indices: number[];
  uploaded_bytes: number;
  status: 'uploading' | 'merging' | 'completed' | 'expired';
  created_at: string;
  expires_at: string;
}

export interface PendingUploadItem {
  upload_id: string;
  model_id: string;
  filename: string;
  file_size: number;
  file_fingerprint: string;
  uploaded_chunks: number;
  total_chunks: number;
  progress_percent: number;
  created_at: string;
  expires_at: string;
}

export interface PendingUploadsResponse {
  pending_uploads: PendingUploadItem[];
}

// Re-export the VideoTaskCreate type from model.ts for convenience
export type { VideoTaskCreate } from './model';

// ---------------------------------------------------------------------------
// API functions
// ---------------------------------------------------------------------------

export const uploadService = {
  /**
   * Initialize a chunked upload session.
   */
  initUpload: async (params: ChunkedUploadInitParams): Promise<ChunkedUploadInitResponse> => {
    const response = await api.post('/upload/init', params);
    return response.data;
  },

  /**
   * Upload a single chunk.
   * @param signal optional AbortSignal for cancellation
   */
  uploadChunk: async (
    uploadId: string,
    chunkIndex: number,
    data: ArrayBuffer,
    signal?: AbortSignal,
  ): Promise<ChunkUploadResponse> => {
    const response = await api.put(
      `/upload/${uploadId}/chunks/${chunkIndex}`,
      data,
      {
        headers: { 'Content-Type': 'application/octet-stream' },
        timeout: 300000, // 5 min per chunk
        signal,
      },
    );
    return response.data;
  },

  /**
   * Finalize the upload: merge chunks and start inference.
   * Returns the same VideoTaskCreate shape as the legacy inferVideo endpoint.
   */
  completeUpload: async (uploadId: string) => {
    const response = await api.post(`/upload/${uploadId}/complete`);
    return response.data;
  },

  /**
   * Query upload status (which chunks are received). Used for resume.
   */
  getUploadStatus: async (uploadId: string): Promise<ChunkedUploadStatus> => {
    const response = await api.get(`/upload/${uploadId}/status`);
    return response.data;
  },

  /**
   * Cancel an in-progress upload and clean up server-side resources.
   */
  cancelUpload: async (uploadId: string): Promise<{ message: string }> => {
    const response = await api.delete(`/upload/${uploadId}`);
    return response.data;
  },

  /**
   * List all pending (incomplete) uploads for the current user.
   */
  getPendingUploads: async (modelId?: string): Promise<PendingUploadsResponse> => {
    const params = modelId ? { model_id: modelId } : {};
    const response = await api.get('/upload/pending', { params });
    return response.data;
  },
};
