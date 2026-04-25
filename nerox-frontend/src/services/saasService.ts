import api from './api';

export interface UsageResponse {
  organization_id: string;
  plan: 'free' | 'pro' | 'enterprise';
  scans_used: number;
  scans_limit: number | null;
  uploads_used: number;
  uploads_limit: number | null;
  last_reset: string;
}

export const saasService = {
  async getUsage(): Promise<UsageResponse> {
    const { data } = await api.get<UsageResponse>('/usage');
    return data;
  },
  async createApiKey(): Promise<{ key: string; created_at: string; active: boolean }> {
    const { data } = await api.post('/api-keys/create');
    return data;
  },
};
