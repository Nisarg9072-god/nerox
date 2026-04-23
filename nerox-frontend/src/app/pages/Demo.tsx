import { motion } from 'motion/react';
import { Shield, AlertCircle, CheckCircle2, TrendingUp } from 'lucide-react';
import { Link } from 'react-router';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card';
import { ThemeToggle } from '../components/ThemeToggle';
import { Progress } from '../components/ui/progress';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts';

const detectionData = [
  { platform: 'Twitter', count: 45 },
  { platform: 'YouTube', count: 32 },
  { platform: 'Instagram', count: 28 },
  { platform: 'Facebook', count: 19 },
  { platform: 'TikTok', count: 15 },
];

const platformDistribution = [
  { name: 'Twitter', value: 35 },
  { name: 'YouTube', value: 25 },
  { name: 'Instagram', value: 20 },
  { name: 'Facebook', value: 12 },
  { name: 'Other', value: 8 },
];

const COLORS = ['#8b5cf6', '#ec4899', '#f59e0b', '#10b981', '#6366f1'];

const sampleAssets = [
  {
    id: 'AST-2024-001',
    name: 'Championship Final Highlights',
    type: 'Video',
    status: 'Protected',
    detections: 12,
    riskScore: 78,
    uploadDate: '2024-01-15',
  },
  {
    id: 'AST-2024-002',
    name: 'Player Interview Series',
    type: 'Video',
    status: 'Protected',
    detections: 5,
    riskScore: 34,
    uploadDate: '2024-01-18',
  },
  {
    id: 'AST-2024-003',
    name: 'Stadium Event Photos',
    type: 'Image',
    status: 'Protected',
    detections: 8,
    riskScore: 56,
    uploadDate: '2024-01-20',
  },
];

