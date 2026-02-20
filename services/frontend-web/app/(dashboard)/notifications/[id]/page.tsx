'use client';

import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { ArrowLeft, Bell, CheckCheck, X, ExternalLink, ArchiveRestore } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { notificationsAPI, NotificationItem } from '@/lib/api/notifications';
import { TYPE_ICONS, TYPE_COLORS, timeAgo } from '@/lib/notification-utils';

const TYPE_LABELS: Record<string, string> = {
  urgent_feedback: 'Urgent Feedback',
  sentiment_spike: 'Sentiment Spike',
  churn_risk: 'Churn Risk',
  volume_spike: 'Volume Spike',
  customer_health_drop: 'Customer Health Drop',
};

const RISK_LEVEL_COLORS: Record<string, string> = {
  healthy: 'text-green-600 bg-green-50',
  moderate: 'text-yellow-600 bg-yellow-50',
  at_risk: 'text-orange-600 bg-orange-50',
  critical: 'text-destructive bg-destructive/10',
};

interface HealthDropMetadata {
  customer_email?: string;
  customer_name?: string;
  old_score?: number;
  new_score?: number;
  old_risk_level?: string;
  new_risk_level?: string;
  is_recovery?: boolean;
  components?: Record<string, number>;
  top_risk_drivers?: string[];
}

function formatScoreChange(old_score: number, new_score: number): string {
  const delta = new_score - old_score;
  const sign = delta >= 0 ? '+' : '';
  return `${old_score} → ${new_score} (${sign}${delta})`;
}

