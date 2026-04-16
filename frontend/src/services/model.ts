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
  network_type: 'YOLOv8' | 'YOLO11' | 'OWLv2';
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
  gpu_id?: number | null;
  gpu_name?: string | null;
  owl_text_encoder_gpu_id?: number | null;
  owl_image_encoder_gpu_id?: number | null;
  owl_text_encoder_large_gpu_id?: number | null;
  owl_image_encoder_large_gpu_id?: number | null;
  error: string | null;
}

export interface ModelDeploymentGpus {
  model_id: string;
  network_type: 'YOLOv8' | 'YOLO11' | 'OWLv2';
  deployed: boolean;
  loaded: boolean;
  triton_model_name: string | null;
  gpu_id: number | null;
  owl_text_encoder_gpu_id: number | null;
  owl_image_encoder_gpu_id: number | null;
  owl_text_encoder_large_gpu_id: number | null;
  owl_image_encoder_large_gpu_id: number | null;
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
  elapsed_seconds?: number;
  eta_seconds?: number;
  created_at?: string;
  started_at?: string;
  completed_at?: string;
  hls_url?: string | null;
  original_hls_url?: string | null;
  hls_segments?: number | null;
  batch_size?: number | null;
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
  hls_url?: string | null;
  original_hls_url?: string | null;
  hls_segments?: number | null;
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
  elapsed_seconds?: number | null;
  eta_seconds?: number | null;
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

export interface VideoExportTaskCreate {
  export_task_id: string;
  task_id: string;
  model_id: string;
  status: VideoTaskStatus;
  message: string;
}

export interface VideoExportTaskProgress {
  export_task_id: string;
  task_id: string;
  model_id: string;
  status: VideoTaskStatus;
  total_frames: number;
  processed_frames: number;
  progress_percent: number;
  current_stage: string;
  elapsed_seconds?: number;
  eta_seconds?: number;
  output_ready: boolean;
  error_message?: string;
  created_at?: string;
  started_at?: string;
  completed_at?: string;
}

export interface VideoExportTaskCancelResponse {
  export_task_id: string;
  status: VideoTaskStatus;
  message: string;
}

export interface VideoExportProgressState {
  phase: 'preparing' | 'converting' | 'downloading';
  percent: number;
  current_stage?: string;
  elapsed_seconds?: number;
  eta_seconds?: number;
}

// ============= VLM Types =============

export interface VLMBoundingBox {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  label: string;
  confidence?: number;
  color?: string;  // Hex color for Canvas rendering
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
  class_colors?: Record<string, string>;  // Label -> color mapping
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
  class_colors?: Record<string, string>;  // Label -> color mapping
  latency_ms: number;
  usage: Record<string, number>;
}

export interface ModelFileUploadResponse extends ModelFile {
  triton_deployment: TritonDeploymentInfo | null;
}

// TensorRT conversion types
export interface TensorRTConversionProgress {
  progress: number;
  message: string;
  status: 'converting' | 'completed' | 'failed';
  triton_loaded?: boolean;
  error?: string;
  warning?: string;
}

// OWL deployment progress types
export interface OwlDeploymentProgress {
  progress: number;
  message: string;
  status: 'deploying' | 'completed' | 'failed';
  owl_text_encoder_gpu_id?: number;
  owl_image_encoder_gpu_id?: number;
  owl_text_encoder_large_gpu_id?: number;
  owl_image_encoder_large_gpu_id?: number;
  error?: string;
}

// ============= Stream Types =============

export interface StreamSession {
  session_id: string;
  model_id: string;
  stream_url: string;
  playback_url: string;
  status: 'pending' | 'active' | 'inactive' | 'error' | 'stopped';
  created_at: string;
  expires_at: string;
}

export interface StreamStatus {
  session_id: string;
  status: string;
  frames_processed: number;
  current_fps: number;
  avg_latency_ms: number;
}

export interface StreamInferenceResult {
  session_id: string;
  frame_id: string;
  timestamp: string;
  latency_ms: number;
  avg_latency_ms: number;
  frames_processed: number;
  detections: {
    boxes: number[][];
    scores: number[];
    class_names: string[];
  };
  class_colors: Record<string, string>;
  image_size: {
    width: number;
    height: number;
  };
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

