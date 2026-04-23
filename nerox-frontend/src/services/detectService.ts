/**
 * src/services/detectService.ts
 * ==============================
 * Detection API wrapper — maps to:
 *   POST /detect  (file mode or asset_id mode)
 */

import api from './api';

export interface DetectionMatch {
  asset_id: string;
  user_id: string;
  filename: string;
  similarity: number;
  match_strength: string;
}

export interface DetectionResponse {
  query_asset_id?: string;
  total_matches: number;
  matches: DetectionMatch[];
}

export const detectService = {
  /** Upload a file and search for visually similar content in the FAISS index. */
  async detectByFile(file: File, topK = 5): Promise<DetectionResponse> {
    const form = new FormData();
    form.append('file', file);
    form.append('top_k', String(topK));
    const { data } = await api.post<DetectionResponse>('/detect', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return data;
  },

  /** Search by existing asset ID (uses stored embedding). */
  async detectByAssetId(assetId: string, topK = 5): Promise<DetectionResponse> {
    const form = new FormData();
    form.append('asset_id', assetId);
    form.append('top_k', String(topK));
    const { data } = await api.post<DetectionResponse>('/detect', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return data;
  },
};
