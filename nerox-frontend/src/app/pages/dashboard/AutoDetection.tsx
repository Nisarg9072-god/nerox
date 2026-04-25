/**
 * src/app/pages/dashboard/AutoDetection.tsx
 * ============================================
 * Phase 2.5: Auto-Detection Dashboard Page
 *
 * Features:
 *   - Start new scan (YouTube or Web)
 *   - Job list with real-time progress
 *   - Job detail view with match results table
 *   - Auto-polling every 5s for running jobs
 *   - Progress bars, loading states, animations
 */

import { useEffect, useState, useCallback, useRef } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import {
  Radar,
  Play,
  RefreshCw,
  Clock,
  CheckCircle2,
  XCircle,
  Loader2,
  Globe,
  Youtube,
  ExternalLink,
  ChevronDown,
  ChevronUp,
  Search,
  Zap,
  Target,
  Activity,
  AlertTriangle,
  Wifi,
  WifiOff,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Badge } from '../../components/ui/badge';
import { Progress } from '../../components/ui/progress';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../../components/ui/select';
import { toast } from 'sonner';
import {
  autoDetectService,
  type DetectionJobItem,
  type DetectionJobDetailResponse,
  type DetectionJobMatchResult,
} from '../../../services/autoDetectService';
import { useWebSocket, useWsEvent } from '../../../context/WebSocketContext';
import type { WsEvent } from '../../../services/wsService';

// ---------------------------------------------------------------------------
// Status helpers
// ---------------------------------------------------------------------------

const STATUS_CONFIG: Record<string, {
  label: string;
  variant: 'default' | 'secondary' | 'destructive' | 'outline';
  icon: React.ElementType;
  color: string;
}> = {
  pending:   { label: 'Pending',   variant: 'secondary',    icon: Clock,        color: 'text-yellow-500' },
  running:   { label: 'Running',   variant: 'default',      icon: Loader2,      color: 'text-blue-500' },
  completed: { label: 'Completed', variant: 'outline',      icon: CheckCircle2, color: 'text-green-500' },
  failed:    { label: 'Failed',    variant: 'destructive',  icon: XCircle,      color: 'text-red-500' },
};

const SOURCE_ICON: Record<string, React.ElementType> = {
  youtube: Youtube,
  web:     Globe,
};

