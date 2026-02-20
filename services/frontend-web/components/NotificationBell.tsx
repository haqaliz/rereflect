'use client';

import { useEffect, useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { Bell } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { notificationsAPI, NotificationItem } from '@/lib/api/notifications';
import { TYPE_ICONS, TYPE_COLORS, timeAgo } from '@/lib/notification-utils';

const POLL_INTERVAL = 30000; // 30 seconds

export function NotificationBell() {
  const router = useRouter();
  const [unreadCount, setUnreadCount] = useState(0);
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);

  const fetchCount = useCallback(async () => {
    try {
      const data = await notificationsAPI.getUnreadCount();
      setUnreadCount(data.count);
    } catch {
      // Silently fail — user may not be authenticated yet
    }
  }, []);

  useEffect(() => {
    fetchCount();
    const interval = setInterval(fetchCount, POLL_INTERVAL);
    return () => clearInterval(interval);
  }, [fetchCount]);

  const fetchRecent = useCallback(async () => {
    setLoading(true);
    try {
      const data = await notificationsAPI.list({ page: 1, page_size: 5 });
      setNotifications(data.items);
      setUnreadCount(data.unread_count);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, []);

  const handleOpenChange = (nextOpen: boolean) => {
    setOpen(nextOpen);
    if (nextOpen) {
      fetchRecent();
    } else {
      // Refresh count after closing (user may have marked items read)
      fetchCount();
    }
  };

  const handleClick = (notification: NotificationItem) => {
    setOpen(false);
    router.push(`/notifications/${notification.id}`);
  };

  const handleViewAll = () => {
    setOpen(false);
    router.push('/notifications');
  };

  return (
    <Popover open={open} onOpenChange={handleOpenChange}>
      <PopoverTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          className="relative h-8 w-8"
          aria-label={`Notifications${unreadCount > 0 ? ` (${unreadCount} unread)` : ''}`}
        >
          <Bell className="h-4 w-4" />
          {unreadCount > 0 && (
            <span className="absolute -top-0.5 -right-0.5 flex items-center justify-center min-w-[16px] h-4 px-1 text-[10px] font-bold text-primary-foreground bg-destructive rounded-full">
              {unreadCount > 99 ? '99+' : unreadCount}
            </span>
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-[360px] p-0">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-border">
          <h3 className="font-semibold text-sm">Notifications</h3>
          {unreadCount > 0 && (
            <span className="text-xs text-muted-foreground">
              {unreadCount} unread
            </span>
          )}
        </div>

        {/* List */}
        <div className="max-h-[320px] overflow-y-auto">
          {loading && notifications.length === 0 ? (
            <div className="flex items-center justify-center py-8">
              <div className="relative w-6 h-6">
                <div className="absolute inset-0 border-2 border-primary/20 rounded-full" />
                <div className="absolute inset-0 border-2 border-primary border-t-transparent rounded-full animate-spin" />
              </div>
            </div>
          ) : notifications.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-8 text-muted-foreground">
              <Bell className="w-8 h-8 mb-2 opacity-30" />
              <p className="text-sm font-medium">No notifications</p>
              <p className="text-xs">You&apos;re all caught up!</p>
            </div>
          ) : (
            notifications.map(notification => {
              const Icon = TYPE_ICONS[notification.type] || Bell;
              const isRecovery = notification.type === 'customer_health_drop' && notification.metadata?.is_recovery === true;
              const iconColor = isRecovery ? 'text-green-500' : (TYPE_COLORS[notification.type] || 'text-muted-foreground');

              return (
                <div
                  key={notification.id}
                  onClick={() => handleClick(notification)}
                  className={`relative flex gap-3 px-4 py-3 cursor-pointer hover:bg-muted/50 transition-colors border-b border-border last:border-b-0 ${
                    !notification.is_read ? 'bg-primary/5' : ''
                  }`}
                >
                  {!notification.is_read && (
                    <div className="absolute left-0 top-0 bottom-0 w-0.5 bg-primary rounded-r" />
                  )}
                  <div data-testid={`popover-notif-icon-${notification.id}`} className={`mt-0.5 ${iconColor}`}>
                    <Icon className="w-4 h-4" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className={`text-xs ${!notification.is_read ? 'font-semibold' : 'font-medium'} text-foreground truncate`}>
                      {notification.title}
                    </p>
                    {notification.message && (
                      <p className="text-xs text-muted-foreground mt-0.5 line-clamp-1">
                        {notification.message}
                      </p>
                    )}
                    <p className="text-[10px] text-muted-foreground/70 mt-0.5">
                      {timeAgo(notification.created_at)}
                    </p>
                  </div>
                </div>
              );
            })
          )}
        </div>

        {/* Footer */}
        <div className="border-t border-border p-2">
          <Button
            variant="ghost"
            size="sm"
            className="w-full text-xs"
            onClick={handleViewAll}
          >
            View all notifications
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  );
}
