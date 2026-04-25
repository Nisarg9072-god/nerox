import { motion } from 'motion/react';
import { Upload as UploadIcon, Image, Video, CheckCircle2, X, Loader2, AlertCircle } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Progress } from '../../components/ui/progress';
import { useState, useCallback } from 'react';
import { assetService } from '../../../services/assetService';
import { toast } from 'sonner';

interface UploadedFile {
  id: string;
  name: string;
  size: string;
  type: 'image' | 'video';
  progress: number;
  status: 'uploading' | 'completed' | 'error';
  assetId?: string;
  watermarkId?: string;
  errorMsg?: string;
}

export default function Upload() {
  const [files, setFiles] = useState<UploadedFile[]>([]);
  const [dragging, setDragging] = useState(false);

  const updateFile = useCallback((id: string, patch: Partial<UploadedFile>) => {
    setFiles(prev => prev.map(f => (f.id === id ? { ...f, ...patch } : f)));
  }, []);

  const MAX_FILE_SIZE_MB = 50;

  const uploadFile = useCallback(async (file: File) => {
    // Client-side file size validation (matches backend MAX_FILE_SIZE_MB)
    if (file.size > MAX_FILE_SIZE_MB * 1024 * 1024) {
      toast.error(`${file.name}: File exceeds the maximum allowed size of ${MAX_FILE_SIZE_MB}MB.`);
      return;
    }

    const fid = `${file.name}-${Date.now()}`;
    const entry: UploadedFile = {
      id:       fid,
      name:     file.name,
      size:     (file.size / 1024 / 1024).toFixed(2) + ' MB',
      type:     file.type.startsWith('image') ? 'image' : 'video',
      progress: 0,
      status:   'uploading',
    };

    setFiles(prev => [...prev, entry]);

    try {
      const resp = await assetService.upload(file, (pct) => {
        updateFile(fid, { progress: pct });
      });
      updateFile(fid, {
        progress:    100,
        status:      'completed',
        assetId:     resp.asset_id,
        watermarkId: resp.watermark_id,
      });
      toast.success(`${file.name} uploaded — AI fingerprinting & watermarking started`);
    } catch (err: any) {
      const msg = err?.response?.data?.error || 'Upload failed';
      updateFile(fid, { status: 'error', errorMsg: msg });
      toast.error(`${file.name}: ${msg}`);
    }
  }, [updateFile]);

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    Array.from(e.dataTransfer.files).forEach(uploadFile);
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) Array.from(e.target.files).forEach(uploadFile);
    e.target.value = '';
  };

  const removeFile = (id: string) =>
    setFiles(prev => prev.filter(f => f.id !== id));

  const uploadingCount  = files.filter(f => f.status === 'uploading').length;
  const completedCount  = files.filter(f => f.status === 'completed').length;

  return (
    <div className="p-4 sm:p-6 md:p-8 space-y-6 md:space-y-8">
      <div>
        <h1 className="text-2xl sm:text-3xl font-bold mb-1">Upload Assets</h1>
        <p className="text-sm sm:text-base text-muted-foreground">Protect your images and videos with AI fingerprinting and watermarking</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 sm:gap-6">
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="lg:col-span-2">
          <Card>
            <CardContent className="p-0">
              {/* Drop zone */}
              <div
                className={`p-8 sm:p-12 border-2 border-dashed rounded-lg m-4 sm:m-6 transition-all ${
                  dragging ? 'border-primary bg-primary/5' : 'border-border'
                }`}
                onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
                onDragLeave={() => setDragging(false)}
                onDrop={handleDrop}
              >
                <div className="text-center">
                  <div className="inline-flex p-3 sm:p-4 rounded-full bg-primary/10 mb-3 sm:mb-4">
                    <UploadIcon className="h-6 w-6 sm:h-8 sm:w-8 text-primary" />
                  </div>
                  <h3 className="text-lg sm:text-xl font-semibold mb-1 sm:mb-2">Drop files here</h3>
                  <p className="text-sm text-muted-foreground mb-4 sm:mb-6">or click to browse</p>
                  <label>
                    <input
                      type="file"
                      multiple
                      accept="image/jpeg,image/png,video/mp4,video/quicktime"
                      className="hidden"
                      onChange={handleFileSelect}
                    />
                    <Button asChild size="sm"><span>Select Files</span></Button>
                  </label>
                  <p className="text-xs text-muted-foreground mt-3">Supported: JPG, PNG, MP4, MOV (Max 50MB)</p>
                </div>
              </div>

              {/* File list */}
              {files.length > 0 && (
                <div className="px-6 pb-6 space-y-3">
                  <h3 className="font-semibold mb-3">
                    Files{uploadingCount > 0 && ` (${uploadingCount} uploading)`}
                  </h3>
                  {files.map((file) => (
                    <div key={file.id} className={`p-4 rounded-lg border ${
                      file.status === 'error' ? 'border-destructive/50' : 'border-border'
                    }`}>
                      <div className="flex items-start gap-3 mb-3">
                        <div className="p-2 rounded-lg bg-primary/10">
                          {file.type === 'image'
                            ? <Image className="h-5 w-5 text-primary" />
                            : <Video className="h-5 w-5 text-primary" />}
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="font-medium truncate">{file.name}</div>
                          <div className="text-sm text-muted-foreground">{file.size}</div>
                          {file.assetId && (
                            <div className="text-xs text-muted-foreground mt-0.5">
                              Asset ID: {file.assetId}
                            </div>
                          )}
                        </div>
                        {file.status === 'completed' && <CheckCircle2 className="h-5 w-5 text-green-500 shrink-0" />}
                        {file.status === 'error'     && <AlertCircle  className="h-5 w-5 text-destructive shrink-0" />}
                        {file.status === 'uploading' && <Loader2 className="h-5 w-5 animate-spin text-primary shrink-0" />}
                        {file.status !== 'uploading' && (
                          <button onClick={() => removeFile(file.id)} className="p-1 hover:bg-accent rounded ml-1">
                            <X className="h-4 w-4" />
                          </button>
                        )}
                      </div>

                      {file.status === 'uploading' && (
                        <div className="space-y-1">
                          <div className="flex items-center justify-between text-sm">
                            <span className="text-muted-foreground">{file.progress}%</span>
                          </div>
                          <Progress value={file.progress} />
                        </div>
                      )}
                      {file.status === 'completed' && (
                        <div className="text-xs text-green-600 dark:text-green-400">
                          ✓ Uploaded — AI fingerprinting & watermarking running in background
                        </div>
                      )}
                      {file.status === 'error' && (
                        <div className="text-xs text-destructive">{file.errorMsg}</div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </motion.div>

        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }} className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Protection Features</CardTitle>
              <CardDescription>Automatically applied</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {[
                { title: 'AI Fingerprinting', desc: 'ResNet50 2048-d embedding via FAISS' },
                { title: 'Invisible Watermark', desc: 'DCT frequency-domain ownership token' },
                { title: 'Active Monitoring',  desc: 'Risk scoring & instant alerts' },
              ].map(item => (
                <div key={item.title} className="flex items-start gap-3">
                  <CheckCircle2 className="h-5 w-5 text-primary shrink-0 mt-0.5" />
                  <div>
                    <div className="font-medium">{item.title}</div>
                    <div className="text-sm text-muted-foreground">{item.desc}</div>
                  </div>
                </div>
              ))}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Session Stats</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex justify-between">
                <span className="text-muted-foreground">Uploaded now</span>
                <span className="font-semibold">{completedCount} files</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Uploading</span>
                <span className="font-semibold">{uploadingCount} files</span>
              </div>
            </CardContent>
          </Card>
        </motion.div>
      </div>
    </div>
  );
}
