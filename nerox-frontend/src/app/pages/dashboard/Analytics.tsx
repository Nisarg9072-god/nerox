import { motion } from 'motion/react';
import { TrendingUp, TrendingDown, BarChart2 } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../../components/ui/card';
import {
  LineChart, Line, BarChart, Bar, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from 'recharts';
import { useEffect, useState } from 'react';
import {
  analyticsService,
  type DashboardResponse,
  type PlatformsResponse,
  type DetectionInsightsResponse,
} from '../../../services/analyticsService';
import { toast } from 'sonner';
import { useWsEvent } from '../../../context/WebSocketContext';

const PIE_COLORS = ['#3b82f6', '#ef4444', '#f59e0b', '#8b5cf6', '#06b6d4', '#6b7280'];

function Skeleton({ h = 300 }: { h?: number }) {
  return <div className={`bg-muted/30 rounded animate-pulse`} style={{ height: h }} />;
}

export default function Analytics() {
  const [dash,     setDash]     = useState<DashboardResponse | null>(null);
  const [platforms, setPlatforms] = useState<PlatformsResponse | null>(null);
  const [insights, setInsights] = useState<DetectionInsightsResponse | null>(null);
  const [loading,  setLoading]  = useState(true);

  useEffect(() => {
    let c = false;
    Promise.all([
      analyticsService.getDashboard(),
      analyticsService.getPlatforms(),
      analyticsService.getDetectionInsights(30),
    ]).then(([d, pl, ins]) => {
      if (c) return;
      setDash(d);
      setPlatforms(pl);
      setInsights(ins);
    }).catch(() => {
      if (!c) toast.error('Failed to load analytics.');
    }).finally(() => { if (!c) setLoading(false); });
    return () => { c = true; };
  }, []);

  useWsEvent('job_completed', () => {
    analyticsService.getDetectionInsights(30).then(setInsights).catch(() => {});
  });

  const ov = dash?.overview;

  const timelineData = (dash?.trend_last_30_days ?? [])
    .filter(t => t.count > 0)
    .map(t => ({ date: t.date.slice(5), count: t.count }));

  const pieData = platforms?.platforms.slice(0, 6).map((p, i) => ({
    name: p.platform.charAt(0).toUpperCase() + p.platform.slice(1),
    value: p.detection_count,
    color: PIE_COLORS[i % PIE_COLORS.length],
  })) ?? [];

  const insightTrend = insights?.daily_trend.map((t) => ({ date: t.date.slice(5), count: t.count })) ?? [];
  const attackedAssets = insights?.top_attacked_assets ?? [];

  return (
    <div className="p-6 md:p-8 space-y-8">
      <div>
        <h1 className="text-3xl font-bold mb-2">Analytics</h1>
        <p className="text-muted-foreground">Comprehensive insights into asset protection and piracy trends</p>
      </div>

      {/* Overview KPIs */}
      <div className="grid md:grid-cols-4 gap-6">
        {loading ? (
          Array.from({ length: 4 }).map((_, i) => (
            <Card key={i}><CardContent className="p-6"><Skeleton h={60} /></CardContent></Card>
          ))
        ) : (
          <>
            <Card><CardContent className="p-6">
              <div className="flex items-center justify-between mb-2">
                <div className="text-sm text-muted-foreground">Total Detections</div>
                <TrendingUp className="h-4 w-4 text-green-500" />
              </div>
              <div className="text-3xl font-bold mb-1">{ov?.total_detections ?? 0}</div>
              <div className="text-xs text-muted-foreground">All-time</div>
            </CardContent></Card>

            <Card><CardContent className="p-6">
              <div className="flex items-center justify-between mb-2">
                <div className="text-sm text-muted-foreground">WM Verifications</div>
                <TrendingUp className="h-4 w-4 text-blue-500" />
              </div>
              <div className="text-3xl font-bold mb-1">{ov?.watermark_verifications ?? 0}</div>
              <div className="text-xs text-muted-foreground">Watermark confirmed</div>
            </CardContent></Card>

            <Card><CardContent className="p-6">
              <div className="flex items-center justify-between mb-2">
                <div className="text-sm text-muted-foreground">High-Risk Assets</div>
                <TrendingDown className="h-4 w-4 text-destructive" />
              </div>
              <div className="text-3xl font-bold mb-1">{ov?.high_risk_assets ?? 0}</div>
              <div className="text-xs text-muted-foreground">Score ≥ 51</div>
            </CardContent></Card>

            <Card><CardContent className="p-6">
              <div className="flex items-center justify-between mb-2">
                <div className="text-sm text-muted-foreground">Detection Rate</div>
                <BarChart2 className="h-4 w-4 text-primary" />
              </div>
              <div className="text-3xl font-bold mb-1">{ov?.detection_rate ?? 0}</div>
              <div className="text-xs text-muted-foreground">Per asset</div>
            </CardContent></Card>
          </>
        )}
      </div>

      <div className="grid lg:grid-cols-2 gap-6">
        {/* Detection timeline */}
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}>
          <Card>
            <CardHeader>
              <CardTitle>Detection Timeline</CardTitle>
              <CardDescription>Last 30 days</CardDescription>
            </CardHeader>
            <CardContent>
              {loading ? <Skeleton /> : timelineData.length === 0 ? (
                <div className="h-[300px] flex items-center justify-center text-muted-foreground">No detections yet</div>
              ) : (
                <ResponsiveContainer width="100%" height={300}>
                  <LineChart data={timelineData}>
                    <CartesianGrid strokeDasharray="3 3" opacity={0.1} />
                    <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                    <YAxis />
                    <Tooltip />
                    <Line type="monotone" dataKey="count" stroke="hsl(var(--destructive))" strokeWidth={2} name="Detections" />
                  </LineChart>
                </ResponsiveContainer>
              )}
            </CardContent>
          </Card>
        </motion.div>

        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.05 }}>
          <Card>
            <CardHeader>
              <CardTitle>Detection Insights Trend</CardTitle>
              <CardDescription>Real detection-insights daily counts</CardDescription>
            </CardHeader>
            <CardContent>
              {loading ? <Skeleton /> : insightTrend.length === 0 ? (
                <div className="h-[300px] flex items-center justify-center text-muted-foreground">No insights yet</div>
              ) : (
                <ResponsiveContainer width="100%" height={300}>
                  <LineChart data={insightTrend}>
                    <CartesianGrid strokeDasharray="3 3" opacity={0.1} />
                    <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                    <YAxis />
                    <Tooltip />
                    <Legend />
                    <Line type="monotone" dataKey="count" stroke="hsl(var(--primary))" strokeWidth={2} name="Daily detections" />
                  </LineChart>
                </ResponsiveContainer>
              )}
            </CardContent>
          </Card>
        </motion.div>

        {/* Platform pie */}
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}>
          <Card>
            <CardHeader>
              <CardTitle>Platform Distribution</CardTitle>
              <CardDescription>Where content is detected</CardDescription>
            </CardHeader>
            <CardContent className="flex items-center justify-center">
              {loading ? <Skeleton /> : pieData.length === 0 ? (
                <div className="h-[300px] flex items-center justify-center text-muted-foreground">No platform data</div>
              ) : (
                <ResponsiveContainer width="100%" height={300}>
                  <PieChart>
                    <Pie
                      data={pieData}
                      cx="50%"
                      cy="50%"
                      labelLine={false}
                      label={(e) => `${e.name} (${e.value})`}
                      outerRadius={100}
                      dataKey="value"
                    >
                      {pieData.map((entry, index) => (
                        <Cell key={index} fill={entry.color} />
                      ))}
                    </Pie>
                    <Tooltip />
                  </PieChart>
                </ResponsiveContainer>
              )}
            </CardContent>
          </Card>
        </motion.div>

        {/* Most detected assets */}
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }}>
          <Card className="lg:col-span-2">
            <CardHeader>
              <CardTitle>Top Attacked Assets</CardTitle>
              <CardDescription>Most targeted assets from detection-insights</CardDescription>
            </CardHeader>
            <CardContent>
              {loading ? <Skeleton /> : attackedAssets.length === 0 ? (
                <div className="py-6 text-center text-muted-foreground">
                  No detection data yet. Upload assets and run detections.
                </div>
              ) : (
                <div className="space-y-4">
                  {attackedAssets.slice(0, 5).map((asset) => (
                    <div key={asset.asset_id} className="flex items-center justify-between">
                      <div className="flex-1 pr-4">
                        <div className="font-medium mb-1 truncate">{asset.filename}</div>
                        <div className="flex gap-2 text-xs text-muted-foreground mb-1">
                          <span>Risk {asset.max_risk}/100</span>
                          <span>•</span>
                          <span className="capitalize">{asset.platforms.slice(0, 3).join(', ')}</span>
                        </div>
                        <div className="w-full bg-muted rounded-full h-2">
                          <div
                            className={`h-2 rounded-full ${
                              asset.max_risk >= 76 ? 'bg-destructive' :
                              asset.max_risk >= 51 ? 'bg-orange-500' :
                              'bg-primary'
                            }`}
                            style={{ width: `${asset.max_risk}%` }}
                          />
                        </div>
                      </div>
                      <div className="ml-4 text-2xl font-bold text-muted-foreground">
                        {asset.detection_count}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </motion.div>
      </div>
    </div>
  );
}
