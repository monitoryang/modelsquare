/**
 * Authentication related API services
 */

import api from './api';

export interface User {
  id: string;
  email: string;
  username: string;
  full_name: string | null;
  avatar_url: string | null;
  bio: string | null;
  is_active: boolean;
  is_superuser: boolean;
  created_at: string;
}

export interface LoginRequest {
  username: string;  // Actually email
  password: string;
}

export interface RegisterRequest {
  email: string;
  username: string;
  password: string;
  full_name?: string;
  verification_code: string;
}

export interface CreateUserRequest {
  email: string;
  username: string;
  password: string;
  full_name?: string;
}

export interface SendVerificationCodeRequest {
  email: string;
}

export interface SendVerificationCodeResponse {
  success: boolean;
  message: string;
}

export interface UserListResponse {
  items: User[];
  total: number;
  page: number;
  page_size: number;
}

export interface UserStatusUpdate {
  is_active?: boolean;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

// New API Key interfaces
export interface ApiKeyInfo {
  id: string;
  name: string;
  key: string;
  is_active: boolean;
  expires_at: string;
  last_used_at: string | null;
  created_at: string;
  total_calls: number;
  is_expired: boolean;
  is_valid: boolean;
}

export interface ApiKeyListResponse {
  items: ApiKeyInfo[];
  total: number;
}

export interface ApiKeyCreateRequest {
  name: string;
  expires_in_days: number;
}

export interface ApiKeyUpdateRequest {
  name?: string;
  is_active?: boolean;
}

export interface ApiUsageDaily {
  date: string;
  call_count: number;
  success_count: number;
  error_count: number;
  avg_latency_ms: number;
}

export interface ApiUsageSummary {
  total_calls: number;
  total_success: number;
  total_errors: number;
  avg_latency_ms: number;
  daily_usage: ApiUsageDaily[];
}

export interface ApiKeyUsageResponse {
  key_info: ApiKeyInfo;
  usage_summary: ApiUsageSummary;
}

export const authService = {
  // Login
  login: async (data: LoginRequest): Promise<TokenResponse> => {
    const formData = new URLSearchParams();
    formData.append('username', data.username);
    formData.append('password', data.password);
    
    const response = await api.post('/auth/login', formData, {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    });
    
    const tokens = response.data;
    localStorage.setItem('access_token', tokens.access_token);
    localStorage.setItem('refresh_token', tokens.refresh_token);
    
    return tokens;
  },

  // Register
  register: async (data: RegisterRequest): Promise<User> => {
    const response = await api.post('/auth/register', data);
    return response.data;
  },

  // Get current user
  getCurrentUser: async (): Promise<User> => {
    const response = await api.get('/auth/me');
    return response.data;
  },

  // Logout
  logout: () => {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    window.location.href = '/login';
  },

  // Check if user is authenticated
  isAuthenticated: (): boolean => {
    return !!localStorage.getItem('access_token');
  },

  // ============= API Key Management =============

  // List all API keys
  listApiKeys: async (): Promise<ApiKeyListResponse> => {
    const response = await api.get('/auth/apikeys');
    return response.data;
  },

  // Create new API key
  createApiKey: async (data: ApiKeyCreateRequest): Promise<ApiKeyInfo> => {
    const response = await api.post('/auth/apikeys', data);
    return response.data;
  },

  // Get API key details with usage statistics
  getApiKeyDetail: async (keyId: string, days: number = 30): Promise<ApiKeyUsageResponse> => {
    const response = await api.get(`/auth/apikeys/${keyId}`, { params: { days } });
    return response.data;
  },

  // Update API key
  updateApiKey: async (keyId: string, data: ApiKeyUpdateRequest): Promise<ApiKeyInfo> => {
    const response = await api.patch(`/auth/apikeys/${keyId}`, data);
    return response.data;
  },

  // Delete API key
  deleteApiKey: async (keyId: string): Promise<void> => {
    await api.delete(`/auth/apikeys/${keyId}`);
  },

  // ============= Email Verification =============

  // Send verification code
  sendVerificationCode: async (email: string): Promise<SendVerificationCodeResponse> => {
    const response = await api.post('/auth/send-verification-code', { email });
    return response.data;
  },

  // ============= User Management (Superuser Only) =============

  // List all users
  listUsers: async (page: number = 1, pageSize: number = 10): Promise<UserListResponse> => {
    const response = await api.get('/auth/users', { params: { page, page_size: pageSize } });
    return response.data;
  },

  // Create new user (by admin)
  createUser: async (data: CreateUserRequest): Promise<User> => {
    const response = await api.post('/auth/users', data);
    return response.data;
  },

  // Update user status
  updateUserStatus: async (userId: string, data: UserStatusUpdate): Promise<User> => {
    const response = await api.patch(`/auth/users/${userId}`, data);
    return response.data;
  },

  // Delete user
  deleteUser: async (userId: string): Promise<void> => {
    await api.delete(`/auth/users/${userId}`);
  },
};

export default authService;
