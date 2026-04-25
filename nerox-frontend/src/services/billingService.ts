import api from './api';

export const billingService = {
  async createCheckout(plan: 'pro' | 'enterprise'): Promise<{ plan: string; checkout_url: string; session_id: string }> {
    const { data } = await api.post('/billing/checkout', { plan });
    return data;
  },
};