function formatTime(iso: string | null): string {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

function timeSince(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function AutoDetection() {
  // ── State ─────────────────────────────────────────────────────────────────
  const [jobs, setJobs] = useState<DetectionJobItem[]>([]);
  const [totalJobs, setTotalJobs] = useState(0);
  const [loading, setLoading] = useState(true);
  const [starting, setStarting] = useState(false);

  // New scan form
  const [source, setSource] = useState<'youtube' | 'web'>('youtube');
  const [query, setQuery] = useState('');

  // Expanded job detail
  const [expandedJobId, setExpandedJobId] = useState<string | null>(null);
  const [jobDetail, setJobDetail] = useState<DetectionJobDetailResponse | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);

  // WebSocket integration
  const { connected: wsConnected, wsStatus } = useWebSocket();

  // Polling ref (fallback when WS not connected)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // ── Load jobs ─────────────────────────────────────────────────────────────
  const loadJobs = useCallback(async () => {
    try {
      const res = await autoDetectService.getDetectionJobs(50);
      setJobs(res.jobs);
      setTotalJobs(res.total);
    } catch {
      // Silent on poll errors
    } finally {
      setLoading(false);
    }
  }, []);

  // ── WebSocket events update jobs in real-time ────────────────────────────
  const handleWsJobEvent = useCallback((event: WsEvent) => {
    const payload = event.data || {};
    const jobId = String(payload.job_id || '');
    if (!jobId) return;

    if (event.type === 'job_progress' || event.type === 'job_completed' || event.type === 'job_failed') {
      setJobs((prev) => {
        const idx = prev.findIndex((j) => j.job_id === jobId);
        if (idx === -1) return prev;
        const next = [...prev];
        next[idx] = {
          ...next[idx],
          status: String(payload.status || next[idx].status) as DetectionJobItem['status'],
          total_scanned: Number(payload.total_scanned ?? next[idx].total_scanned),
          matches_found: Number(payload.matches_found ?? next[idx].matches_found),
          error: event.type === 'job_failed' ? String(payload.reason || 'Job failed') : next[idx].error,
          completed_at: event.type === 'job_completed' || event.type === 'job_failed'
            ? new Date().toISOString()
            : next[idx].completed_at,
        };
        return next;
      });

      if (expandedJobId && jobId === expandedJobId && jobDetail) {
        setJobDetail((prev) => prev ? {
          ...prev,
          status: String(payload.status || prev.status) as DetectionJobDetailResponse['status'],
          total_scanned: Number(payload.total_scanned ?? prev.total_scanned),
          matches_found: Number(payload.matches_found ?? prev.matches_found),
          error: event.type === 'job_failed' ? String(payload.reason || 'Job failed') : prev.error,
          results: Array.isArray(payload.top_matches) ? payload.top_matches as DetectionJobMatchResult[] : prev.results,
        } : prev);
      }
    }
  }, [expandedJobId, jobDetail]);

  useWsEvent('job_progress', handleWsJobEvent);
  useWsEvent('job_completed', handleWsJobEvent);
  useWsEvent('job_failed', handleWsJobEvent);

  // ── Fallback polling (reduced frequency when WS connected) ────────────────
  useEffect(() => {
    loadJobs();

    // Poll only as fallback when WebSocket is disconnected.
    if (wsConnected) return;
    const interval = 5000;
    pollRef.current = setInterval(() => {
      loadJobs();
      if (expandedJobId) {
        autoDetectService.getDetectionJob(expandedJobId)
          .then(setJobDetail)
          .catch(() => {});
      }
    }, interval);

    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [loadJobs, expandedJobId, wsConnected]);

  // ── Start scan ────────────────────────────────────────────────────────────
  const handleStartScan = async () => {
    if (!query.trim()) {
      toast.error('Please enter a search query or URL.');
      return;
    }
    if (source === 'web' && !query.startsWith('http')) {
      toast.error('Web source requires a full URL (starting with http).');
      return;
    }

    setStarting(true);
    try {
      const res = await autoDetectService.startAutoDetection({ source, query: query.trim() });
      toast.success(res.message);
      setQuery('');
      await loadJobs();
    } catch (err: any) {
      toast.error(err?.response?.data?.error || 'Failed to start detection job.');
    } finally {
      setStarting(false);
    }
  };

  // ── Expand/collapse job detail ────────────────────────────────────────────
  const toggleJobDetail = async (jobId: string) => {
    if (expandedJobId === jobId) {
      setExpandedJobId(null);
      setJobDetail(null);
      return;
    }

    setExpandedJobId(jobId);
    setLoadingDetail(true);
    try {
      const detail = await autoDetectService.getDetectionJob(jobId);
      setJobDetail(detail);
    } catch {
      toast.error('Failed to load job details.');
    } finally {
      setLoadingDetail(false);
    }
  };

  // ── Stats ─────────────────────────────────────────────────────────────────
  const runningJobs = jobs.filter(j => j.status === 'running').length;
  const completedJobs = jobs.filter(j => j.status === 'completed').length;
  const totalMatches = jobs.reduce((acc, j) => acc + j.matches_found, 0);
  const totalScanned = jobs.reduce((acc, j) => acc + j.total_scanned, 0);

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div className="p-4 sm:p-6 md:p-8 space-y-6 md:space-y-8">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold mb-1 flex items-center gap-2">
            <Radar className="h-6 w-6 sm:h-8 sm:w-8 text-primary shrink-0" />
            Auto Detection
          </h1>
          <p className="text-sm sm:text-base text-muted-foreground">
            Automatically scan external sources for unauthorized use of your assets
          </p>
        </div>
        <div className="flex items-center gap-2 self-start sm:self-auto">
          {wsConnected ? (
            <Badge variant="outline" className="gap-1.5 text-green-600 border-green-500/50">
              <Wifi className="h-3 w-3" />
              Live
            </Badge>
          ) : (
            <Badge variant="outline" className="gap-1.5 text-muted-foreground">
              <WifiOff className="h-3 w-3" />
              {wsStatus === 'reconnecting' ? 'Reconnecting' : wsStatus === 'connecting' ? 'Connecting' : 'Polling'}
            </Badge>
          )}
          <Button variant="outline" size="sm" onClick={loadJobs} disabled={loading}>
            <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''} sm:mr-2`} />
            <span className="hidden sm:inline">Refresh</span>
          </Button>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
        {[
          {
            label: 'Active Scans',
            value: runningJobs,
            icon: Activity,
            gradient: 'from-blue-500/10 to-cyan-500/10',
            iconColor: 'text-blue-500',
          },
          {
            label: 'Completed Scans',
            value: completedJobs,
            icon: CheckCircle2,
            gradient: 'from-green-500/10 to-emerald-500/10',
            iconColor: 'text-green-500',
          },
          {
            label: 'Total Scanned',
            value: totalScanned,
            icon: Target,
            gradient: 'from-purple-500/10 to-violet-500/10',
            iconColor: 'text-purple-500',
          },
          {
            label: 'Matches Found',
            value: totalMatches,
            icon: AlertTriangle,
            gradient: 'from-orange-500/10 to-amber-500/10',
            iconColor: totalMatches > 0 ? 'text-orange-500' : 'text-muted-foreground',
          },
        ].map((stat, i) => (
          <motion.div
            key={stat.label}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.08 }}
          >
            <Card className={`bg-gradient-to-br ${stat.gradient} border-0`}>
              <CardContent className="p-5">
                <div className="flex items-center justify-between mb-3">
                  <stat.icon className={`h-5 w-5 ${stat.iconColor}`} />
                </div>
                <div className={`text-3xl font-bold ${loading ? 'opacity-40' : ''}`}>
                  {loading ? '…' : stat.value}
                </div>
                <div className="text-sm text-muted-foreground mt-1">{stat.label}</div>
              </CardContent>
            </Card>
          </motion.div>
        ))}
      </div>

      {/* Start New Scan */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.3 }}
      >
        <Card className="border-primary/20 overflow-hidden">
          <div className="h-1 bg-gradient-to-r from-primary via-blue-500 to-cyan-500" />
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Zap className="h-5 w-5 text-primary" />
              Start New Detection Scan
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-col gap-3">
              <div className="flex flex-col sm:flex-row items-stretch sm:items-end gap-3">
                <div className="w-full sm:w-44 shrink-0">
                  <label className="text-sm font-medium text-muted-foreground mb-2 block">
                    Source
                  </label>
                  <Select
                    value={source}
                    onValueChange={(v) => setSource(v as 'youtube' | 'web')}
                  >
                    <SelectTrigger id="auto-detect-source">
                      <SelectValue placeholder="Select source" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="youtube">
                        <div className="flex items-center gap-2">
                          <Youtube className="h-4 w-4 text-red-500" />
                          YouTube
                        </div>
                      </SelectItem>
                      <SelectItem value="web">
                        <div className="flex items-center gap-2">
                          <Globe className="h-4 w-4 text-blue-500" />
                          Web Scraper
                        </div>
                      </SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <div className="flex-1">
                  <label className="text-sm font-medium text-muted-foreground mb-2 block">
                    {source === 'youtube' ? 'Search Keywords' : 'Page URL'}
                  </label>
                  <div className="relative">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                    <Input
                      id="auto-detect-query"
                      className="pl-10"
                      placeholder={
                        source === 'youtube'
                          ? 'e.g., digital art, photography…'
                          : 'https://example.com/gallery'
                      }
                      value={query}
                      onChange={(e) => setQuery(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && handleStartScan()}
                      disabled={starting}
                    />
                  </div>
                </div>

                <Button
                  id="auto-detect-start-btn"
                  onClick={handleStartScan}
                  disabled={starting || !query.trim()}
                  className="h-10 px-6 gap-2 w-full sm:w-auto shrink-0"
                >
                  {starting ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin" />
                      Starting…
                    </>
                  ) : (
                    <>
                      <Play className="h-4 w-4" />
                      Start Scan
                    </>
                  )}
                </Button>
              </div>

              <p className="text-xs text-muted-foreground">
                {source === 'youtube'
                  ? 'Searches YouTube for videos matching your keywords and compares thumbnails against your protected assets.'
                  : 'Scrapes images from the given URL and compares them against your protected assets.'}
              </p>
            </div>
          </CardContent>
        </Card>
      </motion.div>

      {/* Job List */}
      <div className="space-y-3">
        <h2 className="text-xl font-semibold flex items-center gap-2">
          <Clock className="h-5 w-5 text-muted-foreground" />
          Detection Jobs
          {totalJobs > 0 && (
            <Badge variant="secondary" className="ml-2">{totalJobs}</Badge>
          )}
        </h2>

        {loading ? (
          <div className="space-y-3">
            {Array.from({ length: 3 }).map((_, i) => (
              <Card key={i}>
                <CardContent className="p-6">
                  <div className="h-16 bg-muted/30 rounded animate-pulse" />
                </CardContent>
              </Card>
            ))}
          </div>
        ) : jobs.length === 0 ? (
          <Card>
            <CardContent className="p-12 text-center">
              <Radar className="h-12 w-12 mx-auto text-muted-foreground/40 mb-4" />
              <p className="text-muted-foreground text-lg">No detection jobs yet</p>
              <p className="text-sm text-muted-foreground mt-1">
                Start a scan above to automatically detect misuse of your assets.
              </p>
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-3">
            <AnimatePresence mode="popLayout">
              {jobs.map((job, i) => {
                const cfg = STATUS_CONFIG[job.status] || STATUS_CONFIG.pending;
                const StatusIcon = cfg.icon;
                const SourceIcon = SOURCE_ICON[job.source] || Globe;
                const isExpanded = expandedJobId === job.job_id;
                const isRunning = job.status === 'running';

                return (
                  <motion.div
                    key={job.job_id}
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, scale: 0.95 }}
                    transition={{ delay: i * 0.04 }}
                    layout
                  >
                    <Card
                      className={`transition-all cursor-pointer hover:border-primary/40 ${
                        isExpanded ? 'border-primary/50 shadow-lg shadow-primary/5' : ''
                      } ${isRunning ? 'border-blue-500/30' : ''}`}
                      onClick={() => toggleJobDetail(job.job_id)}
                    >
                      <CardContent className="p-5">
                        {/* Job header row */}
                        <div className="flex items-center gap-4">
                          {/* Source icon */}
                          <div className={`p-2.5 rounded-lg bg-muted/50 ${cfg.color}`}>
                            <SourceIcon className="h-5 w-5" />
                          </div>

                          {/* Main info */}
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 flex-wrap mb-1">
                              <span className="font-semibold truncate max-w-[180px] sm:max-w-[280px] text-sm sm:text-base">
                                {job.query}
                              </span>
                              <Badge variant={cfg.variant} className="gap-1 text-xs">
                                <StatusIcon className={`h-3 w-3 ${isRunning ? 'animate-spin' : ''}`} />
                                {cfg.label}
                              </Badge>
                              <Badge variant="outline" className="capitalize text-xs">
                                {job.source}
                              </Badge>
                            </div>
                            <div className="flex flex-wrap items-center gap-2 sm:gap-4 text-xs text-muted-foreground">
                              <span>{timeSince(job.created_at)}</span>
                              <span>Scanned: {job.total_scanned}</span>
                              {job.matches_found > 0 && (
                                <span className="text-orange-500 font-medium">
                                  {job.matches_found} match{job.matches_found !== 1 ? 'es' : ''}
                                </span>
                              )}
                            </div>
                          </div>

                          {/* Progress indicator for running jobs */}
                          {isRunning && (
                            <div className="w-24 hidden sm:block">
                              <Progress value={job.total_scanned * 3.3} className="h-1.5" />
                              <div className="text-[10px] text-muted-foreground text-center mt-1">
                                scanning…
                              </div>
                            </div>
                          )}

                          {/* Expand toggle */}
                          <div className="p-1">
                            {isExpanded ? (
                              <ChevronUp className="h-4 w-4 text-muted-foreground" />
                            ) : (
                              <ChevronDown className="h-4 w-4 text-muted-foreground" />
                            )}
                          </div>
                        </div>

                        {/* Running progress bar (mobile) */}
                        {isRunning && (
                          <div className="mt-3 sm:hidden">
                            <Progress value={job.total_scanned * 3.3} className="h-1.5" />
                          </div>
                        )}

                        {/* Expanded detail */}
                        <AnimatePresence>
                          {isExpanded && (
                            <motion.div
                              initial={{ height: 0, opacity: 0 }}
                              animate={{ height: 'auto', opacity: 1 }}
                              exit={{ height: 0, opacity: 0 }}
                              transition={{ duration: 0.2 }}
                              className="overflow-hidden"
                              onClick={(e) => e.stopPropagation()}
                            >
                              <div className="mt-4 pt-4 border-t border-border">
                                {loadingDetail ? (
                                  <div className="flex items-center justify-center py-6">
                                    <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                                    <span className="ml-2 text-sm text-muted-foreground">Loading details…</span>
                                  </div>
                                ) : jobDetail ? (
                                  <div className="space-y-4">
                                    {/* Detail stats */}
                                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                                      <div className="p-3 rounded-lg bg-muted/30">
                                        <div className="text-xs text-muted-foreground">Total Scanned</div>
                                        <div className="text-lg font-bold">{jobDetail.total_scanned}</div>
                                      </div>
                                      <div className="p-3 rounded-lg bg-muted/30">
                                        <div className="text-xs text-muted-foreground">Matches Found</div>
                                        <div className={`text-lg font-bold ${jobDetail.matches_found > 0 ? 'text-orange-500' : ''}`}>
                                          {jobDetail.matches_found}
                                        </div>
                                      </div>
                                      <div className="p-3 rounded-lg bg-muted/30">
                                        <div className="text-xs text-muted-foreground">Started</div>
                                        <div className="text-sm font-medium">{formatTime(jobDetail.started_at)}</div>
                                      </div>
                                      <div className="p-3 rounded-lg bg-muted/30">
                                        <div className="text-xs text-muted-foreground">Completed</div>
                                        <div className="text-sm font-medium">{formatTime(jobDetail.completed_at)}</div>
                                      </div>
                                    </div>

                                    {/* Error display */}
                                    {jobDetail.error && (
                                      <div className="p-3 rounded-lg bg-destructive/10 border border-destructive/20 text-sm text-destructive">
                                        <span className="font-medium">Error:</span> {jobDetail.error}
                                      </div>
                                    )}

                                    {/* Match results table */}
                                    {jobDetail.results.length > 0 && (
                                      <div>
                                        <h4 className="text-sm font-semibold mb-2">Match Results</h4>
                                        <div className="rounded-lg border border-border overflow-hidden">
                                          <div className="overflow-x-auto">
                                            <table className="w-full text-sm">
                                              <thead>
                                                <tr className="bg-muted/40 border-b border-border">
                                                  <th className="text-left p-3 font-medium">Source</th>
                                                  <th className="text-left p-3 font-medium">Asset</th>
                                                  <th className="text-left p-3 font-medium">Similarity</th>
                                                  <th className="text-left p-3 font-medium">Strength</th>
                                                  <th className="text-left p-3 font-medium">Platform</th>
                                                  <th className="text-left p-3 font-medium">Link</th>
                                                </tr>
                                              </thead>
                                              <tbody>
                                                {jobDetail.results.map((r, ri) => (
                                                  <tr
                                                    key={ri}
                                                    className="border-b border-border/50 hover:bg-muted/20 transition-colors"
                                                  >
                                                    <td className="p-3 max-w-[200px] truncate" title={r.source_title}>
                                                      {r.source_title || r.source_url.split('/').pop() || '—'}
                                                    </td>
                                                    <td className="p-3">
                                                      <span className="font-mono text-xs">
                                                        {r.asset_filename || r.asset_id.slice(-8).toUpperCase()}
                                                      </span>
                                                    </td>
                                                    <td className="p-3">
                                                      <div className="flex items-center gap-2">
                                                        <Progress
                                                          value={Math.round(r.similarity * 100)}
                                                          className="h-1.5 w-16"
                                                        />
                                                        <span className="text-xs font-medium">
                                                          {Math.round(r.similarity * 100)}%
                                                        </span>
                                                      </div>
                                                    </td>
                                                    <td className="p-3">
                                                      <Badge
                                                        variant={r.match_strength === 'strong' ? 'destructive' : 'default'}
                                                      >
                                                        {r.match_strength}
                                                      </Badge>
                                                    </td>
                                                    <td className="p-3 capitalize">{r.platform}</td>
                                                    <td className="p-3">
                                                      {r.source_url && (
                                                        <a
                                                          href={r.source_url}
                                                          target="_blank"
                                                          rel="noopener noreferrer"
                                                          className="text-primary hover:underline inline-flex items-center gap-1"
                                                        >
                                                          <ExternalLink className="h-3 w-3" />
                                                          View
                                                        </a>
                                                      )}
                                                    </td>
                                                  </tr>
                                                ))}
                                              </tbody>
                                            </table>
                                          </div>
                                        </div>
                                      </div>
                                    )}

                                    {/* No matches */}
                                    {jobDetail.status === 'completed' && jobDetail.results.length === 0 && (
                                      <div className="text-center py-6 text-muted-foreground">
                                        <CheckCircle2 className="h-8 w-8 mx-auto mb-2 text-green-500" />
                                        <p>No matches found — your assets appear safe on this scan.</p>
                                      </div>
                                    )}
                                  </div>
                                ) : null}
                              </div>
                            </motion.div>
                          )}
                        </AnimatePresence>
                      </CardContent>
                    </Card>
                  </motion.div>
                );
              })}
            </AnimatePresence>
          </div>
        )}
      </div>
    </div>
  );
}
