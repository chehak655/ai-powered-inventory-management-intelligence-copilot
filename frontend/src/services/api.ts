import axios from 'axios';
import {
  Dataset,
  DatasetListResponse,
  DatasetPreviewResponse,
  SuggestedConfig,
  DatasetConfiguration,
  Company,
  User,
  TrainingRun,
  CandidateModel,
  ModelComparisonResponse,
  ModelSchemaResponse,
  PredictionResponse,
  PredictionLog,
  InventoryKPIsResponse,
  CopilotResponse,
  WorkspaceMember,
  AddWorkerPayload,
  WorkspaceJoinRequest,
  WorkerJoinRequestPayload,
} from '../types';

const api = axios.create({
  baseURL: '/api/v1',
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor to attach JWT token and active company ID
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }

  const companyId = localStorage.getItem('active_company_id');
  if (companyId) {
    config.headers['X-Company-Id'] = companyId;
  }

  return config;
});

// Response interceptor for session expiration
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response && error.response.status === 401) {
      if (!window.location.pathname.includes('/login')) {
        localStorage.removeItem('token');
        localStorage.removeItem('active_company_id');
        window.location.href = '/login';
      }
    }
    return Promise.reject(error);
  }
);

export const authApi = {
  login: async (email: string, password: string) => {
    const res = await api.post<{ access_token: string; user: User; companies: Company[] }>('/auth/login', {
      email,
      password,
    });
    return res.data;
  },
  register: async (email: string, password: string, fullName: string, companyName: string) => {
    const res = await api.post<{ access_token: string; user: User; companies: Company[] }>('/auth/register', {
      email,
      password,
      full_name: fullName,
      company_name: companyName,
    });
    return res.data;
  },
  getMe: async () => {
    const res = await api.get<{ user: User; companies: Company[] }>('/auth/me');
    return res.data;
  },
  logout: async () => {
    const res = await api.post('/auth/logout');
    return res.data;
  },
  submitJoinRequest: async (payload: WorkerJoinRequestPayload) => {
    const res = await api.post<WorkspaceJoinRequest>('/auth/join-request', payload);
    return res.data;
  },
};

export const workspaceApi = {
  list: async () => {
    const res = await api.get<Company[]>('/workspaces/');
    return res.data;
  },
  current: async () => {
    const res = await api.get<Company>('/workspaces/current');
    return res.data;
  },
  getMembers: async () => {
    const res = await api.get<WorkspaceMember[]>('/workspaces/members');
    return res.data;
  },
  addWorker: async (data: AddWorkerPayload) => {
    const res = await api.post<WorkspaceMember>('/workspaces/workers', data);
    return res.data;
  },
  updateRole: async (memberId: string, role: 'OWNER' | 'WORKER') => {
    const res = await api.put<WorkspaceMember>(`/workspaces/members/${memberId}/role`, { role });
    return res.data;
  },
  getJoinRequests: async (status?: string) => {
    const res = await api.get<WorkspaceJoinRequest[]>('/workspaces/join-requests', {
      params: status ? { status } : undefined,
    });
    return res.data;
  },
  approveJoinRequest: async (requestId: string) => {
    const res = await api.post<WorkspaceJoinRequest>(`/workspaces/join-requests/${requestId}/approve`);
    return res.data;
  },
  rejectJoinRequest: async (requestId: string, reason?: string) => {
    const res = await api.post<WorkspaceJoinRequest>(`/workspaces/join-requests/${requestId}/reject`, {
      reason,
    });
    return res.data;
  },
};

export const datasetApi = {
  upload: async (file: File, name?: string, onProgress?: (percent: number) => void) => {
    const formData = new FormData();
    formData.append('file', file);
    if (name) {
      formData.append('name', name);
    }

    const res = await api.post<Dataset>('/datasets/upload', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
      onUploadProgress: (progressEvent) => {
        if (progressEvent.total && onProgress) {
          const percent = Math.round((progressEvent.loaded * 100) / progressEvent.total);
          onProgress(percent);
        }
      },
    });
    return res.data;
  },
  list: async (page = 1, pageSize = 10, search?: string) => {
    const res = await api.get<DatasetListResponse>('/datasets/', {
      params: { page, page_size: pageSize, search },
    });
    return res.data;
  },
  get: async (id: string) => {
    const res = await api.get<Dataset>(`/datasets/${id}`);
    return res.data;
  },
  preview: async (id: string, page = 1, pageSize = 20) => {
    const res = await api.get<DatasetPreviewResponse>(`/datasets/${id}/preview`, {
      params: { page, page_size: pageSize },
    });
    return res.data;
  },
  getSuggestedConfig: async (id: string) => {
    const res = await api.get<SuggestedConfig>(`/datasets/${id}/suggested-config`);
    return res.data;
  },
  getConfig: async (id: string) => {
    const res = await api.get<DatasetConfiguration>(`/datasets/${id}/configuration`);
    return res.data;
  },
  saveConfig: async (id: string, config: {
    task_type: string;
    target_column?: string | null;
    feature_columns: string[];
    date_column?: string | null;
    entity_columns?: string[] | null;
    excluded_columns?: string[] | null;
  }) => {
    const res = await api.post<DatasetConfiguration>(`/datasets/${id}/configuration`, config);
    return res.data;
  },
  delete: async (id: string) => {
    const res = await api.delete(`/datasets/${id}`);
    return res.data;
  },
  downloadUrl: (id: string) => `/api/v1/datasets/${id}/download`,
};

