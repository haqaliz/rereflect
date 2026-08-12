'use client';

import { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Switch } from '@/components/ui/switch';
import { useAuth } from '@/contexts/AuthContext';
import { customersAPI } from '@/lib/api/customers';

interface OutreachOptOutToggleProps {
  email: string;
  initialValue?: boolean;
}

/**
 * Per-customer outreach opt-out switch (outreach-core AC9). Bound directly to
 * `outreach_opt_out`: checked = customer has opted out of outreach emails.
 * Admin/owner only — members never see the control (the PATCH would 403
 * anyway). Optimistic flip with revert + toast on failure.
 */
export function OutreachOptOutToggle({ email, initialValue = false }: OutreachOptOutToggleProps) {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [optedOut, setOptedOut] = useState(initialValue);
  const [saving, setSaving] = useState(false);

  const isAdminOrOwner = user?.role === 'owner' || user?.role === 'admin';
  if (!isAdminOrOwner) return null;

  const handleToggle = async (checked: boolean) => {
    setOptedOut(checked);
    setSaving(true);
    try {
      await customersAPI.updateOutreachOptOut(email, checked);
      queryClient.invalidateQueries({ queryKey: ['customer-profile', email] });
    } catch {
      setOptedOut(!checked);
      toast.error('Could not update outreach preference. Please try again.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex items-center gap-2">
      <span className="text-xs text-muted-foreground whitespace-nowrap">Send outreach emails</span>
      <Switch
        aria-label="Send outreach emails"
        checked={optedOut}
        onCheckedChange={handleToggle}
        disabled={saving}
      />
    </div>
  );
}
