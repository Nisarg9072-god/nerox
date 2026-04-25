import { motion } from 'motion/react';
import { Upload as UploadIcon, CheckCircle2, XCircle, AlertCircle, FileCheck, Clock } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Progress } from '../../components/ui/progress';
import { useState } from 'react';
import { watermarkService, type VerifyResponse } from '../../../services/watermarkService';
import { toast } from 'sonner';

interface HistoryItem {
  name: string;
  result: VerifyResponse;
  at: string;
}

export default function Verification() {
  const [verifying, setVerifying]   = useState(false);
  const [progress,  setProgress]    = useState(0);
  const [result,    setResult]      = useState<VerifyResponse | null>(null);
  const [file,      setFile]        = useState<File | null>(null);
  const [history,   setHistory]     = useState<HistoryItem[]>([]);

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files?.[0]) {
      setFile(e.target.files[0]);
      setResult(null);
    }
  };

  const handleVerify = async () => {
    if (!file) return;
    setVerifying(true);
    setResult(null);
    setProgress(0);

    // Animate indeterminate progress while real API runs
    const timer = setInterval(() => {
      setProgress(p => Math.min(p + 4, 90));
    }, 200);

    try {
      const resp = await watermarkService.verify(file);
      setProgress(100);
      setResult(resp);
      setHistory(prev => [{ name: file.name, result: resp, at: new Date().toLocaleTimeString() }, ...prev.slice(0, 4)]);
      if (resp.verified) {
        toast.success('Ownership verified — watermark found!');
      } else {
        toast.info('No watermark detected in this file.');
      }
    } catch (err: any) {
      const msg = err?.response?.data?.error || 'Verification failed.';
      toast.error(msg);
    } finally {
      clearInterval(timer);
      setVerifying(false);
    }
  };

  const reset = () => { setFile(null); setResult(null); setProgress(0); };

  return (
    <div className="p-4 sm:p-6 md:p-8 space-y-6 md:space-y-8">
      <div>
        <h1 className="text-2xl sm:text-3xl font-bold mb-1">Watermark Verification</h1>
        <p className="text-sm sm:text-base text-muted-foreground">Verify ownership of suspicious media files via DCT watermark extraction</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 sm:gap-6">
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="lg:col-span-2">
          <Card>
            <CardHeader>
              <CardTitle>Upload for Verification</CardTitle>
              <CardDescription>Upload an image or video to check for embedded ownership watermarks</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-6">
                {/* Drop zone */}
                <div className="border-2 border-dashed border-border rounded-lg p-8 sm:p-12 text-center">
                  <div className="inline-flex p-3 sm:p-4 rounded-full bg-primary/10 mb-3 sm:mb-4">
                    <UploadIcon className="h-6 w-6 sm:h-8 sm:w-8 text-primary" />
                  </div>
                  <h3 className="text-base sm:text-lg font-semibold mb-1 sm:mb-2">Select suspicious media file</h3>
                  <p className="text-xs sm:text-sm text-muted-foreground mb-4 sm:mb-6">
                    Upload the suspicious file to verify ownership
                  </p>
                  <label>
                    <input
                      type="file"
                      accept="image/jpeg,image/png,video/mp4,video/quicktime"
                      className="hidden"
                      onChange={handleFileSelect}
                    />
                    <Button asChild size="sm"><span>Choose File</span></Button>
                  </label>
                </div>

                {/* File selected */}
                {file && !verifying && !result && (
                  <div className="p-4 rounded-lg border border-border">
                    <div className="flex items-center justify-between mb-4">
                      <div>
                        <div className="font-medium">{file.name}</div>
                        <div className="text-sm text-muted-foreground">
                          {(file.size / 1024 / 1024).toFixed(2)} MB
                        </div>
                      </div>
                      <FileCheck className="h-5 w-5 text-primary" />
                    </div>
                    <Button onClick={handleVerify} disabled={verifying} className="w-full">
                      Verify Ownership
                    </Button>
                  </div>
                )}

                {/* Analysing */}
                {verifying && (
                  <div className="p-6 rounded-lg border border-border">
                    <div className="text-center mb-4">
                      <div className="inline-flex p-3 rounded-full bg-primary/10 mb-3">
                        <div className="h-6 w-6 border-2 border-primary border-t-transparent rounded-full animate-spin" />
                      </div>
                      <div className="font-medium mb-2">Extracting watermark…</div>
                      <div className="text-sm text-muted-foreground">
                        Running DCT frequency-domain analysis on <span className="font-mono">{file?.name}</span>
                      </div>
                    </div>
                    <Progress value={progress} className="h-2" />
                  </div>
                )}

                {/* Result */}
                {result && !verifying && (
                  <div className={`p-6 rounded-lg border-2 ${
                    result.verified
                      ? 'border-green-500 bg-green-500/5'
                      : result.error
                        ? 'border-destructive bg-destructive/5'
                        : 'border-muted'
                  }`}>
                    <div className="flex items-start gap-4 mb-6">
                      <div className={`p-3 rounded-full ${
                        result.verified ? 'bg-green-500/10' : 'bg-destructive/10'
                      }`}>
                        {result.verified
                          ? <CheckCircle2 className="h-8 w-8 text-green-500" />
                          : <XCircle      className="h-8 w-8 text-destructive" />}
                      </div>
                      <div className="flex-1">
                        <h3 className="text-xl font-bold mb-2">
                          {result.verified ? 'Ownership Verified' : 'No Watermark Detected'}
                        </h3>
                        <p className="text-muted-foreground">
                          {result.verified
                            ? 'This content contains a valid Nerox DCT watermark proving ownership.'
                            : result.error
                              ? result.error
                              : 'No embedded ownership watermark found in this file.'}
                        </p>
                      </div>
                    </div>

                    {result.verified && (
                      <div className="grid grid-cols-2 sm:grid-cols-2 md:grid-cols-3 gap-3 sm:gap-4 mb-4">
                        <div className="p-3 sm:p-4 rounded-lg bg-background">
                          <div className="text-xs sm:text-sm text-muted-foreground mb-1">Confidence</div>
                          <div className="text-xl sm:text-2xl font-bold">
                            {Math.round(result.confidence * 100)}%
                          </div>
                          <div className="text-xs text-muted-foreground capitalize">
                            {result.confidence_label}
                          </div>
                        </div>
                        {result.ownership && (
                          <>
                            <div className="p-3 sm:p-4 rounded-lg bg-background">
                              <div className="text-xs sm:text-sm text-muted-foreground mb-1">Asset ID</div>
                              <div className="font-mono text-xs break-all">{result.ownership.asset_id.slice(-12)}</div>
                            </div>
                            <div className="p-3 sm:p-4 rounded-lg bg-background col-span-2 sm:col-span-1">
                              <div className="text-xs sm:text-sm text-muted-foreground mb-1">WM Token</div>
                              <div className="font-mono text-xs break-all text-muted-foreground">
                                {result.wm_token_detected?.slice(0, 16)}…
                              </div>
                            </div>
                          </>
                        )}
                        <div className="p-3 sm:p-4 rounded-lg bg-background">
                          <div className="text-xs sm:text-sm text-muted-foreground mb-1">Method</div>
                          <div className="font-semibold text-sm">{result.watermark_method}</div>
                        </div>
                      </div>
                    )}

                    <div className="flex flex-col sm:flex-row gap-3">
                      <Button onClick={reset} variant="outline" className="w-full sm:w-auto">Verify Another File</Button>
                    </div>
                  </div>
                )}
              </div>
            </CardContent>
          </Card>
        </motion.div>

        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }} className="space-y-6">
          <Card>
            <CardHeader><CardTitle>How it Works</CardTitle></CardHeader>
            <CardContent className="space-y-4">
              {[
                { n: 1, title: 'Upload File',   desc: 'Select the suspicious media file' },
                { n: 2, title: 'AI Analysis',   desc: 'DCT frequency-domain watermark extraction' },
                { n: 3, title: 'Get Results',   desc: 'Instant ownership proof with confidence score' },
              ].map(s => (
                <div key={s.n} className="flex gap-3">
                  <div className="flex h-6 w-6 items-center justify-center rounded-full bg-primary text-primary-foreground text-sm font-medium shrink-0">
                    {s.n}
                  </div>
                  <div>
                    <div className="font-medium mb-1">{s.title}</div>
                    <div className="text-sm text-muted-foreground">{s.desc}</div>
                  </div>
                </div>
              ))}
            </CardContent>
          </Card>

          <Card>
            <CardHeader><CardTitle>Session History</CardTitle></CardHeader>
            <CardContent className="space-y-3">
              {history.length === 0 ? (
                <p className="text-sm text-muted-foreground">No verifications yet this session.</p>
              ) : (
                history.map((h, i) => (
                  <div key={i} className="p-3 rounded-lg bg-muted/50">
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-sm font-medium truncate max-w-[140px]">{h.name}</span>
                      {h.result.verified
                        ? <CheckCircle2 className="h-4 w-4 text-green-500 shrink-0" />
                        : <XCircle      className="h-4 w-4 text-destructive shrink-0" />}
                    </div>
                    <div className="text-xs text-muted-foreground">
                      {h.result.verified
                        ? `${Math.round(h.result.confidence * 100)}% confidence`
                        : 'No watermark'}{' '}
                      • {h.at}
                    </div>
                  </div>
                ))
              )}
            </CardContent>
          </Card>
        </motion.div>
      </div>
    </div>
  );
}
