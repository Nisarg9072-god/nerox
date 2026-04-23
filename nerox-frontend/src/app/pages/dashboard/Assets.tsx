import { motion } from 'motion/react';
import { Search, Image, Video, Shield, Eye, AlertCircle, RefreshCw, ExternalLink } from 'lucide-react';
import { Card, CardContent } from '../../components/ui/card';
import { Input } from '../../components/ui/input';
import { Button } from '../../components/ui/button';
import { Progress } from '../../components/ui/progress';
import { Badge } from '../../components/ui/badge';
import { useEffect, useState } from 'react';
import { assetService, type AssetItem } from '../../../services/assetService';
import { toast } from 'sonner';

function SkeletonRow() {
  return (
    <Card>
      <CardContent className="p-6">
        <div className="flex items-center gap-4">
          <div className="h-12 w-12 rounded-lg bg-muted animate-pulse" />
          <div className="flex-1 space-y-2">
            <div className="h-4 w-48 bg-muted rounded animate-pulse" />
            <div className="h-3 w-32 bg-muted rounded animate-pulse" />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

const BACKEND_BASE = (import.meta.env.VITE_API_BASE_URL as string) || 'http://localhost:8000';

export default function Assets() {
  const [assets, setAssets]     = useState<AssetItem[]>([]);
  const [loading, setLoading]   = useState(true);
  const [total, setTotal]       = useState(0);
  const [searchTerm, setSearchTerm] = useState('');
  const [filterType, setFilterType] = useState<'all' | 'image' | 'video'>('all');

  const load = () => {
    setLoading(true);
    assetService.list(0, 100)
      .then(r => { setAssets(r.assets); setTotal(r.total); })
      .catch(() => toast.error('Failed to load assets.'))
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  const filtered = assets.filter(a => {
    const matchSearch = a.original_filename.toLowerCase().includes(searchTerm.toLowerCase());
    const matchType   =
      filterType === 'all' ? true : a.file_type === filterType;
    return matchSearch && matchType;
  });

  const riskColor = (score: number) =>
    score >= 76 ? 'text-destructive' :
    score >= 51 ? 'text-orange-500' :
    score >= 26 ? 'text-yellow-500' :
    'text-green-500';

  return (
    <div className="p-6 md:p-8 space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold mb-2">Asset Manager</h1>
          <p className="text-muted-foreground">
            {total} protected asset{total !== 1 ? 's' : ''} • AI fingerprinting + watermarking
          </p>
        </div>
        <Button variant="outline" onClick={load} disabled={loading}>
          <RefreshCw className={`h-4 w-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </Button>
      </div>

      <div className="flex flex-col md:flex-row gap-4">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search assets..."
            className="pl-10"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
        </div>
        <div className="flex gap-2">
          {(['all', 'image', 'video'] as const).map(t => (
            <Button
              key={t}
              variant={filterType === t ? 'default' : 'outline'}
              onClick={() => setFilterType(t)}
            >
              {t === 'image' && <Image className="h-4 w-4 mr-2" />}
              {t === 'video' && <Video className="h-4 w-4 mr-2" />}
              {t.charAt(0).toUpperCase() + t.slice(1)}
            </Button>
          ))}
        </div>
      </div>

      <div className="grid gap-4">
        {loading
          ? Array.from({ length: 4 }).map((_, i) => <SkeletonRow key={i} />)
          : filtered.length === 0
            ? (
              <Card>
                <CardContent className="p-12 text-center text-muted-foreground">
                  {assets.length === 0
                    ? 'No assets yet. Upload your first file to get started.'
                    : 'No assets match your search.'}
                </CardContent>
              </Card>
            )
            : filtered.map((asset, i) => (
              <motion.div
                key={asset.asset_id}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.04 }}
              >
                <Card className="hover:border-primary/50 transition-all">
                  <CardContent className="p-6">
                    <div className="flex flex-col lg:flex-row lg:items-center gap-6">
                      <div className="flex items-start gap-4 flex-1">
                        <div className="p-3 rounded-lg bg-primary/10">
                          {asset.file_type === 'image'
                            ? <Image className="h-6 w-6 text-primary" />
                            : <Video className="h-6 w-6 text-primary" />}
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 mb-2 flex-wrap">
                            <h3 className="font-semibold truncate">{asset.original_filename}</h3>
                            <Badge variant="outline">{asset.status}</Badge>
                            {asset.file_type && (
                              <Badge variant="secondary">{asset.file_type}</Badge>
                            )}
                          </div>
                          <div className="text-sm text-muted-foreground mb-2">
                            {asset.asset_id.slice(-8).toUpperCase()} •{' '}
                            {(asset.file_size / 1024 / 1024).toFixed(1)} MB •{' '}
                            {new Date(asset.created_at).toLocaleDateString()}
                          </div>
                          <div className="flex items-center gap-4 text-sm flex-wrap">
                            <div className="flex items-center gap-1">
                              <Shield className={`h-4 w-4 ${asset.watermark_id ? 'text-green-500' : 'text-muted-foreground'}`} />
                              <span className={asset.watermark_id ? 'text-green-600 dark:text-green-400' : 'text-muted-foreground'}>
                                Watermark {asset.watermark_id ? '✓' : 'pending'}
                              </span>
                            </div>
                            <div className="flex items-center gap-1">
                              <Eye className={`h-4 w-4 ${asset.fingerprint_id ? 'text-blue-500' : 'text-muted-foreground'}`} />
                              <span className={asset.fingerprint_id ? 'text-blue-600 dark:text-blue-400' : 'text-muted-foreground'}>
                                Fingerprint {asset.fingerprint_id ? '✓' : 'pending'}
                              </span>
                            </div>
                          </div>
                        </div>
                      </div>

                      <div className="flex flex-col md:flex-row items-start md:items-center gap-4 lg:gap-6">
                        {asset.file_url && (
                          <a
                            href={asset.file_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-xs text-primary hover:underline flex items-center gap-1"
                          >
                            <ExternalLink className="h-3 w-3" /> Preview
                          </a>
                        )}
                      </div>
                    </div>
                  </CardContent>
                </Card>
              </motion.div>
            ))}
      </div>
    </div>
  );
}
