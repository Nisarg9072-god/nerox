import { motion } from 'motion/react';
import { Shield, Check } from 'lucide-react';
import { Link } from 'react-router';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card';
import { ThemeToggle } from '../components/ThemeToggle';

const plans = [
  {
    name: 'Starter',
    price: '$299',
    period: '/month',
    description: 'Perfect for small teams getting started',
    features: [
      'Up to 1,000 assets',
      'Basic AI fingerprinting',
      'Watermark embedding',
      'Platform monitoring',
      'Email support',
      'Monthly reports',
    ],
  },
  {
    name: 'Professional',
    price: '$899',
    period: '/month',
    description: 'For growing organizations',
    features: [
      'Up to 10,000 assets',
      'Advanced AI fingerprinting',
      'Invisible watermarking',
      'Real-time detection',
      'Priority support',
      'Custom reports',
      'API access',
      'Multi-user accounts',
    ],
    popular: true,
  },
  {
    name: 'Enterprise',
    price: 'Custom',
    period: '',
    description: 'For large-scale operations',
    features: [
      'Unlimited assets',
      'Custom AI models',
      'White-label solution',
      'Dedicated support team',
      'SLA guarantee',
      'Custom integrations',
      'Advanced analytics',
      'Compliance reports',
      'Training & onboarding',
    ],
  },
];

export default function Pricing() {
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
            <Link to="/pricing" className="text-sm hover:text-primary transition-colors font-medium">Pricing</Link>
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
              Simple, Transparent Pricing
            </h1>
            <p className="text-xl text-muted-foreground max-w-3xl mx-auto">
              Choose the plan that fits your organization's needs. All plans include a 14-day free trial.
            </p>
          </motion.div>

          <div className="grid md:grid-cols-3 gap-8 mb-16">
            {plans.map((plan, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.1 }}
                viewport={{ once: true }}
              >
                <Card className={`h-full ${plan.popular ? 'border-primary shadow-lg scale-105' : ''}`}>
                  {plan.popular && (
                    <div className="bg-primary text-primary-foreground text-center py-2 rounded-t-xl text-sm font-medium">
                      Most Popular
                    </div>
                  )}
                  <CardHeader>
                    <CardTitle>{plan.name}</CardTitle>
                    <CardDescription>{plan.description}</CardDescription>
                    <div className="pt-4">
                      <span className="text-4xl font-bold">{plan.price}</span>
                      <span className="text-muted-foreground">{plan.period}</span>
                    </div>
                  </CardHeader>
                  <CardContent>
                    <ul className="space-y-3 mb-6">
                      {plan.features.map((feature, j) => (
                        <li key={j} className="flex items-start gap-2">
                          <Check className="h-5 w-5 text-primary shrink-0 mt-0.5" />
                          <span className="text-sm">{feature}</span>
                        </li>
                      ))}
                    </ul>
                    <Link to="/register" className="block">
                      <Button className="w-full" variant={plan.popular ? 'default' : 'outline'}>
                        {plan.name === 'Enterprise' ? 'Contact Sales' : 'Start Free Trial'}
                      </Button>
                    </Link>
                  </CardContent>
                </Card>
              </motion.div>
            ))}
          </div>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            className="text-center"
          >
            <h2 className="text-3xl font-bold mb-8">Frequently Asked Questions</h2>
            <div className="grid md:grid-cols-2 gap-6 max-w-4xl mx-auto text-left">
              <Card>
                <CardContent className="p-6">
                  <h3 className="font-semibold mb-2">What's included in the free trial?</h3>
                  <p className="text-sm text-muted-foreground">
                    Full access to all features in your selected plan for 14 days. No credit card required.
                  </p>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="p-6">
                  <h3 className="font-semibold mb-2">Can I change plans later?</h3>
                  <p className="text-sm text-muted-foreground">
                    Yes, you can upgrade or downgrade your plan at any time. Changes take effect immediately.
                  </p>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="p-6">
                  <h3 className="font-semibold mb-2">What payment methods do you accept?</h3>
                  <p className="text-sm text-muted-foreground">
                    We accept all major credit cards, ACH transfers, and wire transfers for Enterprise plans.
                  </p>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="p-6">
                  <h3 className="font-semibold mb-2">Is there a setup fee?</h3>
                  <p className="text-sm text-muted-foreground">
                    No setup fees for Starter and Professional plans. Enterprise plans may include onboarding services.
                  </p>
                </CardContent>
              </Card>
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
