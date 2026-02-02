'use client';

import { Suspense, useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { Card, CardHeader, CardContent, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { Badge } from '@/components/ui/badge';
import {
  billingAPI,
  Plan,
  Subscription,
  Usage,
  Invoice,
  formatPrice,
  getStatusColor,
  getStatusLabel,
  canUpgrade,
  BILLING_CYCLES,
} from '@/lib/api/billing';
import {
  Crown,
  Zap,
  Building2,
  Sparkles,
  Check,
  X,
  ArrowRight,
  ExternalLink,
  Receipt,
  Clock,
  AlertTriangle,
  MessageSquare,
  Users,
  Loader2,
  Settings as SettingsIcon,
} from 'lucide-react';
import { SettingsTabs } from '@/components/SettingsTabs';
import { toast } from 'sonner';

function BillingPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [loading, setLoading] = useState(true);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [subscription, setSubscription] = useState<Subscription | null>(null);
  const [usage, setUsage] = useState<Usage | null>(null);
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [canManageBilling, setCanManageBilling] = useState(false);
  const [billingCycle, setBillingCycle] = useState<'monthly' | 'annual'>('monthly');
  const [checkoutLoading, setCheckoutLoading] = useState<string | null>(null);
  const [portalLoading, setPortalLoading] = useState(false);
  const [trialLoading, setTrialLoading] = useState(false);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const token = localStorage.getItem('access_token');
        if (!token) {
          router.push('/login');
          return;
        }

        // Check if returning from successful checkout
        const isSuccess = searchParams.get('success') === 'true';

        if (isSuccess) {
          // Sync subscription from Stripe to update local database
          try {
            const syncRes = await billingAPI.syncSubscription();
            setSubscription(syncRes.subscription);
            setCanManageBilling(syncRes.can_manage_billing);
            toast.success('Subscription updated successfully!');

            // Clear the URL params after sync
            router.replace('/settings/billing');
          } catch (syncErr) {
            console.error('Failed to sync subscription:', syncErr);
            toast.error('Failed to sync subscription');
          }
        }

        const [plansRes, subRes, usageRes, invoicesRes] = await Promise.all([
          billingAPI.getPlans(),
          isSuccess ? Promise.resolve(null) : billingAPI.getSubscription(), // Skip if already synced
          billingAPI.getUsage(),
          billingAPI.getInvoices(),
        ]);

        setPlans(plansRes.plans);
        if (subRes) {
          setSubscription(subRes.subscription);
          setCanManageBilling(subRes.can_manage_billing);
        }
        setUsage(usageRes);
        setInvoices(invoicesRes.invoices);
      } catch (err) {
        console.error('Failed to load billing data:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, [router, searchParams]);

  const handleStartTrial = async () => {
    setTrialLoading(true);
    try {
      const result = await billingAPI.startTrial({ plan: 'pro' });
      setSubscription(result.subscription);
    } catch (err) {
      console.error('Failed to start trial:', err);
    } finally {
      setTrialLoading(false);
    }
  };

  const handleCheckout = async (plan: string) => {
    setCheckoutLoading(plan);
    try {
      const result = await billingAPI.createCheckout({
        plan,
        billing_cycle: billingCycle,
        success_url: `${window.location.origin}/settings/billing?success=true`,
        cancel_url: `${window.location.origin}/settings/billing?canceled=true`,
      });
      window.location.href = result.checkout_url;
    } catch (err) {
      console.error('Failed to create checkout:', err);
      setCheckoutLoading(null);
    }
  };

  const handleManageBilling = async () => {
    setPortalLoading(true);
    try {
      const result = await billingAPI.createPortal({
        return_url: window.location.href,
      });
      window.location.href = result.portal_url;
    } catch (err) {
      console.error('Failed to open billing portal:', err);
      setPortalLoading(false);
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

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="flex flex-col items-center space-y-4">
          <div className="relative w-16 h-16">
            <div className="absolute inset-0 border-4 border-primary/20 rounded-full"></div>
            <div className="absolute inset-0 border-4 border-primary border-t-transparent rounded-full animate-spin"></div>
          </div>
          <p className="text-muted-foreground font-medium">Loading billing...</p>
        </div>
      </div>
    );
  }

  const currentPlan = plans.find(p => p.id === subscription?.plan) || plans[0];

  return (
    <div className="min-h-screen pattern-bg">
      <main className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
        {/* Header */}
        <div className="animate-fade-in">
          <div className="flex items-center space-x-3 mb-6">
            <div className="p-3 bg-secondary rounded-xl">
              <SettingsIcon className="w-8 h-8 text-primary" />
            </div>
            <div>
              <h1 className="text-4xl font-bold text-foreground">Settings</h1>
              <p className="text-muted-foreground text-lg">Manage your organization and preferences</p>
            </div>
          </div>

          {/* Settings Tabs */}
          <SettingsTabs />
        </div>

        {/* Current Subscription Card */}
        <Card className="animate-slide-up stagger-1">
          <CardHeader className="border-b border-border">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-2">
                <div className="p-2 bg-secondary rounded-lg">
                  <Crown className="w-5 h-5 text-primary" />
                </div>
                <div>
                  <CardTitle>Current Plan</CardTitle>
                  <CardDescription>Your subscription details</CardDescription>
                </div>
              </div>
              {canManageBilling && subscription?.stripe_subscription_id && (
                <Button
                  onClick={handleManageBilling}
                  variant="outline"
                  disabled={portalLoading}
                >
                  {portalLoading ? (
                    <Loader2 className="w-4 h-4 animate-spin mr-2" />
                  ) : (
                    <ExternalLink className="w-4 h-4 mr-2" />
                  )}
                  Manage Billing
                </Button>
              )}
            </div>
          </CardHeader>
          <CardContent className="pt-6">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              {/* Plan Info */}
              <div className="space-y-2">
                <p className="text-sm font-medium text-muted-foreground uppercase tracking-wider">Plan</p>
                <div className="flex items-center gap-2">
                  {(() => {
                    const Icon = getPlanIcon(currentPlan.id);
                    return <Icon className="w-5 h-5 text-primary" />;
                  })()}
                  <span className="text-2xl font-bold text-foreground">{currentPlan.name}</span>
                </div>
                {subscription?.billing_cycle && (
                  <p className="text-sm text-muted-foreground capitalize">
                    {subscription.billing_cycle} billing
                  </p>
                )}
              </div>

              {/* Status */}
              <div className="space-y-2">
                <p className="text-sm font-medium text-muted-foreground uppercase tracking-wider">Status</p>
                <div className="flex items-center gap-2">
                  <Badge className={getStatusColor(subscription?.status || 'active')}>
                    {getStatusLabel(subscription?.status || 'active')}
                  </Badge>
                  {subscription?.is_trial && subscription.trial_days_remaining !== null && (
                    <span className="text-sm text-muted-foreground">
                      ({subscription.trial_days_remaining} days left)
                    </span>
                  )}
                </div>
                {subscription?.cancel_at_period_end && (
                  <p className="text-sm text-amber-600 flex items-center gap-1">
                    <AlertTriangle className="w-4 h-4" />
                    Cancels at period end
                  </p>
                )}
              </div>

              {/* Renewal */}
              <div className="space-y-2">
                <p className="text-sm font-medium text-muted-foreground uppercase tracking-wider">
                  {subscription?.is_trial ? 'Trial Ends' : 'Next Renewal'}
                </p>
                <div className="flex items-center gap-2">
                  <Clock className="w-5 h-5 text-muted-foreground" />
                  <span className="text-foreground font-medium">
                    {subscription?.is_trial && subscription.trial_end
                      ? new Date(subscription.trial_end).toLocaleDateString('en-US', {
                          month: 'long',
                          day: 'numeric',
                          year: 'numeric',
                        })
                      : subscription?.current_period_end
                      ? new Date(subscription.current_period_end).toLocaleDateString('en-US', {
                          month: 'long',
                          day: 'numeric',
                          year: 'numeric',
                        })
                      : 'N/A'}
                  </span>
                </div>
              </div>
            </div>

            {/* Trial CTA for free users */}
            {subscription?.plan === 'free' && !subscription.is_trial && (
              <div className="mt-6 p-4 bg-primary/5 border border-primary/20 rounded-xl">
                <div className="flex items-center justify-between">
                  <div>
                    <h4 className="font-semibold text-foreground">Try Pro for Free</h4>
                    <p className="text-sm text-muted-foreground">
                      Start a 14-day trial of Pro features. No credit card required.
                    </p>
                  </div>
                  <Button onClick={handleStartTrial} disabled={trialLoading}>
                    {trialLoading ? (
                      <Loader2 className="w-4 h-4 animate-spin mr-2" />
                    ) : (
                      <Sparkles className="w-4 h-4 mr-2" />
                    )}
                    Start Free Trial
                  </Button>
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Usage Card */}
        {usage && (
          <Card className="animate-slide-up stagger-2">
            <CardHeader className="border-b border-border">
              <div className="flex items-center space-x-2">
                <div className="p-2 bg-secondary rounded-lg">
                  <MessageSquare className="w-5 h-5 text-primary" />
                </div>
                <div>
                  <CardTitle>Usage This Period</CardTitle>
                  <CardDescription>
                    {new Date(usage.period_start).toLocaleDateString()} - {new Date(usage.period_end).toLocaleDateString()}
                  </CardDescription>
                </div>
              </div>
            </CardHeader>
            <CardContent className="pt-6">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                {/* Feedback Usage */}
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <MessageSquare className="w-4 h-4 text-muted-foreground" />
                      <span className="font-medium text-foreground">Feedback Processed</span>
                    </div>
                    <span className="text-sm text-muted-foreground">
                      {usage.feedback_used.toLocaleString()} / {usage.feedback_limit?.toLocaleString() || 'Unlimited'}
                    </span>
                  </div>
                  <Progress
                    value={usage.feedback_percentage}
                    className={`h-3 ${usage.feedback_percentage >= 90 ? '[&>div]:bg-destructive' : usage.feedback_percentage >= 75 ? '[&>div]:bg-amber-500' : ''}`}
                  />
                  {usage.feedback_percentage >= 80 && usage.feedback_limit && (
                    <p className="text-sm text-amber-600 flex items-center gap-1">
                      <AlertTriangle className="w-4 h-4" />
                      {usage.feedback_percentage >= 100
                        ? `Limit reached! ${usage.overage_count} overage items.`
                        : `Approaching limit (${usage.feedback_percentage.toFixed(0)}% used)`}
                    </p>
                  )}
                </div>

                {/* Seats Usage */}
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Users className="w-4 h-4 text-muted-foreground" />
                      <span className="font-medium text-foreground">Team Seats</span>
                    </div>
                    <span className="text-sm text-muted-foreground">
                      {usage.seats_used} / {usage.seats_limit || 'Unlimited'}
                    </span>
                  </div>
                  <Progress
                    value={usage.seats_percentage}
                    className={`h-3 ${usage.seats_percentage >= 90 ? '[&>div]:bg-destructive' : usage.seats_percentage >= 75 ? '[&>div]:bg-amber-500' : ''}`}
                  />
                </div>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Plan Comparison */}
        <div className="animate-slide-up stagger-3">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-2xl font-bold text-foreground">Compare Plans</h2>
            <div className="flex items-center gap-2 p-1 bg-secondary rounded-lg">
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
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {plans.map((plan) => {
              const Icon = getPlanIcon(plan.id);
              // Check if this is the current plan AND matches the billing cycle being viewed
              const isCurrentPlan = plan.id === subscription?.plan;
              const isCurrentBillingCycle = subscription?.billing_cycle === billingCycle || !subscription?.billing_cycle;
              const isCurrent = isCurrentPlan && isCurrentBillingCycle;
              const showUpgrade = canUpgrade(subscription?.plan || 'free', plan.id);
              const price = billingCycle === 'annual' ? plan.price_annual : plan.price_monthly;

              return (
                <Card
                  key={plan.id}
                  className={`relative transition-all ${
                    isCurrent
                      ? 'ring-2 ring-primary !bg-primary/15 dark:!bg-primary/25'
                      : 'hover:border-primary/50'
                  } ${plan.is_popular && !isCurrent ? 'border-primary' : ''}`}
                >
                  {plan.is_popular && (
                    <div className="absolute -top-3 left-1/2 -translate-x-1/2">
                      <Badge className="bg-primary text-primary-foreground">Most Popular</Badge>
                    </div>
                  )}
                  <CardHeader className="pb-4">
                    <div className="flex items-center gap-2 mb-2">
                      <Icon className="w-5 h-5 text-primary" />
                      <CardTitle className="text-lg">{plan.name}</CardTitle>
                    </div>
                    <div className="flex items-baseline gap-1">
                      <span className={`font-bold text-foreground ${price === null ? 'text-xl' : 'text-3xl'}`}>
                        {formatPrice(price)}
                      </span>
                      {price !== null && (
                        <span className="text-muted-foreground">/{billingCycle === 'annual' ? 'year' : 'month'}</span>
                      )}
                    </div>
                    <CardDescription>{plan.description}</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-4">
                      {/* Limits */}
                      <div className="space-y-2 pb-4 border-b border-border">
                        <div className="flex items-center gap-2 text-sm">
                          <MessageSquare className="w-4 h-4 text-muted-foreground" />
                          <span className="text-foreground">
                            {plan.feedback_limit?.toLocaleString() || 'Unlimited'} feedback/mo
                          </span>
                        </div>
                        <div className="flex items-center gap-2 text-sm">
                          <Users className="w-4 h-4 text-muted-foreground" />
                          <span className="text-foreground">
                            {plan.seat_limit || 'Unlimited'} team seats
                          </span>
                        </div>
                      </div>

                      {/* Features */}
                      <ul className="space-y-2">
                        {plan.features.slice(0, 5).map((feature) => (
                          <li key={feature.id} className="flex items-start gap-2 text-sm">
                            {feature.included ? (
                              <Check className="w-4 h-4 text-green-500 mt-0.5 shrink-0" />
                            ) : (
                              <X className="w-4 h-4 text-muted-foreground mt-0.5 shrink-0" />
                            )}
                            <span className={feature.included ? 'text-foreground' : 'text-muted-foreground'}>
                              {feature.name}
                            </span>
                          </li>
                        ))}
                      </ul>

                      {/* CTA */}
                      <div className="pt-4">
                        {isCurrent ? (
                          <Button variant="outline" className="w-full text-primary cursor-default hover:bg-transparent hover:text-primary">
                            <Check className="w-4 h-4 mr-2" />
                            Current Plan
                          </Button>
                        ) : plan.id === 'enterprise' ? (
                          <Button variant="outline" className="w-full" asChild>
                            <a href="mailto:sales@rereflect.com">
                              Contact Sales
                              <ArrowRight className="w-4 h-4 ml-2" />
                            </a>
                          </Button>
                        ) : showUpgrade ? (
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
                        ) : (
                          <Button variant="outline" className="w-full" onClick={handleManageBilling}>
                            Downgrade
                          </Button>
                        )}
                      </div>
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        </div>

        {/* Invoice History */}
        {invoices.length > 0 && (
          <Card className="animate-slide-up stagger-4">
            <CardHeader className="border-b border-border">
              <div className="flex items-center space-x-2">
                <div className="p-2 bg-secondary rounded-lg">
                  <Receipt className="w-5 h-5 text-primary" />
                </div>
                <div>
                  <CardTitle>Invoice History</CardTitle>
                  <CardDescription>Your recent invoices and payments</CardDescription>
                </div>
              </div>
            </CardHeader>
            <CardContent className="pt-6">
              <div className="space-y-3">
                {invoices.map((invoice) => (
                  <div
                    key={invoice.id}
                    className="flex items-center justify-between p-4 border border-border rounded-lg hover:bg-secondary/50 transition-colors"
                  >
                    <div className="flex items-center gap-4">
                      <div className="p-2 bg-secondary rounded-lg">
                        <Receipt className="w-4 h-4 text-muted-foreground" />
                      </div>
                      <div>
                        <p className="font-medium text-foreground">
                          Invoice {invoice.number || invoice.id.slice(0, 8)}
                        </p>
                        <p className="text-sm text-muted-foreground">
                          {new Date(invoice.created).toLocaleDateString('en-US', {
                            month: 'short',
                            day: 'numeric',
                            year: 'numeric',
                          })}
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-4">
                      <div className="text-right">
                        <p className="font-medium text-foreground">
                          ${(invoice.amount_paid / 100).toFixed(2)}
                        </p>
                        <Badge
                          variant="outline"
                          className={
                            invoice.status === 'paid'
                              ? 'text-green-600 border-green-600/30 bg-green-50 dark:bg-green-950'
                              : invoice.status === 'open'
                              ? 'text-yellow-600 border-yellow-600/30 bg-yellow-50 dark:bg-yellow-950'
                              : 'text-muted-foreground'
                          }
                        >
                          {invoice.status}
                        </Badge>
                      </div>
                      {invoice.hosted_invoice_url && (
                        <Button variant="ghost" size="sm" asChild>
                          <a href={invoice.hosted_invoice_url} target="_blank" rel="noopener noreferrer">
                            <ExternalLink className="w-4 h-4" />
                          </a>
                        </Button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        )}
      </main>
    </div>
  );
}

export default function BillingPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen flex items-center justify-center">
          <div className="flex flex-col items-center space-y-4">
            <div className="relative w-16 h-16">
              <div className="absolute inset-0 border-4 border-primary/20 rounded-full"></div>
              <div className="absolute inset-0 border-4 border-primary border-t-transparent rounded-full animate-spin"></div>
            </div>
            <p className="text-muted-foreground font-medium">Loading billing...</p>
          </div>
        </div>
      }
    >
      <BillingPageContent />
    </Suspense>
  );
}
