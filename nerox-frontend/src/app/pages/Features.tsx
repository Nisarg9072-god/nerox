import { motion } from 'motion/react';
import { Shield, Eye, AlertTriangle, BarChart3, Lock, Zap, Check, FileSearch, Clock, Globe } from 'lucide-react';
import { Link } from 'react-router';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card';
import { ThemeToggle } from '../components/ThemeToggle';

const featuresList = [
  {
    icon: Shield,
    title: 'AI Fingerprinting',
    description: 'Create unique digital signatures using advanced neural networks',
    benefits: [
      'Perceptual hashing technology',
      'Resistant to compression and editing',
      'Instant recognition across formats',
      'Works with images and videos',
    ],
  },
  {
    icon: Eye,
    title: 'Invisible Watermarking',
    description: 'Embed imperceptible ownership markers in your content',
    benefits: [
      'Survives format conversion',
      'No visual quality loss',
      'Blockchain-verified ownership',
      'Tamper-proof embedding',
    ],
  },
  {
    icon: AlertTriangle,
    title: 'Detection Engine',
    description: 'Real-time scanning across platforms for unauthorized usage',
    benefits: [
      'Multi-platform monitoring',
      'Automated takedown requests',
      'Social media integration',
      '24/7 continuous scanning',
    ],
  },
  {
    icon: BarChart3,
    title: 'Analytics Dashboard',
    description: 'Comprehensive insights into your asset protection',
    benefits: [
      'Real-time detection alerts',
      'Geographic distribution maps',
      'Trend analysis and reporting',
      'Custom report generation',
    ],
  },
  {
    icon: FileSearch,
    title: 'Ownership Verification',
    description: 'Instantly verify content ownership with AI-powered analysis',
    benefits: [
      'Confidence score calculation',
      'Blockchain proof of ownership',
      'Legal evidence generation',
      'Instant verification reports',
    ],
  },
  {
    icon: Lock,
    title: 'Secure Infrastructure',
    description: 'Enterprise-grade security for your valuable assets',
    benefits: [
      'End-to-end encryption',
      'SOC 2 Type II compliant',
      'GDPR compliant',
      'Regular security audits',
    ],
  },
];

export default function Features() {
  return (
    <div className="min-h-screen">
      <nav className="fixed top-0 left-0 right-0 z-50 border-b border-border/40 bg-background/80 backdrop-blur-xl">
        <div className="container mx-auto px-6 h-16 flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2">
            <Shield className="h-6 w-6" />
            <span className="text-xl font-semibold">Nerox</span>
          </Link>
          <div className="hidden md:flex items-center gap-8">
            <Link to="/features" className="text-sm hover:text-primary transition-colors font-medium">Features</Link>
            <Link to="/demo" className="text-sm hover:text-primary transition-colors">Demo</Link>
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
            className="text-center mb-20"
          >
            <h1 className="text-5xl md:text-6xl font-bold mb-6">
              Powerful Features for Complete Protection
            </h1>
            <p className="text-xl text-muted-foreground max-w-3xl mx-auto">
              Everything you need to protect, track, and verify your digital assets in one comprehensive platform.
            </p>
          </motion.div>

          <div className="grid md:grid-cols-2 gap-8">
            {featuresList.map((feature, i) => {
              const Icon = feature.icon;
              return (
                <motion.div
                  key={i}
                  initial={{ opacity: 0, y: 20 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  transition={{ delay: i * 0.1 }}
                  viewport={{ once: true }}
                >
                  <Card className="h-full hover:border-primary/50 transition-all duration-300">
                    <CardHeader>
                      <div className="rounded-lg bg-primary/10 w-12 h-12 flex items-center justify-center mb-4">
                        <Icon className="h-6 w-6 text-primary" />
                      </div>
                      <CardTitle>{feature.title}</CardTitle>
                      <CardDescription>{feature.description}</CardDescription>
                    </CardHeader>
                    <CardContent>
                      <ul className="space-y-2">
                        {feature.benefits.map((benefit, j) => (
                          <li key={j} className="flex items-start gap-2">
                            <Check className="h-5 w-5 text-primary shrink-0 mt-0.5" />
                            <span className="text-sm text-muted-foreground">{benefit}</span>
                          </li>
                        ))}
                      </ul>
                    </CardContent>
                  </Card>
                </motion.div>
              );
            })}
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
            <h2 className="text-4xl font-bold mb-4">Ready to Get Started?</h2>
            <p className="text-xl text-muted-foreground mb-8">
              See how Nerox can protect your digital assets
            </p>
            <div className="flex items-center justify-center gap-4">
              <Link to="/demo">
                <Button size="lg" variant="outline">View Demo</Button>
              </Link>
              <Link to="/register">
                <Button size="lg">Start Free Trial</Button>
              </Link>
            </div>
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
