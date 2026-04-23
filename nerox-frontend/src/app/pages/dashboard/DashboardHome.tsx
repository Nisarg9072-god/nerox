import { motion } from 'motion/react';
import { Shield, TrendingUp, AlertTriangle, Eye, ArrowUp, ArrowDown, Loader2 } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../../components/ui/card';
import { AreaChart, Area, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { useEffect, useState } from 'react';
import { analyticsService, type DashboardResponse } from '../../../services/analyticsService';
import { toast } from 'sonner';

function SkeletonCard() {
  return (
    <Card>
      <CardContent className="p-6">
        <div className="h-4 w-24 bg-muted rounded animate-pulse mb-3" />
        <div className="h-8 w-16 bg-muted rounded animate-pulse mb-2" />
        <div className="h-3 w-20 bg-muted rounded animate-pulse" />
      </CardContent>
    </Card>
  );
}

export default function DashboardHome() {
  const [data, setData] = useState<DashboardResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    analyticsService.getDashboard()
      .then(d => { if (!cancelled) setData(d); })
      .catch(() => { if (!cancelled) toast.error('Failed to load dashboard data.'); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  const ov = data?.overview;

  const statCards = ov
    ? [
        { label: 'Total Assets',       value: ov.total_assets,       icon: Shield,        change: null },
        { label: 'Total Detections',    value: ov.total_detections,   icon: Eye,           change: null },
        { label: 'Critical Alerts',     value: ov.critical_alerts,    icon: AlertTriangle, change: null },
        { label: 'High-Risk Assets',    value: ov.high_risk_assets,   icon: TrendingUp,    change: null },
      ]
    : [];

  const trendData = data?.trend_last_30_days.filter(t => t.count > 0) ?? [];
  const platformData = (data?.platform_distribution ?? []).map(p => ({
    platform: p.platform.charAt(0).toUpperCase() + p.platform.slice(1),
    count:    p.count,
  }));

  const recentActivity = data?.recent_detections ?? [];

  return (
    <div className="p-6 md:p-8 space-y-8">
      <div>
        <h1 className="text-3xl font-bold mb-2">Dashboard</h1>
        <p className="text-muted-foreground">Overview of your asset protection</p>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        {loading
          ? Array.from({ length: 4 }).map((_, i) => <SkeletonCard key={i} />)
          : statCards.map((stat, i) => {
              const Icon = stat.icon;
              return (
                <motion.div key={i} initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.1 }}>
                  <Card>
                    <CardContent className="p-6">
                      <div className="flex items-center justify-between mb-4">
                        <div className="p-2 rounded-lg bg-primary/10">
                          <Icon className="h-5 w-5 text-primary" />
                        </div>
                      </div>
                      <div className="text-2xl font-bold mb-1">{stat.value.toLocaleString()}</div>
                      <div className="text-sm text-muted-foreground">{stat.label}</div>
                    </CardContent>
                  </Card>
                </motion.div>
              );
            })}
      </div>

      {/* Charts */}
      <div className="grid lg:grid-cols-2 gap-6">
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }}>
          <Card>
            <CardHeader>
              <CardTitle>Detection Trend</CardTitle>
              <CardDescription>Last 30 days</CardDescription>
            </CardHeader>
            <CardContent>
              {loading ? (
                <div className="h-[300px] bg-muted/30 rounded animate-pulse" />
              ) : (
                <ResponsiveContainer width="100%" height={300}>
                  <AreaChart data={trendData}>
                    <CartesianGrid strokeDasharray="3 3" opacity={0.1} />
                    <XAxis dataKey="date" tick={{ fontSize: 11 }} tickFormatter={d => d.slice(5)} />
                    <YAxis />
                    <Tooltip />
                    <Area type="monotone" dataKey="count" stroke="hsl(var(--primary))" fill="hsl(var(--primary))" fillOpacity={0.2} />
                  </AreaChart>
                </ResponsiveContainer>
              )}
            </CardContent>
          </Card>
        </motion.div>

        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }}>
          <Card>
            <CardHeader>
              <CardTitle>Detection by Platform</CardTitle>
              <CardDescription>Top platforms</CardDescription>
            </CardHeader>
            <CardContent>
              {loading ? (
                <div className="h-[300px] bg-muted/30 rounded animate-pulse" />
              ) : platformData.length === 0 ? (
                <div className="h-[300px] flex items-center justify-center text-muted-foreground">
                  No detections yet
                </div>
              ) : (
                <ResponsiveContainer width="100%" height={300}>
                  <BarChart data={platformData}>
                    <CartesianGrid strokeDasharray="3 3" opacity={0.1} />
                    <XAxis dataKey="platform" />
                    <YAxis />
                    <Tooltip />
                    <Bar dataKey="count" fill="hsl(var(--primary))" radius={[8, 8, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              )}
            </CardContent>
          </Card>
        </motion.div>
      </div>

      {/* Recent Activity */}
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.4 }}>
        <Card>
          <CardHeader>
            <CardTitle>Recent Detections</CardTitle>
            <CardDescription>Latest detection events</CardDescription>
          </CardHeader>
          <CardContent>
            {loading ? (
              <div className="space-y-3">
                {Array.from({ length: 4 }).map((_, i) => (
                  <div key={i} className="h-14 bg-muted/30 rounded animate-pulse" />
                ))}
              </div>
            ) : recentActivity.length === 0 ? (
              <div className="py-8 text-center text-muted-foreground">
                No detections yet. Upload assets and run similarity searches to see activity here.
              </div>
            ) : (
              <div className="space-y-4">
                {recentActivity.map((d, i) => (
                  <div key={i} className="flex items-start gap-4 p-3 rounded-lg hover:bg-accent transition-colors">
                    <div className={`p-2 rounded-lg ${
                      d.risk_label === 'critical' ? 'bg-destructive/10' :
                      d.risk_label === 'high'     ? 'bg-orange-500/10' :
                      d.risk_label === 'medium'   ? 'bg-yellow-500/10' :
                      'bg-primary/10'
                    }`}>
                      <Eye className="h-4 w-4" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="font-medium truncate">
                        {d.platform_name.charAt(0).toUpperCase() + d.platform_name.slice(1)}
                        {d.watermark_verified && (
                          <span className="ml-2 text-xs bg-green-500/10 text-green-600 px-1.5 py-0.5 rounded">
                            WM Verified
                          </span>
                        )}
                      </div>
                      <div className="text-sm text-muted-foreground">
                        Risk {d.risk_score}/100 • {d.risk_label} •{' '}
                        {new Date(d.detected_at).toLocaleDateString()}
                      </div>
                    </div>
                    <div className={`text-xs px-2 py-1 rounded-full ${
                      d.risk_label === 'critical' ? 'bg-destructive/10 text-destructive' :
                      d.risk_label === 'high'     ? 'bg-orange-500/10 text-orange-600' :
                      d.risk_label === 'medium'   ? 'bg-yellow-500/10 text-yellow-600' :
                      'bg-primary/10 text-primary'
                    }`}>
                      {d.risk_label}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </motion.div>
    </div>
  );
}
