import { motion } from 'motion/react';
import { Shield, Mail, MapPin, Phone } from 'lucide-react';
import { Link } from 'react-router';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Card, CardContent } from '../components/ui/card';
import { ThemeToggle } from '../components/ThemeToggle';
import { Textarea } from '../components/ui/textarea';
import { useState } from 'react';

export default function Contact() {
  const [submitted, setSubmitted] = useState(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitted(true);
    setTimeout(() => setSubmitted(false), 3000);
  };

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
            <Link to="/contact" className="text-sm hover:text-primary transition-colors font-medium">Contact</Link>
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
              Get in Touch
            </h1>
            <p className="text-xl text-muted-foreground max-w-3xl mx-auto">
              Have questions? We'd love to hear from you. Send us a message and we'll respond as soon as possible.
            </p>
          </motion.div>

          <div className="grid md:grid-cols-3 gap-8 mb-16">
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
            >
              <Card>
                <CardContent className="p-6 text-center">
                  <div className="rounded-lg bg-primary/10 w-12 h-12 flex items-center justify-center mx-auto mb-4">
                    <Mail className="h-6 w-6 text-primary" />
                  </div>
                  <h3 className="font-semibold mb-2">Email</h3>
                  <p className="text-sm text-muted-foreground">contact@nerox.ai</p>
                </CardContent>
              </Card>
            </motion.div>

            <motion.div
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.1 }}
              viewport={{ once: true }}
            >
              <Card>
                <CardContent className="p-6 text-center">
                  <div className="rounded-lg bg-primary/10 w-12 h-12 flex items-center justify-center mx-auto mb-4">
                    <Phone className="h-6 w-6 text-primary" />
                  </div>
                  <h3 className="font-semibold mb-2">Phone</h3>
                  <p className="text-sm text-muted-foreground">+1 (555) 123-4567</p>
                </CardContent>
              </Card>
            </motion.div>

            <motion.div
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.2 }}
              viewport={{ once: true }}
            >
              <Card>
                <CardContent className="p-6 text-center">
                  <div className="rounded-lg bg-primary/10 w-12 h-12 flex items-center justify-center mx-auto mb-4">
                    <MapPin className="h-6 w-6 text-primary" />
                  </div>
                  <h3 className="font-semibold mb-2">Office</h3>
                  <p className="text-sm text-muted-foreground">San Francisco, CA</p>
                </CardContent>
              </Card>
            </motion.div>
          </div>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            className="max-w-2xl mx-auto"
          >
            <Card>
              <CardContent className="p-8">
                <h2 className="text-2xl font-bold mb-6">Send us a message</h2>
                <form onSubmit={handleSubmit} className="space-y-6">
                  <div className="grid md:grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm mb-2">Name</label>
                      <Input placeholder="Your name" required />
                    </div>
                    <div>
                      <label className="block text-sm mb-2">Email</label>
                      <Input type="email" placeholder="your@email.com" required />
                    </div>
                  </div>
                  <div>
                    <label className="block text-sm mb-2">Company</label>
                    <Input placeholder="Your company name" />
                  </div>
                  <div>
                    <label className="block text-sm mb-2">Subject</label>
                    <Input placeholder="How can we help?" required />
                  </div>
                  <div>
                    <label className="block text-sm mb-2">Message</label>
                    <Textarea
                      placeholder="Tell us more about your needs..."
                      className="min-h-[150px]"
                      required
                    />
                  </div>
                  <Button type="submit" size="lg" className="w-full">
                    {submitted ? 'Message Sent!' : 'Send Message'}
                  </Button>
                </form>
              </CardContent>
            </Card>
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
