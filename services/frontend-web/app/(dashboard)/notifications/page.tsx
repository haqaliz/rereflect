'use client';

import { useEffect, useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { Bell, CheckCheck, X, Settings, ArchiveRestore } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { notificationsAPI, NotificationItem } from '@/lib/api/notifications';
import { TYPE_ICONS, TYPE_COLORS, timeAgo } from '@/lib/notification-utils';

const TYPE_FILTERS = [
  { label: 'All', value: undefined },
  { label: 'Urgent', value: 'urgent_feedback' },
  { label: 'Sentiment', value: 'sentiment_spike' },
  { label: 'Churn', value: 'churn_risk' },
  { label: 'Volume', value: 'volume_spike' },
] as const;

const PAGE_SIZE = 20;

export default function NotificationsPage() {
  const router = useRouter();
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [filterType, setFilterType] = useState<string | undefined>(undefined);
  const [showDismissed, setShowDismissed] = useState(false);

  const fetchNotifications = useCallback(async (p: number = 1, type?: string, dismissed?: boolean) => {
    try {
      const data = await notificationsAPI.list({
        page: p,
        page_size: PAGE_SIZE,
        type,
        dismissed,
      });
      if (p === 1) {
        setNotifications(data.items);
      } else {
        setNotifications(prev => [...prev, ...data.items]);
      }
      setTotal(data.total);
    } catch (err) {
      console.error('Failed to load notifications:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    setLoading(true);
    setPage(1);
    fetchNotifications(1, filterType, showDismissed);
  }, [filterType, showDismissed, fetchNotifications]);

  const handleMarkAllRead = async () => {
    try {
      await notificationsAPI.markAllRead();
      setNotifications(prev => prev.map(n => ({ ...n, is_read: true })));
    } catch (err) {
      console.error('Failed to mark all read:', err);
    }
  };

  const handleDismiss = async (e: React.MouseEvent, id: number) => {
    e.stopPropagation();
    try {
      await notificationsAPI.dismiss(id);
      setNotifications(prev => prev.filter(n => n.id !== id));
      setTotal(prev => prev - 1);
    } catch (err) {
      console.error('Failed to dismiss:', err);
    }
  };

  const handleClick = (notification: NotificationItem) => {
    router.push(`/notifications/${notification.id}`);
  };

  const handleLoadMore = () => {
    const nextPage = page + 1;
    setPage(nextPage);
    fetchNotifications(nextPage, filterType, showDismissed);
  };

  const handleToggleDismissed = () => {
    setShowDismissed(prev => !prev);
    setFilterType(undefined);
  };

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Notifications</h1>
          <p className="text-sm text-muted-foreground mt-1">
            {showDismissed ? `${total} dismissed` : `${total} notification${total !== 1 ? 's' : ''}`}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {!showDismissed && (
            <Button
              variant="outline"
              size="sm"
              onClick={handleMarkAllRead}
              className="flex items-center gap-2"
            >
              <CheckCheck className="w-4 h-4" />
              Mark all read
            </Button>
          )}
          <Button
            variant={showDismissed ? 'default' : 'ghost'}
            size="sm"
            onClick={handleToggleDismissed}
            className="flex items-center gap-2"
          >
            <ArchiveRestore className="w-4 h-4" />
            {showDismissed ? 'Show active' : 'Dismissed'}
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => router.push('/settings/notifications')}
            className="flex items-center gap-2"
          >
            <Settings className="w-4 h-4" />
            Preferences
          </Button>
        </div>
      </div>

      {/* Filter pills */}
      <div className="flex gap-2">
        {TYPE_FILTERS.map(opt => (
          <button
            key={opt.label}
            onClick={() => setFilterType(opt.value)}
            className={`px-3 py-1.5 rounded-full text-xs font-medium whitespace-nowrap transition-colors ${
              filterType === opt.value
                ? 'bg-primary text-primary-foreground'
                : 'bg-muted text-muted-foreground hover:bg-muted/80'
            }`}
          >
            {opt.label}
          </button>
        ))}
      </div>

      {/* Notification List */}
      <div className="rounded-lg border border-border overflow-hidden">
        {loading && notifications.length === 0 ? (
          <div className="flex items-center justify-center py-16">
            <div className="relative w-8 h-8">
              <div className="absolute inset-0 border-2 border-primary/20 rounded-full" />
              <div className="absolute inset-0 border-2 border-primary border-t-transparent rounded-full animate-spin" />
            </div>
          </div>
        ) : notifications.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
            <Bell className="w-12 h-12 mb-3 opacity-30" />
            <p className="font-medium text-lg">
              {showDismissed ? 'No dismissed notifications' : 'No notifications'}
            </p>
            <p className="text-sm mt-1">
              {showDismissed ? 'Dismissed notifications will appear here' : "You're all caught up!"}
            </p>
          </div>
        ) : (
          <>
            {notifications.map(notification => {
              const Icon = TYPE_ICONS[notification.type] || Bell;
              const iconColor = TYPE_COLORS[notification.type] || 'text-muted-foreground';

              return (
                <div
                  key={notification.id}
                  onClick={() => handleClick(notification)}
                  className={`relative flex gap-3 px-5 py-4 cursor-pointer hover:bg-muted/50 transition-colors border-b border-border last:border-b-0 ${
                    !notification.is_read && !showDismissed ? 'bg-primary/5' : ''
                  } ${showDismissed ? 'opacity-60' : ''}`}
                >
                  {!notification.is_read && !showDismissed && (
                    <div className="absolute left-0 top-0 bottom-0 w-1 bg-primary rounded-r" />
                  )}

                  <div className={`mt-0.5 ${iconColor}`}>
                    <Icon className="w-5 h-5" />
                  </div>

                  <div className="flex-1 min-w-0">
                    <p className={`text-sm ${!notification.is_read && !showDismissed ? 'font-semibold' : 'font-medium'} text-foreground`}>
                      {notification.title}
                    </p>
                    {notification.message && (
                      <p className="text-sm text-muted-foreground mt-0.5 line-clamp-2">
                        {notification.message}
                      </p>
                    )}
                    <p className="text-xs text-muted-foreground/70 mt-1">
                      {timeAgo(notification.created_at)}
                    </p>
                  </div>

                  {!showDismissed && (
                    <button
                      onClick={(e) => handleDismiss(e, notification.id)}
                      className="mt-0.5 p-1 rounded-md text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-colors"
                      title="Dismiss"
                    >
                      <X className="w-4 h-4" />
                    </button>
                  )}
                </div>
              );
            })}

            {notifications.length < total && (
              <div className="p-4 text-center border-t border-border">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={handleLoadMore}
                >
                  Load more ({total - notifications.length} remaining)
                </Button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
