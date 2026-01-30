export { api } from './api';
export { modelService } from './model';
export { authService } from './auth';
export type { 
  Model, 
  ModelListResponse, 
  ModelListParams, 
  InferenceResponse, 
  DetectionResult,
  VideoTaskCreate,
  VideoTaskProgress,
  VideoTaskResult,
  FrameDetectionResult,
} from './model';
export type { User, LoginRequest, RegisterRequest, TokenResponse } from './auth';
