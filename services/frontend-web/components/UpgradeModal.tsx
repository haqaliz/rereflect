'use client';

import { useState, useEffect } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  billingAPI,
  Plan,
  formatPrice,
  canUpgrade,
  BILLING_CYCLES,
} from '@/lib/api/billing';
import {
  Crown,
  Zap,
  Building2,
  Sparkles,
  Check,
  MessageSquare,
  Users,
  Loader2,
  ArrowRight,
} from 'lucide-react';

interface UpgradeModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  currentPlan?: string;
  reason?: 'feedback_limit' | 'seat_limit' | 'feature' | 'general';
  featureName?: string;
}

export function UpgradeModal({
  open,
  onOpenChange,
  currentPlan = 'free',
  reason = 'general',
  featureName,
}: UpgradeModalProps) {
  const [plans, setPlans] = useState<Plan[]>([]);
  const [loading, setLoading] = useState(true);
  const [billingCycle, setBillingCycle] = useState<'monthly' | 'annual'>('monthly');
  const [checkoutLoading, setCheckoutLoading] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      const fetchPlans = async () => {
        try {
          const response = await billingAPI.getPlans();
          setPlans(response.plans);
        } catch (err) {
          console.error('Failed to fetch plans:', err);
        } finally {
          setLoading(false);
        }
      };
      fetchPlans();
    }
  }, [open]);

  const handleCheckout = async (plan: string) => {
    setCheckoutLoading(plan);
    try {
      const result = await billingAPI.createCheckout({
        plan,
        billing_cycle: billingCycle,
        success_url: `${window.location.origin}/settings/billing?success=true`,
        cancel_url: window.location.href,
      });
      window.location.href = result.checkout_url;
    } catch (err) {
      console.error('Failed to create checkout:', err);
      setCheckoutLoading(null);
    }
  };

  const getPlanIcon = (planId: string) => {
    switch (planId) {
      case 'free':
        return Zap;
      case 'pro':
        return Crown;
      case 'business':
        return Building2;
      case 'enterprise':
        return Sparkles;
      default:
        return Zap;
    }
  };

  const getReasonMessage = () => {
    switch (reason) {
      case 'feedback_limit':
        return "You've reached your feedback limit for this month.";
      case 'seat_limit':
        return "You've reached your team seat limit.";
      case 'feature':
        return featureName
          ? `${featureName} requires a higher plan.`
          : 'This feature requires a higher plan.';
      default:
        return 'Unlock more features with an upgraded plan.';
    }
  };

  // Filter to show only upgradeable plans
  const upgradePlans = plans.filter(
    (p) => p.id !== 'free' && canUpgrade(currentPlan, p.id)
  );

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle className="text-2xl">Upgrade Your Plan</DialogTitle>
          <DialogDescription>{getReasonMessage()}</DialogDescription>
        </DialogHeader>

        {loading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="w-8 h-8 animate-spin text-primary" />
          </div>
        ) : (
          <div className="space-y-6 py-4">
            {/* Billing cycle toggle */}
            <div className="flex items-center justify-center gap-2 p-1 bg-secondary rounded-lg w-fit mx-auto">
              {BILLING_CYCLES.map((cycle) => (
                <button
                  key={cycle.value}
                  onClick={() => setBillingCycle(cycle.value as 'monthly' | 'annual')}
                  className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                    billingCycle === cycle.value
                      ? 'bg-background text-foreground shadow-sm'
                      : 'text-muted-foreground hover:text-foreground'
                  }`}
                >
                  {cycle.label}
                  {cycle.discount && (
                    <span className="ml-2 text-xs text-green-600">{cycle.discount}</span>
                  )}
                </button>
              ))}
            </div>

            {/* Plans grid */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {upgradePlans.map((plan) => {
                const Icon = getPlanIcon(plan.id);
                const price =
                  billingCycle === 'annual' ? plan.price_annual : plan.price_monthly;

                return (
                  <div
                    key={plan.id}
                    className={`relative rounded-xl border p-5 ${
                      plan.is_popular ? 'border-primary ring-2 ring-primary/20' : 'border-border'
                    }`}
                  >
                    {plan.is_popular && (
                      <div className="absolute -top-3 left-1/2 -translate-x-1/2">
                        <Badge className="bg-primary text-primary-foreground">Popular</Badge>
                      </div>
                    )}

                    <div className="flex items-center gap-2 mb-3">
                      <Icon className="w-5 h-5 text-primary" />
                      <h3 className="font-semibold text-foreground">{plan.name}</h3>
                    </div>

                    <div className="flex items-baseline gap-1 mb-4">
                      <span className="text-2xl font-bold text-foreground">
                        {formatPrice(price)}
                      </span>
                      {price !== null && (
                        <span className="text-sm text-muted-foreground">
                          /{billingCycle === 'annual' ? 'year' : 'mo'}
                        </span>
                      )}
                    </div>

                    {/* Limits */}
                    <div className="space-y-2 mb-4 pb-4 border-b border-border">
                      <div className="flex items-center gap-2 text-sm">
                        <MessageSquare className="w-4 h-4 text-muted-foreground" />
                        <span className="text-foreground">
                          {plan.feedback_limit?.toLocaleString() || 'Unlimited'} feedback
                        </span>
                      </div>
                      <div className="flex items-center gap-2 text-sm">
                        <Users className="w-4 h-4 text-muted-foreground" />
                        <span className="text-foreground">
                          {plan.seat_limit || 'Unlimited'} seats
                        </span>
                      </div>
                    </div>

                    {/* Key features */}
                    <ul className="space-y-2 mb-4">
                      {plan.features.slice(0, 4).map((feature) => (
                        <li key={feature.id} className="flex items-start gap-2 text-sm">
                          <Check className="w-4 h-4 text-green-500 mt-0.5 shrink-0" />
                          <span className="text-foreground">{feature.name}</span>
                        </li>
                      ))}
                    </ul>

                    {/* CTA */}
                    {plan.id === 'enterprise' ? (
                      <Button variant="outline" className="w-full" asChild>
                        <a href="mailto:sales@rereflect.com">
                          Contact Sales
                          <ArrowRight className="w-4 h-4 ml-2" />
                        </a>
                      </Button>
                    ) : (
                      <Button
                        className="w-full"
                        onClick={() => handleCheckout(plan.id)}
                        disabled={checkoutLoading === plan.id}
                      >
                        {checkoutLoading === plan.id ? (
                          <Loader2 className="w-4 h-4 animate-spin mr-2" />
                        ) : null}
                        Upgrade to {plan.name}
                      </Button>
                    )}
                  </div>
                );
              })}
            </div>

            <p className="text-center text-sm text-muted-foreground">
              Questions? Contact us at{' '}
              <a href="mailto:support@rereflect.com" className="text-primary hover:underline">
                support@rereflect.com
              </a>
            </p>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
