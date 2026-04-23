/**
 * src/services/assetService.ts
 * ============================
 * Asset API wrapper — maps to:
 *   POST /assets/upload
 *   GET  /assets
 *   GET  /assets/{id}
 *   GET  /assets/{id}/fingerprint-status
 *   GET  /assets/{id}/watermark-status
 */

import api from './api';

// ── Response types ────────────────────────────────────────────────────────────

export interface AssetUploadResponse {
  asset_id: string;
  fingerprint_id: string;
  watermark_id: string;
  status: string;
  message: string;
}

export interface AssetItem {
  asset_id: string;
  filename: string;
  original_filename: string;
  file_type: string;
  file_size: number;
  status: string;
  has_fingerprint: boolean;
  fingerprint_dim?: number;
  fingerprint_id?: string;
  watermark_id?: string;
  processed_at?: string;
  created_at: string;
  file_url?: string;
}

export interface AssetListResponse {
  total: number;
  assets: AssetItem[];
}

export interface FingerprintStatus {
  fingerprint_id: string;
  asset_id: string;
  processing_status: string;
  created_at: string;
  completed_at?: string;
  processing_duration_ms?: number;
  error_message?: string;
}

export interface WatermarkStatus {
  watermark_id: string;
  asset_id: string;
  status: string;
  watermark_method: string;
  has_token: boolean;
  processing_duration_ms?: number;
  completed_at?: string;
  verification_count: number;
  last_verified_at?: string;
  error_message?: string;
}

// ── Service ──────────────────────────────────────────────────────────────────

export const assetService = {
  /**
   * Upload a file. Reports real upload progress via the onProgress callback.
   * Returns immediately with asset_id — fingerprinting and watermarking run in background.
   */
  async upload(
    file: File,
    onProgress?: (pct: number) => void,
  ): Promise<AssetUploadResponse> {
    const form = new FormData();
    form.append('file', file);

    const { data } = await api.post<AssetUploadResponse>('/assets/upload', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress: (evt) => {
        if (onProgress && evt.total) {
          onProgress(Math.round((evt.loaded * 100) / evt.total));
        }
      },
    });
    return data;
  },

  /** List assets owned by the current user. */
  async list(skip = 0, limit = 50): Promise<AssetListResponse> {
    const { data } = await api.get<AssetListResponse>(
      `/assets?skip=${skip}&limit=${limit}`,
    );
    return data;
  },

  /** Get full details for a single asset. */
  async getById(assetId: string): Promise<AssetItem> {
    const { data } = await api.get<AssetItem>(`/assets/${assetId}`);
    return data;
  },

  /** Poll this endpoint until processing_status === 'completed'. */
  async getFingerprintStatus(assetId: string): Promise<FingerprintStatus> {
    const { data } = await api.get<FingerprintStatus>(
      `/assets/${assetId}/fingerprint-status`,
    );
    return data;
  },

  /** Poll this endpoint until status === 'completed'. */
  async getWatermarkStatus(assetId: string): Promise<WatermarkStatus> {
    const { data } = await api.get<WatermarkStatus>(
      `/assets/${assetId}/watermark-status`,
    );
    return data;
  },
};