  // Get model deployment GPU mapping
  getDeploymentGpus: async (modelId: string): Promise<ModelDeploymentGpus> => {
    const response = await api.get(`/models/${modelId}/deployment-gpus`);
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
    onProgress?: (percent: number, loaded: number, total: number, rate: number) => void
  ): Promise<ModelFileUploadResponse> => {
    const formData = new FormData();
    formData.append('file', file);
    const response = await api.post(`/models/${modelId}/files`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress: (progressEvent) => {
        if (onProgress && progressEvent.total) {
          const percent = Math.round((progressEvent.loaded * 100) / progressEvent.total);
          // rate is in bytes/s (provided by axios), default 0 if not available
          const rate = (progressEvent as { rate?: number }).rate ?? 0;
          onProgress(percent, progressEvent.loaded, progressEvent.total, rate);
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
      timeout: 0, // no timeout for uploads; rely on upload progress instead
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
    onProgress?: (percent: number, loaded: number, total: number, rate: number) => void,
    textPrompts?: string,
    owlVariant?: string
  ): Promise<VideoTaskCreate> => {
    const formData = new FormData();
    formData.append('video', video);
    formData.append('conf_threshold', confThreshold.toString());
    formData.append('iou_threshold', iouThreshold.toString());
    formData.append('background_mode', backgroundMode.toString());
    if (sampleFps) {
      formData.append('sample_fps', sampleFps.toString());
    }
    if (textPrompts && textPrompts.trim()) {
      formData.append('text_prompts', textPrompts.trim());
    }
    if (owlVariant) {
      formData.append('owl_variant', owlVariant);
    }
    const response = await api.post(`/models/${modelId}/infer/video`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 1800000, // 30 minutes timeout for large video uploads
      onUploadProgress: (progressEvent) => {
        if (onProgress && progressEvent.total) {
          const percent = Math.round((progressEvent.loaded * 100) / progressEvent.total);
          const rate = (progressEvent as { rate?: number }).rate ?? 0;
          onProgress(percent, progressEvent.loaded, progressEvent.total, rate);
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
      timeout: 1800000, // 30 minutes timeout for large video downloads
    });
    return response.data;
  },

  // Download original video for frontend playback
  downloadOriginalVideo: async (modelId: string, taskId: string): Promise<Blob> => {
    const response = await api.get(`/models/${modelId}/infer/video/${taskId}/download/original`, {
      responseType: 'blob',
      timeout: 1800000,
    });
    return response.data;
  },

  // Create export task with selected classes
  createVideoExportTask: async (
    modelId: string,
    taskId: string,
    selectedClasses: string[],
  ): Promise<VideoExportTaskCreate> => {
    const response = await api.post(`/models/${modelId}/infer/video/${taskId}/export`, selectedClasses);
    return response.data;
  },

  // Poll export task progress
  getVideoExportTaskProgress: async (
    modelId: string,
    taskId: string,
    exportTaskId: string,
  ): Promise<VideoExportTaskProgress> => {
    const response = await api.get(`/models/${modelId}/infer/video/${taskId}/export/${exportTaskId}/status`);
    return response.data;
  },

  // Cancel export task
  cancelVideoExportTask: async (
    modelId: string,
    taskId: string,
    exportTaskId: string,
  ): Promise<VideoExportTaskCancelResponse> => {
    const response = await api.post(`/models/${modelId}/infer/video/${taskId}/export/${exportTaskId}/cancel`);
    return response.data;
  },

  // Download completed export task result
  downloadVideoExportTaskResult: async (
    modelId: string,
    taskId: string,
    exportTaskId: string,
    options?: { onProgress?: (progress: VideoExportProgressState) => void; signal?: AbortSignal },
  ): Promise<Blob> => {
    const response = await api.get(`/models/${modelId}/infer/video/${taskId}/export/${exportTaskId}/download`, {
      responseType: 'blob',
      timeout: 1800000,
      signal: options?.signal,
      onDownloadProgress: (progressEvent) => {
        if (options?.onProgress && progressEvent.total) {
          options.onProgress({
            phase: 'downloading',
            percent: Math.round((progressEvent.loaded / progressEvent.total) * 100),
            current_stage: 'downloading',
          });
        }
      },
    });
    return response.data;
  },

  // Export video with selected class detections as MP4
  exportVideoWithClasses: async (
    modelId: string,
    taskId: string,
    selectedClasses: string[],
    options?: {
      onProgress?: (progress: VideoExportProgressState) => void;
      signal?: AbortSignal;
    },
  ): Promise<Blob> => {
    const createRes = await modelService.createVideoExportTask(modelId, taskId, selectedClasses);

    // Poll conversion progress until completed
    while (true) {
      const progress = await modelService.getVideoExportTaskProgress(modelId, taskId, createRes.export_task_id);

      options?.onProgress?.({
        phase: 'converting',
        percent: Math.round(progress.progress_percent),
        current_stage: progress.current_stage,
        elapsed_seconds: progress.elapsed_seconds,
        eta_seconds: progress.eta_seconds,
      });

      if (progress.status === 'completed') {
        return modelService.downloadVideoExportTaskResult(modelId, taskId, createRes.export_task_id, options);
      }

      if (progress.status === 'failed') {
        throw new Error(progress.error_message || '视频导出失败');
      }

      if (progress.status === 'cancelled') {
        throw new Error('EXPORT_CANCELLED');
      }

      if (options?.signal?.aborted) {
        try {
          await modelService.cancelVideoExportTask(modelId, taskId, createRes.export_task_id);
        } catch {
          // ignore cancellation request failure
        }
        throw new Error('EXPORT_CANCELLED');
      }

      await new Promise((resolve) => setTimeout(resolve, 1000));
    }
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
    onProgress?: (percent: number) => void
  ): Promise<VLMGroundingResponse> => {
    const formData = new FormData();
    formData.append('image', image);
    formData.append('prompt', prompt);
    
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
    onProgress?: (percent: number) => void
  ): Promise<VLMGroundingChatResponse> => {
    const formData = new FormData();
    formData.append('image', image);
    formData.append('message', message);
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

  // Convert ONNX model to TensorRT with progress streaming
  convertToTensorRT: (
    modelId: string,
    useFp16: boolean = true,
    onProgress?: (data: TensorRTConversionProgress) => void,
    onComplete?: (data: TensorRTConversionProgress) => void,
    onError?: (error: Error) => void
  ): { abort: () => void } => {
    const baseUrl = api.defaults.baseURL || '';
    const token = localStorage.getItem('access_token');
    const url = `${baseUrl}/models/${modelId}/convert-to-tensorrt?use_fp16=${useFp16}`;
    
    // Use fetch with streaming for SSE
    const controller = new AbortController();
    
    (async () => {
      try {
        const response = await fetch(url, {
          method: 'POST',
          headers: {
            'Authorization': token ? `Bearer ${token}` : '',
            'Accept': 'text/event-stream',
          },
          signal: controller.signal,
        });
        
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        const reader = response.body?.getReader();
        if (!reader) {
          throw new Error('No response body');
        }
        
        const decoder = new TextDecoder();
        let buffer = '';
        
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          
          buffer += decoder.decode(value, { stream: true });
          
          // Process SSE events
          const lines = buffer.split('\n');
          buffer = lines.pop() || ''; // Keep incomplete line in buffer
          
          for (const line of lines) {
            if (line.startsWith('data: ')) {
              try {
                const data = JSON.parse(line.slice(6)) as TensorRTConversionProgress;
                if (data.status === 'completed' || data.status === 'failed') {
                  onComplete?.(data);
                } else {
                  onProgress?.(data);
                }
              } catch {
                // Skip invalid JSON
              }
            }
          }
        }
      } catch (error) {
        if ((error as Error).name !== 'AbortError') {
          onError?.(error as Error);
        }
      }
    })();
    
    return {
      abort: () => controller.abort(),
    };
  },

  // ============= Stream Session APIs =============

  // Create a new stream session
  createStreamSession: async (
    modelId: string,
    streamType: 'rtmp' | 'webrtc' | 'hls' = 'rtmp'
  ): Promise<StreamSession> => {
    const response = await api.post('/stream/start', {
      model_id: modelId,
      stream_type: streamType,
    });
    return response.data;
  },

  // Activate inference for a stream session
  activateStreamSession: async (
    sessionId: string,
    confThreshold: number = 0.25,
    iouThreshold: number = 0.45,
    textPrompts?: string,
    owlVariant?: string,
  ): Promise<{ status: string; session_id: string; message: string }> => {
    const params: Record<string, string | number> = {
      conf_threshold: confThreshold,
      iou_threshold: iouThreshold,
    };
    if (textPrompts && textPrompts.trim()) {
      params.text_prompts = textPrompts.trim();
    }
    if (owlVariant) {
      params.owl_variant = owlVariant;
    }
    const response = await api.post(
      `/stream/${sessionId}/activate`,
      null,
      { params }
    );
    return response.data;
  },

  // Update text prompts for an active OWL stream session
  updateStreamTextPrompts: async (
    sessionId: string,
    textPrompts: string,
    owlVariant?: string,
  ): Promise<{ status: string; session_id: string; message: string }> => {
    const params: Record<string, string> = { text_prompts: textPrompts.trim() };
    if (owlVariant) params.owl_variant = owlVariant;
    const response = await api.post(
      `/stream/${sessionId}/update-prompts`,
      null,
      { params }
    );
    return response.data;
  },

  // Get stream session status
  getStreamStatus: async (sessionId: string): Promise<StreamStatus> => {
    const response = await api.get(`/stream/${sessionId}/status`);
    return response.data;
  },

  // Get latest inference result
  getStreamLatestResult: async (sessionId: string): Promise<StreamInferenceResult | null> => {
    const response = await api.get(`/stream/${sessionId}/latest-result`);
    if (response.data.status === 'no_result') {
      return null;
    }
    return response.data;
  },

  // Stop stream session
  stopStreamSession: async (sessionId: string): Promise<{ status: string; session_id: string }> => {
    const response = await api.post(`/stream/${sessionId}/stop`);
    return response.data;
  },

  // Create WebSocket connection for real-time results
  createStreamWebSocket: (sessionId: string): WebSocket => {
    const baseUrl = api.defaults.baseURL || '';
    const wsUrl = baseUrl.replace(/^http/, 'ws');
    return new WebSocket(`${wsUrl}/stream/${sessionId}/ws`);
  },

  // Create WebSocket connection for real-time parameter control
  createStreamControlWebSocket: (sessionId: string): WebSocket => {
    const baseUrl = api.defaults.baseURL || '';
    const wsUrl = baseUrl.replace(/^http/, 'ws');
    return new WebSocket(`${wsUrl}/stream/${sessionId}/ws/control`);
  },

  // Create WebSocket connection for real-time video task updates
  createVideoTaskWebSocket: (modelId: string, taskId: string): WebSocket => {
    const baseUrl = api.defaults.baseURL || '';
    const wsUrl = baseUrl.replace(/^http/, 'ws');
    return new WebSocket(`${wsUrl}/models/${modelId}/infer/video/${taskId}/ws`);
  },

  // Run OWL open-vocabulary detection on a single image
  inferOwl: async (
    modelId: string,
    image: File,
    textPrompts: string,
    owlVariant: string = 'owlv2-base-patch16',
    confThreshold: number = 0.1,
    iouThreshold: number = 0.3
  ): Promise<InferenceResponse> => {
    const formData = new FormData();
    formData.append('image', image);
    formData.append('text_prompts', textPrompts);
    formData.append('owl_variant', owlVariant);
    formData.append('conf_threshold', confThreshold.toString());
    formData.append('iou_threshold', iouThreshold.toString());
    const response = await api.post(`/models/${modelId}/infer/owl`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return response.data;
  },

  // Run OWL detection and get rendered image as blob
  inferOwlRender: async (
    modelId: string,
    image: File,
    textPrompts: string,
    owlVariant: string = 'owlv2-base-patch16',
    confThreshold: number = 0.1,
    iouThreshold: number = 0.3,
    lineWidth: number = 2,
    fontSize: number = 14
  ): Promise<Blob> => {
    const formData = new FormData();
    formData.append('image', image);
    formData.append('text_prompts', textPrompts);
    formData.append('owl_variant', owlVariant);
    formData.append('conf_threshold', confThreshold.toString());
    formData.append('iou_threshold', iouThreshold.toString());
    formData.append('line_width', lineWidth.toString());
    formData.append('font_size', fontSize.toString());
    const response = await api.post(`/models/${modelId}/infer/owl/render`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      responseType: 'blob',
    });
    return response.data;
  },

  // Upload OWL ONNX files + tokenizer and auto-deploy with SSE progress streaming
  uploadOwlFiles: (
    modelId: string,
    textEncoder: File,
    textEncoderLarge: File,
    imageEncoderBase: File,
    imageEncoderLarge: File,
    tokenizerFiles: {
      vocab_json: File;
      merges_txt: File;
      tokenizer_config: File;
      special_tokens_map: File;
      added_tokens: File;
    },
    onProgress?: (data: OwlDeploymentProgress) => void,
    onComplete?: (data: OwlDeploymentProgress) => void,
    onError?: (error: Error) => void
  ): { abort: () => void } => {
    const baseUrl = api.defaults.baseURL || '';
    const token = localStorage.getItem('access_token');
    const url = `${baseUrl}/models/${modelId}/owl-files`;

    const controller = new AbortController();

    (async () => {
      try {
        const formData = new FormData();
        formData.append('text_encoder', textEncoder);
        formData.append('text_encoder_large', textEncoderLarge);
        formData.append('image_encoder_base', imageEncoderBase);
        formData.append('image_encoder_large', imageEncoderLarge);
        formData.append('vocab_json', tokenizerFiles.vocab_json);
        formData.append('merges_txt', tokenizerFiles.merges_txt);
        formData.append('tokenizer_config', tokenizerFiles.tokenizer_config);
        formData.append('special_tokens_map', tokenizerFiles.special_tokens_map);
        formData.append('added_tokens', tokenizerFiles.added_tokens);

        const response = await fetch(url, {
          method: 'POST',
          headers: {
            'Authorization': token ? `Bearer ${token}` : '',
            'Accept': 'text/event-stream',
          },
          body: formData,
          signal: controller.signal,
        });

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        const reader = response.body?.getReader();
        if (!reader) {
          throw new Error('No response body');
        }

        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });

          const lines = buffer.split('\n');
          buffer = lines.pop() || '';

          for (const line of lines) {
            if (line.startsWith('data: ')) {
              try {
                const data = JSON.parse(line.slice(6)) as OwlDeploymentProgress;
                if (data.status === 'completed' || data.status === 'failed') {
                  onComplete?.(data);
                } else {
                  onProgress?.(data);
                }
              } catch {
                // Skip invalid JSON
              }
            }
          }
        }
      } catch (error) {
        if ((error as Error).name !== 'AbortError') {
          onError?.(error as Error);
        }
      }
    })();

    return {
      abort: () => controller.abort(),
    };
  },
};