function HealthDropDetail({ metadata }: { metadata: HealthDropMetadata }) {
  const { old_score, new_score, new_risk_level, top_risk_drivers, components } = metadata;

  return (
    <div className="space-y-4">
      {old_score !== undefined && new_score !== undefined && (
        <div>
          <h3 className="text-sm font-medium text-muted-foreground mb-1">Score Change</h3>
          <p className="text-sm font-semibold text-foreground">
            {formatScoreChange(old_score, new_score)}
          </p>
        </div>
      )}

      {new_risk_level && (
        <div>
          <h3 className="text-sm font-medium text-muted-foreground mb-1">Risk Level</h3>
          <span
            data-testid="risk-level-badge"
            className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${RISK_LEVEL_COLORS[new_risk_level] || 'text-muted-foreground bg-muted'}`}
          >
            {new_risk_level}
          </span>
        </div>
      )}

      {top_risk_drivers && top_risk_drivers.length > 0 && (
        <div>
          <h3 className="text-sm font-medium text-muted-foreground mb-1">Top Risk Drivers</h3>
          <div className="flex flex-wrap gap-1.5">
            {top_risk_drivers.map(driver => (
              <span
                key={driver}
                className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-muted text-muted-foreground"
              >
                {driver}
              </span>
            ))}
          </div>
        </div>
      )}

      {components && Object.keys(components).length > 0 && (
        <div>
          <h3 className="text-sm font-medium text-muted-foreground mb-2">Component Breakdown</h3>
          <div className="grid grid-cols-2 gap-2">
            {Object.entries(components).map(([key, value]) => (
              <div
                key={key}
                data-testid={`component-${key}`}
                className="bg-muted/50 rounded-md px-3 py-2"
              >
                <p className="text-xs text-muted-foreground capitalize">{key.replace(/_/g, ' ')}</p>
                <p className="text-sm font-medium text-foreground mt-0.5">{value}</p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default function NotificationDetailPage() {
  const params = useParams();
  const router = useRouter();
  const [notification, setNotification] = useState<NotificationItem | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const id = Number(params.id);
    if (isNaN(id)) {
      setError('Invalid notification ID');
      setLoading(false);
      return;
    }

    const fetchNotification = async () => {
      try {
        const data = await notificationsAPI.getById(id);
        setNotification(data);
      } catch {
        setError('Notification not found');
      } finally {
        setLoading(false);
      }
    };

    fetchNotification();
  }, [params.id]);

  const handleDismiss = async () => {
    if (!notification) return;
    try {
      await notificationsAPI.dismiss(notification.id);
      router.push('/notifications');
    } catch {
      // ignore
    }
  };

  const handleRestore = async () => {
    if (!notification) return;
    try {
      await notificationsAPI.restore(notification.id);
      setNotification(prev => prev ? { ...prev, is_dismissed: false } : prev);
    } catch {
      // ignore
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24">
        <div className="relative w-8 h-8">
          <div className="absolute inset-0 border-2 border-primary/20 rounded-full" />
          <div className="absolute inset-0 border-2 border-primary border-t-transparent rounded-full animate-spin" />
        </div>
      </div>
    );
  }

  if (error || !notification) {
    return (
      <div className="p-6 max-w-2xl mx-auto">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => router.push('/notifications')}
          className="mb-6 flex items-center gap-2"
        >
          <ArrowLeft className="w-4 h-4" />
          Back to notifications
        </Button>
        <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
          <Bell className="w-12 h-12 mb-3 opacity-30" />
          <p className="font-medium text-lg">{error || 'Notification not found'}</p>
        </div>
      </div>
    );
  }

  const Icon = TYPE_ICONS[notification.type] || Bell;
  const iconColor = TYPE_COLORS[notification.type] || 'text-muted-foreground';
  const typeLabel = TYPE_LABELS[notification.type] || notification.type;

  return (
    <div className="p-6 max-w-2xl mx-auto space-y-6">
      {/* Back button */}
      <Button
        variant="ghost"
        size="sm"
        onClick={() => router.push('/notifications')}
        className="flex items-center gap-2"
      >
        <ArrowLeft className="w-4 h-4" />
        Back to notifications
      </Button>

      {/* Notification card */}
      <div className="rounded-lg border border-border overflow-hidden">
        {/* Header */}
        <div className="flex items-start gap-4 px-6 py-5 bg-muted/30">
          <div className={`mt-1 ${iconColor}`}>
            <Icon className="w-6 h-6" />
          </div>
          <div className="flex-1 min-w-0">
            <h1 className="text-lg font-semibold text-foreground">
              {notification.title}
            </h1>
            <div className="flex items-center gap-3 mt-1.5 text-sm text-muted-foreground">
              <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium ${iconColor} bg-muted`}>
                <Icon className="w-3 h-3" />
                {typeLabel}
              </span>
              <span>{timeAgo(notification.created_at)}</span>
              <span>{new Date(notification.created_at).toLocaleString()}</span>
            </div>
          </div>
        </div>

        {/* Body */}
        <div className="px-6 py-5 space-y-4">
          {notification.message && (
            <div>
              <h3 className="text-sm font-medium text-muted-foreground mb-1">Message</h3>
              <p className="text-sm text-foreground leading-relaxed">
                {notification.message}
              </p>
            </div>
          )}

          {notification.type === 'customer_health_drop' && notification.metadata ? (
            <HealthDropDetail metadata={notification.metadata as HealthDropMetadata} />
          ) : (
            notification.metadata && Object.keys(notification.metadata).length > 0 && (
              <div>
                <h3 className="text-sm font-medium text-muted-foreground mb-2">Details</h3>
                <div className="grid grid-cols-2 gap-3">
                  {Object.entries(notification.metadata).map(([key, value]) => (
                    <div key={key} className="bg-muted/50 rounded-md px-3 py-2">
                      <p className="text-xs text-muted-foreground capitalize">
                        {key.replace(/_/g, ' ')}
                      </p>
                      <p className="text-sm font-medium text-foreground mt-0.5">
                        {String(value)}
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            )
          )}

          {notification.link && (
            <div>
              <h3 className="text-sm font-medium text-muted-foreground mb-1">Related page</h3>
              {notification.type === 'customer_health_drop' ? (
                <Button
                  data-testid="view-customer-link"
                  variant="outline"
                  size="sm"
                  onClick={() => router.push(notification.link!)}
                  className="flex items-center gap-2"
                >
                  <ExternalLink className="w-3.5 h-3.5" />
                  View Customer Profile
                </Button>
              ) : (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => router.push(notification.link!)}
                  className="flex items-center gap-2"
                >
                  <ExternalLink className="w-3.5 h-3.5" />
                  Go to {notification.link}
                </Button>
              )}
            </div>
          )}
        </div>

        {/* Footer actions */}
        <div className="flex items-center justify-between px-6 py-3 border-t border-border bg-muted/20">
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            {notification.is_dismissed ? (
              <>
                <X className="w-4 h-4" />
                Dismissed
              </>
            ) : (
              <>
                <CheckCheck className="w-4 h-4" />
                Read
              </>
            )}
          </div>
          {notification.is_dismissed ? (
            <Button
              variant="outline"
              size="sm"
              onClick={handleRestore}
              className="flex items-center gap-2"
            >
              <ArchiveRestore className="w-4 h-4" />
              Restore
            </Button>
          ) : (
            <Button
              variant="outline"
              size="sm"
              onClick={handleDismiss}
              className="flex items-center gap-2 text-destructive hover:bg-destructive/10 border-destructive/30"
            >
              <X className="w-4 h-4" />
              Dismiss
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