export const trainingApi = {
  start: async (datasetId: string, taskType?: string) => {
    const res = await api.post<TrainingRun>('/training/start', {
      dataset_id: datasetId,
      task_type: taskType,
    });
    return res.data;
  },
  listRuns: async (datasetId?: string, limit = 20) => {
    const res = await api.get<TrainingRun[]>('/training/runs', {
      params: { dataset_id: datasetId, limit },
    });
    return res.data;
  },
  getRun: async (runId: string) => {
    const res = await api.get<TrainingRun>(`/training/runs/${runId}`);
    return res.data;
  },
  getStatus: async (runId: string) => {
    const res = await api.get<{
      id: string;
      status: string;
      task_type: string;
      candidate_count: number;
      duration_seconds: number;
      error_message?: string | null;
    }>(`/training/runs/${runId}/status`);
    return res.data;
  },
  getComparison: async (runId: string) => {
    const res = await api.get<ModelComparisonResponse>(`/training/runs/${runId}/comparison`);
    return res.data;
  },
  getModel: async (modelId: string) => {
    const res = await api.get<CandidateModel>(`/training/models/${modelId}`);
    return res.data;
  },
  activateModel: async (modelId: string) => {
    const res = await api.post<CandidateModel>(`/training/models/${modelId}/activate`);
    return res.data;
  },
};

export const modelsApi = {
  list: async (datasetId?: string, isActive?: boolean, taskType?: string) => {
    const res = await api.get<CandidateModel[]>('/models/', {
      params: { dataset_id: datasetId, is_active: isActive, task_type: taskType },
    });
    return res.data;
  },
  get: async (modelId: string) => {
    const res = await api.get<CandidateModel>(`/models/${modelId}`);
    return res.data;
  },
  activate: async (modelId: string) => {
    const res = await api.post<CandidateModel>(`/models/${modelId}/activate`);
    return res.data;
  },
  getSchema: async (modelId: string) => {
    const res = await api.get<ModelSchemaResponse>(`/models/${modelId}/schema`);
    return res.data;
  },
};

export const predictionApi = {
  predictSingle: async (data: { model_id?: string; dataset_id?: string; inputs: Record<string, any> }) => {
    const res = await api.post<PredictionResponse>('/predictions/single', data);
    return res.data;
  },
  predictBatch: async (data: { model_id?: string; dataset_id?: string; records: Record<string, any>[] }) => {
    const res = await api.post<PredictionResponse>('/predictions/batch', data);
    return res.data;
  },
  predictBatchFile: async (file: File, modelId?: string, datasetId?: string) => {
    const formData = new FormData();
    formData.append('file', file);
    const res = await api.post('/predictions/batch-file', formData, {
      params: { model_id: modelId, dataset_id: datasetId },
      headers: { 'Content-Type': 'multipart/form-data' },
      responseType: 'blob',
    });
    return res.data;
  },
  getHistory: async (modelId?: string, datasetId?: string, limit = 20) => {
    const res = await api.get<PredictionLog[]>('/predictions/history', {
      params: { model_id: modelId, dataset_id: datasetId, limit },
    });
    return res.data;
  },
};

export const inventoryApi = {
  getKpis: async (datasetId?: string, serviceLevel = 0.95) => {
    const res = await api.get<InventoryKPIsResponse>('/inventory/kpis', {
      params: { dataset_id: datasetId, service_level: serviceLevel },
    });
    return res.data;
  },
};

export const copilotApi = {
  query: async (prompt: string) => {
    const res = await api.post<CopilotResponse>('/copilot/query', { prompt });
    return res.data;
  },
  getPrompts: async () => {
    const res = await api.get<string[]>('/copilot/prompts');
    return res.data;
  },
};

export default api;
