/**
 * src/services/analyticsService.ts
 * =================================
 * Analytics + Alerts API wrapper — maps to:
 *   GET  /analytics/dashboard
 *   GET  /analytics/assets/high-risk
 *   GET  /analytics/timeline
 *   GET  /analytics/platforms
 *   GET  /analytics/alerts
 *   POST /analytics/alerts/{id}/resolve
 */

import api from './api';

// ── Response types (mirror backend analytics_schema.py) ──────────────────────

export interface OverviewStats {
  total_assets: number;
  total_detections: number;
  high_risk_assets: number;
  critical_alerts: number;
  watermark_verifications: number;
  detection_rate: number;
}

export interface RiskSummary {
  low: number;
  medium: number;
  high: number;
  critical: number;
}

export interface PlatformStat {
  platform: string;
  count: number;
  percentage: number;
}

export interface TrendPoint {
  date: string;
  count: number;
}

export interface RecentDetection {
  detection_id: string;
  asset_id: string;
  platform_name: string;
  similarity_score: number;
  risk_score: number;
  risk_label: string;
  watermark_verified: boolean;
  detected_at: string;
}

export interface TopSource {
  source_url: string;
  detection_count: number;
  avg_risk_score: number;
}

export interface DashboardResponse {
  generated_at: string;
  overview: OverviewStats;
  risk_summary: RiskSummary;
  platform_distribution: PlatformStat[];
  recent_detections: RecentDetection[];
  trend_last_30_days: TrendPoint[];
  top_suspicious_sources: TopSource[];
}

export interface HighRiskAsset {
  asset_id: string;
  original_filename: string;
  file_type: string;
  max_risk_score: number;
  avg_risk_score: number;
  detection_count: number;
  watermark_hits: number;
  platforms: string[];
  last_detected_at?: string;
  recommendation: string;
}

export interface HighRiskResponse {
  total: number;
  assets: HighRiskAsset[];
}

export interface TimelinePoint {
  period: string;
  count: number;
  avg_risk: number;
  platforms: string[];
}

export interface TimelineResponse {
  period_type: string;
  days: number;
  total: number;
  points: TimelinePoint[];
}

export interface PlatformDetail {
  platform: string;
  detection_count: number;
  percentage: number;
  avg_similarity: number;
  avg_risk_score: number;
  watermark_hits: number;
  severity: string;
}

export interface PlatformsResponse {
  total_detections: number;
  platforms: PlatformDetail[];
}

export interface AlertItem {
  alert_id: string;
  alert_type: string;
  asset_id: string;
  severity: string;
  message: string;
  resolved: boolean;
  triggered_at: string;
  resolved_at?: string;
}

export interface AlertListResponse {
  total: number;
  alerts: AlertItem[];
}

// ── Service ──────────────────────────────────────────────────────────────────

export const analyticsService = {
  /** Full dashboard payload — overview + risk + platforms + trend + recent. */
  async getDashboard(): Promise<DashboardResponse> {
    const { data } = await api.get<DashboardResponse>('/analytics/dashboard');
    return data;
  },

  /** Top assets ranked by maximum risk score. */
  async getHighRiskAssets(limit = 20): Promise<HighRiskResponse> {
    const { data } = await api.get<HighRiskResponse>(
      `/analytics/assets/high-risk?limit=${limit}`,
    );
    return data;
  },

  /** Detection counts grouped by day or week. */
  async getTimeline(period: 'day' | 'week' = 'day', days = 30): Promise<TimelineResponse> {
    const { data } = await api.get<TimelineResponse>(
      `/analytics/timeline?period=${period}&days=${days}`,
    );
    return data;
  },

  /** Per-platform detection breakdown. */
  async getPlatforms(): Promise<PlatformsResponse> {
    const { data } = await api.get<PlatformsResponse>('/analytics/platforms');
    return data;
  },

  /** Active (unresolved) alerts for the current user. */
  async getAlerts(limit = 50): Promise<AlertListResponse> {
    const { data } = await api.get<AlertListResponse>(
      `/analytics/alerts?limit=${limit}`,
    );
    return data;
  },

  /** Mark an alert as resolved / dismissed. */
  async resolveAlert(alertId: string): Promise<{ message: string; alert_id: string }> {
    const { data } = await api.post(`/analytics/alerts/${alertId}/resolve`);
    return data;
  },
};
