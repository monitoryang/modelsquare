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
export type VideoTaskStatus = 'pending' | 'processing' | 'rendering' | 'completed' | 'failed' | 'cancelled';

export interface VideoTaskCreate {
  task_id: string;
  model_id: string;
  status: VideoTaskStatus;
  message: string;
  background_mode: boolean;
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

// User video task types
export interface UserVideoTask {
  id: string;
  task_id: string;
  model_id: string;
  model_name: string | null;
  video_filename: string;
  video_size: number | null;
  status: VideoTaskStatus;
  current_stage: string | null;
  total_frames: number;
  processed_frames: number;
  progress_percent: number;
  fps: number | null;
  duration_seconds: number | null;
  render_video_size: number | null;
  error_message: string | null;
  background_mode: boolean;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
}

export interface UserVideoTaskListResponse {
  items: UserVideoTask[];
  total: number;
  page: number;
  page_size: number;
}

export interface VideoTaskCancelResponse {
  task_id: string;
  status: VideoTaskStatus;
  message: string;
}

// ============= VLM Types =============

export interface VLMBoundingBox {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  label: string;
  confidence?: number;
}

export interface VLMHealthResponse {
  status: string;
  model_name?: string;
  available_models: string[];
}

export interface VLMGroundingResponse {
  boxes: VLMBoundingBox[];
  detection_count: number;
  image_width: number;
  image_height: number;
  raw_response: string;
  latency_ms: number;
  render_url?: string;
}

export interface VLMChatMessage {
  role: 'system' | 'user' | 'assistant';
  content: string;
}

export interface VLMChatResponse {
  message: VLMChatMessage;
  finish_reason: string;
  usage: Record<string, number>;
  latency_ms: number;
}

export interface VLMGroundingChatResponse {
  response: string;
  boxes: VLMBoundingBox[];
  detection_count: number;
  image_width: number;
  image_height: number;
  render_url?: string;
  latency_ms: number;
  usage: Record<string, number>;
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
    backgroundMode: boolean = false,
    onProgress?: (percent: number) => void
  ): Promise<VideoTaskCreate> => {
    const formData = new FormData();
    formData.append('video', video);
    formData.append('conf_threshold', confThreshold.toString());
    formData.append('iou_threshold', iouThreshold.toString());
    formData.append('background_mode', backgroundMode.toString());
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
      timeout: 600000, // 10 minutes timeout for large video downloads
    });
    return response.data;
  },

  // Get user's video tasks
  getUserVideoTasks: async (
    page: number = 1,
    pageSize: number = 10,
    statusFilter?: string
  ): Promise<UserVideoTaskListResponse> => {
    const params: Record<string, string | number> = { page, page_size: pageSize };
    if (statusFilter) {
      params.status_filter = statusFilter;
    }
    const response = await api.get('/models/user/video-tasks', { params });
    return response.data;
  },

  // Cancel a video task
  cancelVideoTask: async (taskId: string): Promise<VideoTaskCancelResponse> => {
    const response = await api.post(`/models/user/video-tasks/${taskId}/cancel`);
    return response.data;
  },

  // Delete a video task from history
  deleteVideoTask: async (taskId: string): Promise<void> => {
    await api.delete(`/models/user/video-tasks/${taskId}`);
  },

  // ============= VLM Grounding Detection APIs =============

  // Check VLM service health
  vlmHealthCheck: async (): Promise<VLMHealthResponse> => {
    const response = await api.get('/models/vlm/health');
    return response.data;
  },

  // Perform grounding detection using VLM
  vlmGroundingDetection: async (
    image: File,
    prompt: string,
    renderBoxes: boolean = true,
    onProgress?: (percent: number) => void
  ): Promise<VLMGroundingResponse> => {
    const formData = new FormData();
    formData.append('image', image);
    formData.append('prompt', prompt);
    formData.append('render_boxes', renderBoxes.toString());
    
    const response = await api.post('/models/vlm/grounding', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 120000, // 2 minutes timeout for VLM inference
      onUploadProgress: (progressEvent) => {
        if (onProgress && progressEvent.total) {
          const percent = Math.round((progressEvent.loaded * 100) / progressEvent.total);
          onProgress(percent);
        }
      },
    });
    return response.data;
  },

  // VLM chat completion with optional image
  vlmChat: async (
    messages: VLMChatMessage[],
    image?: File,
    maxTokens: number = 2048,
    temperature: number = 0.7
  ): Promise<VLMChatResponse> => {
    const formData = new FormData();
    formData.append('request', JSON.stringify({ messages, max_tokens: maxTokens, temperature }));
    if (image) {
      formData.append('image', image);
    }
    
    const response = await api.post('/models/vlm/chat', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 120000,
    });
    return response.data;
  },

  // Conversational grounding detection
  vlmGroundingChat: async (
    image: File,
    message: string,
    history?: VLMChatMessage[],
    renderBoxes: boolean = true,
    onProgress?: (percent: number) => void
  ): Promise<VLMGroundingChatResponse> => {
    const formData = new FormData();
    formData.append('image', image);
    formData.append('message', message);
    formData.append('render_boxes', renderBoxes.toString());
    if (history && history.length > 0) {
      formData.append('history', JSON.stringify(history));
    }
    
    const response = await api.post('/models/vlm/grounding/chat', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 120000,
      onUploadProgress: (progressEvent) => {
        if (onProgress && progressEvent.total) {
          const percent = Math.round((progressEvent.loaded * 100) / progressEvent.total);
          onProgress(percent);
        }
      },
    });
    return response.data;
  },
};

export default modelService;
