/**
 * Application type definitions
 */

// Task type enum
export type TaskType = 'classification' | 'detection' | 'segmentation' | 'multimodal' | 'nlp';

// Framework type enum
export type Framework = 'pytorch' | 'onnx' | 'tensorrt';

// Model interface
export interface Model {
  id: string;
  owner_id: string;
  name: string;
  description: string | null;
  task_type: TaskType;
  framework: Framework;
  input_spec: Record<string, unknown> | null;
  output_spec: Record<string, unknown> | null;
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

// User interface
export interface User {
  id: string;
  email: string;
  username: string;
  full_name: string | null;
  avatar_url: string | null;
  bio: string | null;
  is_active: boolean;
  created_at: string;
}

// Inference result types
export interface DetectionResult {
  boxes: number[][];
  scores: number[];
  labels: number[];
  class_names?: string[];
}

export interface SegmentationResult {
  mask_url?: string;
  class_ids: number[];
  class_names?: string[];
}

export interface ClassificationResult {
  class_id: number;
  class_name?: string;
  confidence: number;
  top_k?: Array<{ class_id: number; class_name?: string; confidence: number }>;
}

export interface InferenceResponse {
  model_id: string;
  timestamp_in: string;
  timestamp_out: string;
  latency_ms: number;
  result_type: string;
  result: DetectionResult | SegmentationResult | ClassificationResult | Record<string, unknown>;
  render_url?: string;
}

// Stream session types
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
  last_result?: InferenceResponse;
}
