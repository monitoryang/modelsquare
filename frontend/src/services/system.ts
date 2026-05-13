/**
 * System monitoring services (GPU, health checks)
 */

import { api } from './api';

export interface GPUModelInfo {
  id: string;
  name: string;
  task_type: string | null;
  network_type: string | null;
  gpu_id: number | null;
  is_deployed: boolean;
  is_loaded: boolean;
  created_at: string | null;
}

export interface GPUInfo {
  index: number;
  name: string;
  memory_total_gb: number;
  memory_used_gb: number;
  memory_free_gb: number;
  memory_usage_percent: number;
  gpu_utilization: number;
  load_score: number;
  models: GPUModelInfo[];
  model_count: number;
}

export interface GPUMonitorResponse {
  gpu_count: number;
  monitoring_available: boolean;
  gpus: GPUInfo[];
  total_models: number;
  deployed_models: number;
  loaded_models: number;
  unassigned_models: GPUModelInfo[];
}

export interface LocalDiskInfo {
  mount_point: string;
  total_bytes: number;
  used_bytes: number;
  free_bytes: number;
  usage_percent: number;
  total_display: string;
  used_display: string;
  free_display: string;
  monitored_paths: string[];
}

export interface MinIOBucketInfo {
  name: string;
  object_count: number;
  used_bytes: number;
  used_display: string;
}

export interface MinIOStorageInfo {
  available: boolean;
  buckets: MinIOBucketInfo[];
  total_used_bytes: number;
  total_used_display: string;
  total_object_count: number;
}

export interface StorageMonitorResponse {
  local_disks: LocalDiskInfo[];
  minio: MinIOStorageInfo;
}

export const systemService = {
  /**
   * Get GPU monitoring data with model distribution (superuser only)
   */
  getGPUMonitor: async (): Promise<GPUMonitorResponse> => {
    const response = await api.get('/health/gpus/monitor');
    return response.data;
  },

  /**
   * Get basic GPU status (public)
   */
  getGPUStatus: async () => {
    const response = await api.get('/health/gpus');
    return response.data;
  },

  /**
   * Get storage monitoring data (superuser only)
   */
  getStorageMonitor: async (): Promise<StorageMonitorResponse> => {
    const response = await api.get('/health/storage');
    return response.data;
  },
};
