/**
 * src/services/autoDetectService.ts
 * ====================================
 * Phase 2.5: Auto-Detection API service layer.
 *
 * Maps to:
 *   POST /detect/auto/start  → startAutoDetection()
 *   GET  /detect/jobs        → getDetectionJobs()
 *   GET  /detect/jobs/{id}   → getDetectionJob()
 */

import api from './api';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface StartAutoDetectRequest {
  source: 'youtube' | 'web';
  query: string;
  asset_ids?: string[];
}

export interface StartAutoDetectResponse {
  job_id: string;
  status: string;
  message: string;
}

export interface DetectionJobMatchResult {
  asset_id: string;
  asset_filename: string;
  similarity: number;
  match_strength: string;
  source_url: string;
  source_title: string;
  platform: string;
  detected_at: string;
}

export interface DetectionJobItem {
  job_id: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  source: string;
  query: string;
  total_scanned: number;
  matches_found: number;
  started_at: string | null;
  completed_at: string | null;
  error: string | null;
  created_at: string;
}

export interface DetectionJobListResponse {
  total: number;
  jobs: DetectionJobItem[];
}

export interface DetectionJobDetailResponse {
  job_id: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  source: string;
  query: string;
  total_scanned: number;
  matches_found: number;
  results: DetectionJobMatchResult[];
  started_at: string | null;
  completed_at: string | null;
  error: string | null;
  created_at: string;
}

// ---------------------------------------------------------------------------
// Service
// ---------------------------------------------------------------------------

export const autoDetectService = {
  /**
   * Start a new auto-detection job.
   * The job runs in the background — poll getDetectionJob() for progress.
   */
  async startAutoDetection(req: StartAutoDetectRequest): Promise<StartAutoDetectResponse> {
    const { data } = await api.post<StartAutoDetectResponse>('/detect/auto/start', req);
    return data;
  },

  /**
   * List all detection jobs for the current user.
   */
  async getDetectionJobs(limit = 20, skip = 0): Promise<DetectionJobListResponse> {
    const { data } = await api.get<DetectionJobListResponse>('/detect/jobs', {
      params: { limit, skip },
    });
    return data;
  },

  /**
   * Get detailed info about a specific detection job, including results.
   */
  async getDetectionJob(jobId: string): Promise<DetectionJobDetailResponse> {
    const { data } = await api.get<DetectionJobDetailResponse>(`/detect/jobs/${jobId}`);
    return data;
  },
};
