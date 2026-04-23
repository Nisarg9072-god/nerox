import { motion } from 'motion/react';
import { Shield, Eye, AlertTriangle, BarChart3, Lock, Zap, Check, ArrowRight } from 'lucide-react';
import { Link } from 'react-router';
import { Button } from '../components/ui/button';
import { Card, CardContent } from '../components/ui/card';
import { ThemeToggle } from '../components/ThemeToggle';

const features = [
  {
    icon: Shield,
    title: 'AI Fingerprinting',
    description: 'Advanced neural networks create unique digital signatures for every asset.',
  },
  {
    icon: Eye,
    title: 'Invisible Watermarking',
    description: 'Embed imperceptible ownership markers that survive compression and editing.',
  },
  {
    icon: AlertTriangle,
    title: 'Detection Engine',
    description: 'Real-time scanning across platforms to identify unauthorized usage.',
  },
  {
    icon: BarChart3,
    title: 'Analytics Dashboard',
    description: 'Comprehensive insights into asset protection and piracy trends.',
  },
];

const stats = [
  { value: '99.8%', label: 'Detection Accuracy' },
  { value: '24/7', label: 'Monitoring' },
  { value: '<100ms', label: 'Verification Time' },
  { value: '50M+', label: 'Assets Protected' },
];

const testimonials = [
  {
    company: 'Premier League FC',
    quote: 'Nerox has transformed how we protect our match footage. The AI detection is incredibly accurate.',
    author: 'Digital Rights Manager',
  },
  {
    company: 'ESPN Digital',
    quote: 'Finally, a solution that keeps pace with modern piracy. The watermarking is completely invisible.',
    author: 'Content Protection Lead',
  },
  {
    company: 'NBA Media Group',
    quote: 'Reduced unauthorized distribution by 87% in the first quarter. Game-changing technology.',
    author: 'VP of Media Operations',
  },
];

export default function Landing() {
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
            transition={{ duration: 0.6 }}
            className="text-center"
          >
            <div className="inline-block mb-4 px-4 py-1.5 rounded-full border border-border bg-muted/50">
              <span className="text-sm">Protect. Track. Verify.</span>
            </div>
            <h1 className="text-5xl md:text-7xl font-bold mb-6 bg-gradient-to-br from-foreground to-foreground/60 bg-clip-text text-transparent">
              AI-Powered Digital Asset Protection
            </h1>
            <p className="text-xl text-muted-foreground mb-8 max-w-3xl mx-auto">
              Secure your sports media content with military-grade AI fingerprinting and invisible watermarking. Track unauthorized usage in real-time.
            </p>
            <div className="flex items-center justify-center gap-4">
              <Link to="/register">
                <Button size="lg" className="gap-2">
                  Start Protecting Assets <ArrowRight className="h-4 w-4" />
                </Button>
              </Link>
              <Link to="/demo">
                <Button size="lg" variant="outline">View Demo</Button>
              </Link>
            </div>
          </motion.div>
        </div>
      </section>

      <section className="py-20 px-6 bg-muted/30">
        <div className="container mx-auto max-w-6xl">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-8">
            {stats.map((stat, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.1 }}
                viewport={{ once: true }}
                className="text-center"
              >
                <div className="text-4xl font-bold mb-2">{stat.value}</div>
                <div className="text-sm text-muted-foreground">{stat.label}</div>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      <section className="py-20 px-6">
        <div className="container mx-auto max-w-6xl">
          <div className="text-center mb-16">
            <h2 className="text-4xl font-bold mb-4">Enterprise-Grade Protection</h2>
            <p className="text-xl text-muted-foreground">Everything you need to safeguard your digital assets</p>
          </div>
          <div className="grid md:grid-cols-2 gap-8">
            {features.map((feature, i) => {
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
                    <CardContent className="p-6">
                      <div className="rounded-lg bg-primary/10 w-12 h-12 flex items-center justify-center mb-4">
                        <Icon className="h-6 w-6 text-primary" />
                      </div>
                      <h3 className="text-xl font-semibold mb-2">{feature.title}</h3>
                      <p className="text-muted-foreground">{feature.description}</p>
                    </CardContent>
                  </Card>
                </motion.div>
              );
            })}
          </div>
        </div>
      </section>

      <section className="py-20 px-6 bg-muted/30">
        <div className="container mx-auto max-w-6xl">
          <div className="text-center mb-16">
            <h2 className="text-4xl font-bold mb-4">Trusted by Industry Leaders</h2>
            <p className="text-xl text-muted-foreground">See what organizations say about Nerox</p>
          </div>
          <div className="grid md:grid-cols-3 gap-8">
            {testimonials.map((testimonial, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.1 }}
                viewport={{ once: true }}
              >
                <Card>
                  <CardContent className="p-6">
                    <p className="text-muted-foreground mb-4">&ldquo;{testimonial.quote}&rdquo;</p>
                    <div>
                      <div className="font-semibold">{testimonial.company}</div>
                      <div className="text-sm text-muted-foreground">{testimonial.author}</div>
                    </div>
                  </CardContent>
                </Card>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      <section className="py-20 px-6">
        <div className="container mx-auto max-w-4xl text-center">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
          >
            <h2 className="text-4xl font-bold mb-4">Ready to Protect Your Assets?</h2>
            <p className="text-xl text-muted-foreground mb-8">
              Join leading sports media organizations using Nerox
            </p>
            <Link to="/register">
              <Button size="lg" className="gap-2">
                Start Free Trial <ArrowRight className="h-4 w-4" />
              </Button>
            </Link>
          </motion.div>
        </div>
      </section>

      <footer className="border-t border-border py-12 px-6">
        <div className="container mx-auto max-w-6xl">
          <div className="grid md:grid-cols-4 gap-8 mb-8">
            <div>
              <div className="flex items-center gap-2 mb-4">
                <Shield className="h-5 w-5" />
                <span className="font-semibold">Nerox</span>
              </div>
              <p className="text-sm text-muted-foreground">
                AI-powered digital asset protection for modern sports media.
              </p>
            </div>
            <div>
              <h4 className="font-semibold mb-3">Product</h4>
              <div className="space-y-2">
                <Link to="/features" className="block text-sm text-muted-foreground hover:text-primary">Features</Link>
                <Link to="/pricing" className="block text-sm text-muted-foreground hover:text-primary">Pricing</Link>
                <Link to="/demo" className="block text-sm text-muted-foreground hover:text-primary">Demo</Link>
              </div>
            </div>
            <div>
              <h4 className="font-semibold mb-3">Company</h4>
              <div className="space-y-2">
                <Link to="/about" className="block text-sm text-muted-foreground hover:text-primary">About</Link>
                <Link to="/contact" className="block text-sm text-muted-foreground hover:text-primary">Contact</Link>
              </div>
            </div>
            <div>
              <h4 className="font-semibold mb-3">Legal</h4>
              <div className="space-y-2">
                <a href="#" className="block text-sm text-muted-foreground hover:text-primary">Privacy</a>
                <a href="#" className="block text-sm text-muted-foreground hover:text-primary">Terms</a>
              </div>
            </div>
          </div>
          <div className="border-t border-border pt-8 text-center text-sm text-muted-foreground">
            © 2026 Nerox. All rights reserved.
          </div>
        </div>
      </footer>
    </div>
  );
}
