/**
 * Model related API services
 */

import api from './api';

export interface ClassConfig {
  name: string;
  color: string;
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
  create: async (data: Partial<Model>): Promise<Model> => {
    const response = await api.post('/models', data);
    return response.data;
  },

  // Update model
  update: async (modelId: string, data: Partial<Model>): Promise<Model> => {
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
  ): Promise<ModelFile> => {
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
  inferImage: async (modelId: string, image: File): Promise<unknown> => {
    const formData = new FormData();
    formData.append('image', image);
    const response = await api.post(`/models/${modelId}/infer/image`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return response.data;
  },

  // Run video inference
  inferVideo: async (modelId: string, video: File, maxFrames?: number): Promise<unknown> => {
    const formData = new FormData();
    formData.append('video', video);
    if (maxFrames) {
      formData.append('max_frames', maxFrames.toString());
    }
    const response = await api.post(`/models/${modelId}/infer/video`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return response.data;
  },
};

export default modelService;
