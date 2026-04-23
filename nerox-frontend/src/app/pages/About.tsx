import { motion } from 'motion/react';
import { Shield, Target, Users, Zap } from 'lucide-react';
import { Link } from 'react-router';
import { Button } from '../components/ui/button';
import { Card, CardContent } from '../components/ui/card';
import { ThemeToggle } from '../components/ThemeToggle';

const values = [
  {
    icon: Shield,
    title: 'Security First',
    description: 'We prioritize the protection of your digital assets above all else.',
  },
  {
    icon: Target,
    title: 'Innovation',
    description: 'Constantly evolving our AI technology to stay ahead of piracy threats.',
  },
  {
    icon: Users,
    title: 'Customer Focus',
    description: 'Your success is our success. We build solutions that work for you.',
  },
  {
    icon: Zap,
    title: 'Performance',
    description: 'Lightning-fast detection and verification without compromise.',
  },
];

export default function About() {
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
            <Link to="/about" className="text-sm hover:text-primary transition-colors font-medium">About</Link>
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
              About Nerox
            </h1>
            <p className="text-xl text-muted-foreground max-w-3xl mx-auto">
              We're on a mission to protect the digital assets of sports media organizations worldwide through cutting-edge AI technology.
            </p>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            className="mb-20"
          >
            <Card className="border-none bg-gradient-to-br from-primary/10 to-primary/5">
              <CardContent className="p-12">
                <h2 className="text-3xl font-bold mb-6">Our Story</h2>
                <div className="space-y-4 text-muted-foreground">
                  <p>
                    Nerox was founded in 2023 by a team of AI researchers and sports media professionals who saw firsthand how digital piracy was impacting the industry. We realized that traditional protection methods were no longer effective against modern piracy techniques.
                  </p>
                  <p>
                    We set out to build a solution that combines the latest advances in artificial intelligence, computer vision, and blockchain technology to create an unbreakable shield for digital assets.
                  </p>
                  <p>
                    Today, Nerox protects over 50 million assets for leading sports organizations worldwide, detecting and preventing unauthorized usage in real-time across hundreds of platforms.
                  </p>
                </div>
              </CardContent>
            </Card>
          </motion.div>

          <div className="mb-20">
            <h2 className="text-3xl font-bold text-center mb-12">Our Values</h2>
            <div className="grid md:grid-cols-2 gap-8">
              {values.map((value, i) => {
                const Icon = value.icon;
                return (
                  <motion.div
                    key={i}
                    initial={{ opacity: 0, y: 20 }}
                    whileInView={{ opacity: 1, y: 0 }}
                    transition={{ delay: i * 0.1 }}
                    viewport={{ once: true }}
                  >
                    <Card>
                      <CardContent className="p-6">
                        <div className="rounded-lg bg-primary/10 w-12 h-12 flex items-center justify-center mb-4">
                          <Icon className="h-6 w-6 text-primary" />
                        </div>
                        <h3 className="text-xl font-semibold mb-2">{value.title}</h3>
                        <p className="text-muted-foreground">{value.description}</p>
                      </CardContent>
                    </Card>
                  </motion.div>
                );
              })}
            </div>
          </div>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            className="text-center"
          >
            <h2 className="text-3xl font-bold mb-6">Join Us in Protecting Digital Assets</h2>
            <p className="text-xl text-muted-foreground mb-8 max-w-2xl mx-auto">
              Whether you're a sports league, broadcaster, or media organization, we're here to help you protect what matters most.
            </p>
            <Link to="/contact">
              <Button size="lg">Get in Touch</Button>
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
