/**
 * Model related API services
 */

import api from './api';

export interface ClassConfig {
  name: string;
  color: string;
}

export interface TritonStatus {
  deployed: boolean;
  loaded: boolean;
}

export interface Model {
  id: string;
  owner_id: string;
  name: string;
  description: string | null;
  task_type: 'classification' | 'detection' | 'segmentation' | 'multimodal' | 'nlp';
  framework: 'pytorch' | 'onnx' | 'tensorrt';
  network_type: 'YOLOv8' | 'YOLO11';
  input_spec: Record<string, unknown> | null;
  output_spec: Record<string, unknown> | null;
  class_config: ClassConfig[] | null;
  version: string;
  is_public: boolean;
  thumbnail_url: string | null;
  tags: string[];
  metrics: Record<string, unknown> | null;
  download_count: number;
  like_count: number;
  triton_status: TritonStatus | null;
  created_at: string;
  updated_at: string;
}

export interface ModelListResponse {
  items: Model[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export interface ModelListParams {
  task_type?: string;
  framework?: string;
  keyword?: string;
  page?: number;
  page_size?: number;
}

export interface ModelFile {
  id: string;
  file_path: string;
  file_format: string;
  file_size: number | null;
  created_at: string;
}

export interface TritonDeploymentInfo {
  deployed: boolean;
  triton_model_name: string | null;
  triton_loaded: boolean;
  error: string | null;
}

export interface ImageSize {
  width: number;
  height: number;
}

export interface ModelInfo {
  name: string;
  version: string;
  network_type: string;
  triton_model_name: string;
}

export interface DetectionResult {
  boxes: number[][];
  scores: number[];
  labels: number[];
  class_names: string[];
  class_colors: Record<string, string> | null;
  detection_count: number;
  image_size?: ImageSize;
  input_size?: ImageSize;
  model_info?: ModelInfo;
  inference_device?: string;
  status?: string;
  message?: string;
}

export interface InferenceResponse {
  model_id: string;
  timestamp_in: string;
  timestamp_out: string;
  latency_ms: number;
  result_type: string;
  result: DetectionResult;
  render_url: string | null;
}

// Video inference types
export type VideoTaskStatus = 'pending' | 'processing' | 'rendering' | 'completed' | 'failed';

export interface VideoTaskCreate {
  task_id: string;
  model_id: string;
  status: VideoTaskStatus;
  message: string;
}

export interface VideoTaskProgress {
  task_id: string;
  model_id: string;
  status: VideoTaskStatus;
  total_frames: number;
  processed_frames: number;
  progress_percent: number;
  current_stage: string;
  fps?: number;
  duration_seconds?: number;
  error_message?: string;
  created_at?: string;
  started_at?: string;
  completed_at?: string;
}

export interface FrameDetectionResult {
  frame_index: number;
  timestamp_ms: number;
  boxes: number[][];
  scores: number[];
  labels: number[];
  class_names: string[];
}

export interface VideoTaskResult {
  task_id: string;
  model_id: string;
  total_frames: number;
  fps: number;
  duration_seconds: number;
  class_colors: Record<string, string> | null;
  video_info: Record<string, unknown>;
  frame_results: FrameDetectionResult[];
  render_video_size?: number | null;  // Size of rendered video in bytes
}

export interface ModelFileUploadResponse extends ModelFile {
  triton_deployment: TritonDeploymentInfo | null;
}

// Input types for create/update operations (more permissive than Model)
export interface ModelCreateInput {
  name: string;
  description?: string | null;
  task_type: string;
  framework: string;
  network_type: string;
  version?: string;
  is_public?: boolean;
  class_config?: ClassConfig[];
}

export interface ModelUpdateInput {
  name?: string;
  description?: string | null;
  network_type?: string;
  version?: string;
  is_public?: boolean;
  class_config?: ClassConfig[];
}

export const modelService = {
  // List models with filters
  list: async (params?: ModelListParams): Promise<ModelListResponse> => {
    const response = await api.get('/models', { params });
    return response.data;
  },

  // Get model by ID
  get: async (modelId: string): Promise<Model> => {
    const response = await api.get(`/models/${modelId}`);
    return response.data;
  },

  // Create new model
  create: async (data: ModelCreateInput): Promise<Model> => {
    const response = await api.post('/models', data);
    return response.data;
  },

  // Update model
  update: async (modelId: string, data: ModelUpdateInput): Promise<Model> => {
    const response = await api.patch(`/models/${modelId}`, data);
    return response.data;
  },

  // Delete model
  delete: async (modelId: string): Promise<void> => {
    await api.delete(`/models/${modelId}`);
  },

  // Upload model file
  uploadFile: async (
    modelId: string,
    file: File,
    onProgress?: (percent: number) => void
  ): Promise<ModelFileUploadResponse> => {
    const formData = new FormData();
    formData.append('file', file);
    const response = await api.post(`/models/${modelId}/files`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress: (progressEvent) => {
        if (onProgress && progressEvent.total) {
          const percent = Math.round((progressEvent.loaded * 100) / progressEvent.total);
          onProgress(percent);
        }
      },
    });
    return response.data;
  },

  // List model files
  listFiles: async (modelId: string): Promise<ModelFile[]> => {
    const response = await api.get(`/models/${modelId}/files`);
    return response.data;
  },

  // Get file download URL
  getFileDownloadUrl: async (modelId: string, fileId: string): Promise<string> => {
    const response = await api.get(`/models/${modelId}/files/${fileId}/download`);
    return response.data.download_url;
  },

  // Delete model file
  deleteFile: async (modelId: string, fileId: string): Promise<void> => {
    await api.delete(`/models/${modelId}/files/${fileId}`);
  },

  // Upload model thumbnail
  uploadThumbnail: async (
    modelId: string,
    file: File,
    onProgress?: (percent: number) => void
  ): Promise<Model> => {
    const formData = new FormData();
    formData.append('file', file);
    const response = await api.post(`/models/${modelId}/thumbnail`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress: (progressEvent) => {
        if (onProgress && progressEvent.total) {
          const percent = Math.round((progressEvent.loaded * 100) / progressEvent.total);
          onProgress(percent);
        }
      },
    });
    return response.data;
  },

