/**
 * src/services/watermarkService.ts
 * =================================
 * Watermark API wrapper — maps to:
 *   POST /watermark/verify
 */

import api from './api';

export interface OwnershipMatch {
  asset_id: string;
  user_id: string;
  watermark_id: string;
}

export interface VerifyResponse {
  verified: boolean;
  confidence: number;
  confidence_label: string;
  ownership?: OwnershipMatch;
  wm_token_detected?: string;
  watermark_method: string;
  error?: string;
}

export const watermarkService = {
  /**
   * Upload a suspicious file to extract its DCT watermark and look up
   * the original owner in the Nerox database.
   */
  async verify(file: File): Promise<VerifyResponse> {
    const form = new FormData();
    form.append('file', file);
    const { data } = await api.post<VerifyResponse>('/watermark/verify', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return data;
  },
};
