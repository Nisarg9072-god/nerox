import { motion } from 'motion/react';
import { Search, Calendar, AlertCircle, ExternalLink, RefreshCw, Upload as UploadIcon } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Input } from '../../components/ui/input';
import { Badge } from '../../components/ui/badge';
import { Button } from '../../components/ui/button';
import { Progress } from '../../components/ui/progress';
import { useEffect, useState } from 'react';
import { analyticsService, type DashboardResponse } from '../../../services/analyticsService';
import { detectService, type DetectionResponse, type DetectionMatch } from '../../../services/detectService';
import { toast } from 'sonner';

const RISK_BADGE: Record<string, 'destructive' | 'default' | 'secondary' | 'outline'> = {
  critical: 'destructive',
  high:     'destructive',
  medium:   'default',
  low:      'secondary',
};

export default function Detections() {
  const [dash,      setDash]      = useState<DashboardResponse | null>(null);
  const [loading,   setLoading]   = useState(true);
  const [searchTerm, setSearchTerm] = useState('');

  // File-based detection
  const [detectFile,     setDetectFile]     = useState<File | null>(null);
  const [detecting,      setDetecting]      = useState(false);
  const [detectResult,   setDetectResult]   = useState<DetectionResponse | null>(null);

  const load = () => {
    setLoading(true);
    analyticsService.getDashboard()
      .then(d => setDash(d))
      .catch(() => toast.error('Failed to load detections.'))
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  const handleDetectFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (!f) return;
    setDetectFile(f);
    setDetecting(true);
    setDetectResult(null);
    try {
      const result = await detectService.detectByFile(f, 10);
      setDetectResult(result);
      if (result.total_matches > 0) {
        toast.success(`Found ${result.total_matches} similar asset(s) in your library`);
        load(); // refresh dashboard stats
      } else {
        toast.info('No similar content found.');
      }
    } catch (err: any) {
      toast.error(err?.response?.data?.error || 'Detection failed.');
    } finally {
      setDetecting(false);
      e.target.value = '';
    }
  };

  const recentDetections = dash?.recent_detections ?? [];
  const rs = dash?.overview;

  const filtered = recentDetections.filter(d =>
    d.platform_name.toLowerCase().includes(searchTerm.toLowerCase()) ||
    d.risk_label.includes(searchTerm.toLowerCase()),
  );

  return (
    <div className="p-6 md:p-8 space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold mb-2">Detection Tracking</h1>
          <p className="text-muted-foreground">Monitor unauthorized usage of your protected assets</p>
        </div>
        <Button variant="outline" onClick={load} disabled={loading}>
          <RefreshCw className={`h-4 w-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </Button>
      </div>

      {/* KPI cards */}
      <div className="grid lg:grid-cols-4 gap-6">
        {[
          { label: 'Total Detections', value: rs?.total_detections ?? '—', class: '' },
          { label: 'Critical Alerts',  value: rs?.critical_alerts  ?? '—', class: 'text-destructive' },
          { label: 'High-Risk Assets', value: rs?.high_risk_assets ?? '—', class: 'text-orange-500' },
          { label: 'WM Verified',      value: rs?.watermark_verifications ?? '—', class: 'text-green-600' },
        ].map((s, i) => (
          <Card key={i}>
            <CardContent className="p-6">
              <div className="text-sm text-muted-foreground mb-1">{s.label}</div>
              <div className={`text-3xl font-bold ${loading ? 'opacity-40' : ''} ${s.class}`}>
                {loading ? '…' : s.value}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Run new detection */}
      <Card>
        <CardHeader>
          <CardTitle>Run Similarity Detection</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center gap-4 flex-wrap">
            <label>
              <input
                type="file"
                accept="image/jpeg,image/png,video/mp4,video/quicktime"
                className="hidden"
                onChange={handleDetectFile}
                disabled={detecting}
              />
              <Button asChild variant="outline" disabled={detecting}>
                <span>
                  <UploadIcon className="h-4 w-4 mr-2" />
                  {detecting ? 'Detecting…' : 'Upload file to detect'}
                </span>
              </Button>
            </label>
            {detectFile && !detecting && (
              <span className="text-sm text-muted-foreground">{detectFile.name}</span>
            )}
          </div>

          {detectResult && (
            <div className="mt-4 p-4 rounded-lg border border-border">
              <div className="font-semibold mb-3">
                {detectResult.total_matches} similar asset{detectResult.total_matches !== 1 ? 's' : ''} found
              </div>
              {detectResult.matches.length > 0 && (
                <div className="space-y-2">
                  {detectResult.matches.map((m, i) => (
                    <div key={i} className="flex items-center justify-between text-sm p-2 rounded bg-muted/50">
                      <span className="font-mono text-xs">{m.asset_id.slice(-12)}</span>
                      <span className="text-muted-foreground">{m.filename}</span>
                      <Badge variant={m.match_strength === 'strong' ? 'destructive' : 'default'}>
                        {Math.round(m.similarity * 100)}% — {m.match_strength}
                      </Badge>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Search recent */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
        <Input
          placeholder="Filter by platform or risk level…"
          className="pl-10"
          value={searchTerm}
          onChange={e => setSearchTerm(e.target.value)}
        />
      </div>

      {/* Recent detections */}
      <div className="grid gap-4">
        {loading ? (
          Array.from({ length: 4 }).map((_, i) => (
            <Card key={i}>
              <CardContent className="p-6">
                <div className="h-16 bg-muted/30 rounded animate-pulse" />
              </CardContent>
            </Card>
          ))
        ) : filtered.length === 0 ? (
          <Card>
            <CardContent className="p-12 text-center text-muted-foreground">
              {recentDetections.length === 0
                ? 'No detections yet. Upload assets and run a similarity scan above.'
                : 'No detections match your filter.'}
            </CardContent>
          </Card>
        ) : (
          filtered.map((d, i) => (
            <motion.div
              key={d.detection_id}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.04 }}
            >
              <Card className="hover:border-primary/50 transition-all">
                <CardContent className="p-6">
                  <div className="flex flex-col lg:flex-row lg:items-center gap-6">
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-2 flex-wrap">
                        <h3 className="font-semibold capitalize">
                          {d.platform_name}
                        </h3>
                        <Badge variant={RISK_BADGE[d.risk_label] ?? 'secondary'}>
                          {d.risk_label} risk
                        </Badge>
                        {d.watermark_verified && (
                          <Badge variant="outline" className="text-green-600 border-green-500">
                            WM Verified
                          </Badge>
                        )}
                      </div>
                      <div className="flex flex-wrap items-center gap-4 text-sm text-muted-foreground">
                        <div className="flex items-center gap-1">
                          <Calendar className="h-4 w-4" />
                          {new Date(d.detected_at).toLocaleString()}
                        </div>
                        <div>Asset: {d.asset_id.slice(-8).toUpperCase()}</div>
                      </div>
                    </div>

                    <div className="flex flex-col md:flex-row items-start md:items-center gap-6">
                      <div className="w-full md:w-36">
                        <div className="text-sm text-muted-foreground mb-2">Risk Score</div>
                        <Progress
                          value={d.risk_score}
                          className="h-2"
                        />
                        <div className="text-xs text-muted-foreground mt-1">{d.risk_score}/100</div>
                      </div>
                      <div className="w-full md:w-32">
                        <div className="text-sm text-muted-foreground mb-2">Similarity</div>
                        <Progress
                          value={Math.round(d.similarity_score * 100)}
                          className="h-2"
                        />
                        <div className="text-xs text-muted-foreground mt-1">
                          {Math.round(d.similarity_score * 100)}%
                        </div>
                      </div>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </motion.div>
          ))
        )}
      </div>
    </div>
  );
}