  // Get thumbnail URL
  getThumbnailUrl: async (modelId: string): Promise<string> => {
    const response = await api.get(`/models/${modelId}/thumbnail`);
    return response.data.thumbnail_url;
  },

  // Run image inference
  inferImage: async (
    modelId: string, 
    image: File, 
    confThreshold: number = 0.25,
    iouThreshold: number = 0.45
  ): Promise<InferenceResponse> => {
    const formData = new FormData();
    formData.append('image', image);
    formData.append('conf_threshold', confThreshold.toString());
    formData.append('iou_threshold', iouThreshold.toString());
    const response = await api.post(`/models/${modelId}/infer/image`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return response.data;
  },

  // Run image inference and get rendered image as blob
  inferImageRender: async (
    modelId: string,
    image: File,
    confThreshold: number = 0.25,
    iouThreshold: number = 0.45,
    lineWidth: number = 2,
    fontSize: number = 14
  ): Promise<Blob> => {
    const formData = new FormData();
    formData.append('image', image);
    formData.append('conf_threshold', confThreshold.toString());
    formData.append('iou_threshold', iouThreshold.toString());
    formData.append('line_width', lineWidth.toString());
    formData.append('font_size', fontSize.toString());
    const response = await api.post(`/models/${modelId}/infer/image/render`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      responseType: 'blob',
    });
    return response.data;
  },

  // Run video inference - submit task
  inferVideo: async (
    modelId: string,
    video: File,
    confThreshold: number = 0.25,
    iouThreshold: number = 0.45,
    sampleFps?: number,
    onProgress?: (percent: number) => void
  ): Promise<VideoTaskCreate> => {
    const formData = new FormData();
    formData.append('video', video);
    formData.append('conf_threshold', confThreshold.toString());
    formData.append('iou_threshold', iouThreshold.toString());
    if (sampleFps) {
      formData.append('sample_fps', sampleFps.toString());
    }
    const response = await api.post(`/models/${modelId}/infer/video`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 600000, // 10 minutes timeout for large video uploads
      onUploadProgress: (progressEvent) => {
        if (onProgress && progressEvent.total) {
          const percent = Math.round((progressEvent.loaded * 100) / progressEvent.total);
          onProgress(percent);
        }
      },
    });
    return response.data;
  },

  // Get video task progress
  getVideoTaskProgress: async (modelId: string, taskId: string): Promise<VideoTaskProgress> => {
    const response = await api.get(`/models/${modelId}/infer/video/${taskId}/status`);
    return response.data;
  },

  // Get video task result (JSON)
  getVideoTaskResult: async (modelId: string, taskId: string): Promise<VideoTaskResult> => {
    const response = await api.get(`/models/${modelId}/infer/video/${taskId}/result`);
    return response.data;
  },

  // Download rendered video
  downloadVideoResult: async (modelId: string, taskId: string): Promise<Blob> => {
    const response = await api.get(`/models/${modelId}/infer/video/${taskId}/download`, {
      responseType: 'blob',
    });
    return response.data;
  },
};

export default modelService;