export default function Demo() {
  return (
    <div className="min-h-screen">
      <nav className="fixed top-0 left-0 right-0 z-50 border-b border-border/40 bg-background/80 backdrop-blur-xl">
        <div className="container mx-auto px-6 h-16 flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2">
            <Shield className="h-6 w-6" />
            <span className="text-xl font-semibold">Nerox</span>
          </Link>
          <div className="hidden md:flex items-center gap-8">
            <Link to="/features" className="text-sm hover:text-primary transition-colors">Features</Link>
            <Link to="/demo" className="text-sm hover:text-primary transition-colors font-medium">Demo</Link>
            <Link to="/pricing" className="text-sm hover:text-primary transition-colors">Pricing</Link>
            <Link to="/about" className="text-sm hover:text-primary transition-colors">About</Link>
            <Link to="/contact" className="text-sm hover:text-primary transition-colors">Contact</Link>
          </div>
          <div className="flex items-center gap-3">
            <ThemeToggle />
            <Link to="/login">
              <Button variant="ghost" size="sm">Login</Button>
            </Link>
            <Link to="/register">
              <Button size="sm">Get Started</Button>
            </Link>
          </div>
        </div>
      </nav>

      <section className="pt-32 pb-20 px-6">
        <div className="container mx-auto max-w-6xl">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="text-center mb-16"
          >
            <h1 className="text-5xl md:text-6xl font-bold mb-6">
              See Nerox in Action
            </h1>
            <p className="text-xl text-muted-foreground max-w-3xl mx-auto">
              Explore sample data showing how Nerox protects and tracks digital assets in real-time.
            </p>
          </motion.div>

          <div className="space-y-12">
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
            >
              <h2 className="text-3xl font-bold mb-6">Protected Assets</h2>
              <div className="grid gap-4">
                {sampleAssets.map((asset, i) => (
                  <Card key={i} className="hover:border-primary/50 transition-all">
                    <CardContent className="p-6">
                      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                        <div className="flex-1">
                          <div className="flex items-center gap-3 mb-2">
                            <h3 className="font-semibold">{asset.name}</h3>
                            <span className="px-2 py-1 rounded-md bg-primary/10 text-primary text-xs">
                              {asset.type}
                            </span>
                          </div>
                          <p className="text-sm text-muted-foreground">ID: {asset.id}</p>
                        </div>
                        <div className="flex flex-col md:flex-row items-start md:items-center gap-6">
                          <div>
                            <div className="text-sm text-muted-foreground mb-1">Detections</div>
                            <div className="text-2xl font-bold">{asset.detections}</div>
                          </div>
                          <div className="w-32">
                            <div className="text-sm text-muted-foreground mb-2">Risk Score</div>
                            <Progress value={asset.riskScore} className="h-2" />
                            <div className="text-xs text-muted-foreground mt-1">{asset.riskScore}%</div>
                          </div>
                          <CheckCircle2 className="h-5 w-5 text-green-500" />
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>
            </motion.div>

            <div className="grid md:grid-cols-2 gap-8">
              <motion.div
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
              >
                <Card>
                  <CardHeader>
                    <CardTitle>Detection by Platform</CardTitle>
                    <CardDescription>Unauthorized usage across platforms</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <ResponsiveContainer width="100%" height={300}>
                      <BarChart data={detectionData}>
                        <CartesianGrid strokeDasharray="3 3" opacity={0.1} />
                        <XAxis dataKey="platform" />
                        <YAxis />
                        <Tooltip />
                        <Bar dataKey="count" fill="hsl(var(--primary))" radius={[8, 8, 0, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </CardContent>
                </Card>
              </motion.div>

              <motion.div
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
              >
                <Card>
                  <CardHeader>
                    <CardTitle>Platform Distribution</CardTitle>
                    <CardDescription>Where your content appears most</CardDescription>
                  </CardHeader>
                  <CardContent className="flex items-center justify-center">
                    <ResponsiveContainer width="100%" height={300}>
                      <PieChart>
                        <Pie
                          data={platformDistribution}
                          cx="50%"
                          cy="50%"
                          labelLine={false}
                          label={(entry) => entry.name}
                          outerRadius={100}
                          fill="#8884d8"
                          dataKey="value"
                        >
                          {platformDistribution.map((entry, index) => (
                            <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                          ))}
                        </Pie>
                        <Tooltip />
                      </PieChart>
                    </ResponsiveContainer>
                  </CardContent>
                </Card>
              </motion.div>
            </div>

            <motion.div
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
            >
              <Card>
                <CardHeader>
                  <CardTitle>Sample Ownership Verification</CardTitle>
                  <CardDescription>AI-powered verification results</CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="grid md:grid-cols-3 gap-6">
                    <div className="p-4 rounded-lg bg-muted/50">
                      <div className="text-sm text-muted-foreground mb-2">Confidence Score</div>
                      <div className="text-3xl font-bold">98.7%</div>
                    </div>
                    <div className="p-4 rounded-lg bg-muted/50">
                      <div className="text-sm text-muted-foreground mb-2">Verification Time</div>
                      <div className="text-3xl font-bold">47ms</div>
                    </div>
                    <div className="p-4 rounded-lg bg-muted/50">
                      <div className="text-sm text-muted-foreground mb-2">Watermark Status</div>
                      <div className="text-3xl font-bold flex items-center gap-2">
                        <CheckCircle2 className="h-8 w-8 text-green-500" />
                        Valid
                      </div>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </motion.div>
          </div>
        </div>
      </section>

      <section className="py-20 px-6 bg-muted/30">
        <div className="container mx-auto max-w-4xl text-center">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
          >
            <h2 className="text-4xl font-bold mb-4">Ready to Protect Your Assets?</h2>
            <p className="text-xl text-muted-foreground mb-8">
              Start using Nerox today and see the difference
            </p>
            <Link to="/register">
              <Button size="lg">Start Free Trial</Button>
            </Link>
          </motion.div>
        </div>
      </section>

      <footer className="border-t border-border py-12 px-6">
        <div className="container mx-auto max-w-6xl text-center text-sm text-muted-foreground">
          © 2026 Nerox. All rights reserved.
        </div>
      </footer>
    </div>
  );
}
