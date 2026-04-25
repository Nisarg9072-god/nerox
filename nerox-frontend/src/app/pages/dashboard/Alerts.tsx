import { motion } from 'motion/react';
import { AlertCircle, CheckCircle2, Clock, Bell, Shield, RefreshCw } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../../components/ui/card';
import { Badge } from '../../components/ui/badge';
import { Button } from '../../components/ui/button';
import { useEffect, useState } from 'react';
import { analyticsService, type AlertItem } from '../../../services/analyticsService';
import { toast } from 'sonner';
import { useWsEvent } from '../../../context/WebSocketContext';

const ALERT_META: Record<string, { color: string; label: string; badge: 'destructive' | 'default' | 'secondary' | 'outline' }> = {
  critical_risk:      { color: 'border-destructive',   label: 'Critical Risk',       badge: 'destructive' },
  watermark_verified: { color: 'border-yellow-500',    label: 'WM Verified',         badge: 'default'     },
  detection_spike:    { color: 'border-orange-500',    label: 'Detection Spike',     badge: 'default'     },
  repeated_misuse:    { color: 'border-yellow-600',    label: 'Repeated Misuse',     badge: 'secondary'   },
};

const SEV_COLOR: Record<string, string> = {
  critical: 'text-destructive',
  high:     'text-orange-500',
  medium:   'text-yellow-500',
  low:      'text-primary',
};

export default function Alerts() {
  const [alerts,   setAlerts]   = useState<AlertItem[]>([]);
  const [loading,  setLoading]  = useState(true);
  const [resolving, setResolving] = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    analyticsService.getAlerts()
      .then(r => setAlerts(r.alerts))
      .catch(() => toast.error('Failed to load alerts.'))
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  useWsEvent('alert_created', (event) => {
    const alert = event.data?.alert as AlertItem | undefined;
    if (!alert) return;
    setAlerts((prev) => [alert, ...prev.filter((a) => a.alert_id !== alert.alert_id)].slice(0, 50));
  });

  const handleResolve = async (alertId: string) => {
    setResolving(alertId);
    try {
      await analyticsService.resolveAlert(alertId);
      setAlerts(prev => prev.filter(a => a.alert_id !== alertId));
      toast.success('Alert resolved');
    } catch {
      toast.error('Failed to resolve alert.');
    } finally {
      setResolving(null);
    }
  };

  const counts = {
    critical: alerts.filter(a => a.severity === 'critical').length,
    high:     alerts.filter(a => a.severity === 'high').length,
    medium:   alerts.filter(a => a.severity === 'medium').length,
    total:    alerts.length,
  };

  return (
    <div className="p-4 sm:p-6 md:p-8 space-y-6 md:space-y-8">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold mb-1">Alerts Center</h1>
          <p className="text-sm sm:text-base text-muted-foreground">Critical notifications and priority actions</p>
        </div>
        <Button variant="outline" onClick={load} disabled={loading} className="self-start sm:self-auto shrink-0">
          <RefreshCw className={`h-4 w-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </Button>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-2 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card><CardContent className="p-6">
          <div className="flex items-center justify-between mb-2">
            <Bell className="h-5 w-5 text-muted-foreground" />
            <AlertCircle className="h-5 w-5 text-destructive" />
          </div>
          <div className="text-3xl font-bold mb-1">
            {loading ? '…' : counts.critical}
          </div>
          <div className="text-sm text-muted-foreground">Critical</div>
        </CardContent></Card>

        <Card><CardContent className="p-6">
          <div className="flex items-center justify-between mb-2">
            <Bell className="h-5 w-5 text-muted-foreground" />
            <AlertCircle className="h-5 w-5 text-orange-500" />
          </div>
          <div className="text-3xl font-bold mb-1">
            {loading ? '…' : counts.high}
          </div>
          <div className="text-sm text-muted-foreground">High</div>
        </CardContent></Card>

        <Card><CardContent className="p-6">
          <div className="flex items-center justify-between mb-2">
            <Bell className="h-5 w-5 text-muted-foreground" />
            <Clock className="h-5 w-5 text-yellow-500" />
          </div>
          <div className="text-3xl font-bold mb-1">
            {loading ? '…' : counts.medium}
          </div>
          <div className="text-sm text-muted-foreground">Medium</div>
        </CardContent></Card>

        <Card><CardContent className="p-6">
          <div className="flex items-center justify-between mb-2">
            <Bell className="h-5 w-5 text-muted-foreground" />
            <CheckCircle2 className="h-5 w-5 text-green-500" />
          </div>
          <div className="text-3xl font-bold mb-1">
            {loading ? '…' : counts.total}
          </div>
          <div className="text-sm text-muted-foreground">Active Total</div>
        </CardContent></Card>
      </div>

      {/* Alert list */}
      <div className="grid gap-4">
        {loading ? (
          Array.from({ length: 3 }).map((_, i) => (
            <Card key={i}>
              <CardContent className="p-6">
                <div className="h-16 bg-muted/30 rounded animate-pulse" />
              </CardContent>
            </Card>
          ))
        ) : alerts.length === 0 ? (
          <Card>
            <CardContent className="p-12 text-center">
              <CheckCircle2 className="h-12 w-12 text-green-500 mx-auto mb-4" />
              <h3 className="text-lg font-semibold mb-2">All Clear</h3>
              <p className="text-muted-foreground">No active alerts. Your assets are being monitored.</p>
            </CardContent>
          </Card>
        ) : (
          alerts.map((alert, i) => {
            const meta = ALERT_META[alert.alert_type] ?? {
              color: '', label: alert.alert_type, badge: 'secondary' as const,
            };
            return (
              <motion.div
                key={alert.alert_id}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.04 }}
              >
                <Card className={meta.color ? `border-2 ${meta.color}/50` : ''}>
                  <CardContent className="p-6">
                    <div className="flex flex-col lg:flex-row lg:items-start gap-4">
                      <div className={`p-3 rounded-lg shrink-0 ${
                        alert.severity === 'critical' ? 'bg-destructive/10' :
                        alert.severity === 'high'     ? 'bg-orange-500/10' :
                        'bg-yellow-500/10'
                      }`}>
                        <AlertCircle className={`h-6 w-6 ${SEV_COLOR[alert.severity] ?? 'text-primary'}`} />
                      </div>

                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap mb-1">
                          <h3 className="font-semibold text-sm sm:text-base">{meta.label}</h3>
                          <Badge variant={meta.badge}>{alert.severity}</Badge>
                          <Badge variant="outline" className="text-xs">{alert.alert_type}</Badge>
                        </div>
                        <p className="text-sm text-muted-foreground mb-2 break-words">{alert.message}</p>
                        <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
                          <div className="flex items-center gap-1">
                            <Shield className="h-3 w-3 shrink-0" />
                            <span className="font-mono">{alert.asset_id.slice(-12)}</span>
                          </div>
                          <div className="flex items-center gap-1">
                            <Clock className="h-3 w-3 shrink-0" />
                            {new Date(alert.triggered_at).toLocaleString()}
                          </div>
                        </div>
                      </div>

                      <div className="flex gap-2 sm:shrink-0">
                        <Button
                          variant="outline"
                          size="sm"
                          disabled={resolving === alert.alert_id}
                          onClick={() => handleResolve(alert.alert_id)}
                          className="w-full sm:w-auto"
                        >
                          {resolving === alert.alert_id ? 'Resolving…' : 'Resolve'}
                        </Button>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              </motion.div>
            );
          })
        )}
      </div>
    </div>
  );
}
