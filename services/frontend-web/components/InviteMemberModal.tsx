'use client';

import { useState } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { teamAPI, TeamInvite } from '@/lib/api/team';
import { Mail, Shield, User, Loader2 } from 'lucide-react';
import { toast } from 'sonner';

interface InviteMemberModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onInviteSent: (invite: TeamInvite) => void;
  seatsUsed: number;
  seatsLimit: number | null;
}

export function InviteMemberModal({
  open,
  onOpenChange,
  onInviteSent,
  seatsUsed,
  seatsLimit,
}: InviteMemberModalProps) {
  const [email, setEmail] = useState('');
  const [role, setRole] = useState<'admin' | 'member'>('member');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isAtSeatLimit = seatsLimit !== null && seatsUsed >= seatsLimit;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!email.trim()) {
      setError('Email is required');
      return;
    }

    // Basic email validation
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(email)) {
      setError('Please enter a valid email address');
      return;
    }

    if (isAtSeatLimit) {
      setError('You have reached your seat limit. Please upgrade your plan to invite more members.');
      return;
    }

    setLoading(true);
    try {
      const invite = await teamAPI.inviteMember({ email: email.trim(), role });
      toast.success(`Invitation sent to ${email}`);
      onInviteSent(invite);
      handleClose();
    } catch (err: unknown) {
      const error = err as { response?: { data?: { detail?: string } } };
      const message = error.response?.data?.detail || 'Failed to send invitation';
      setError(message);
      toast.error(message);
    } finally {
      setLoading(false);
    }
  };

  const handleClose = () => {
    setEmail('');
    setRole('member');
    setError(null);
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Mail className="w-5 h-5 text-primary" />
            Invite Team Member
          </DialogTitle>
          <DialogDescription>
            Send an invitation to add a new member to your organization.
            {seatsLimit !== null && (
              <span className="block mt-1 text-sm">
                Seats used: {seatsUsed}/{seatsLimit}
              </span>
            )}
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit}>
          <div className="space-y-4 py-4">
            {/* Email Input */}
            <div className="space-y-2">
              <Label htmlFor="email">Email address</Label>
              <Input
                id="email"
                type="email"
                placeholder="colleague@company.com"
                value={email}
                onChange={(e) => {
                  setEmail(e.target.value);
                  setError(null);
                }}
                disabled={loading || isAtSeatLimit}
                className={error ? 'border-destructive' : ''}
              />
            </div>

            {/* Role Selection */}
            <div className="space-y-2">
              <Label>Role</Label>
              <div className="grid grid-cols-2 gap-3">
                <button
                  type="button"
                  onClick={() => setRole('member')}
                  disabled={loading || isAtSeatLimit}
                  className={`flex flex-col items-center gap-2 p-4 rounded-xl border-2 transition-all ${
                    role === 'member'
                      ? 'border-primary bg-primary/10 text-primary'
                      : 'border-border hover:border-primary/50 text-foreground'
                  } ${loading || isAtSeatLimit ? 'opacity-50 cursor-not-allowed' : ''}`}
                >
                  <div className={`p-2 rounded-lg ${role === 'member' ? 'bg-primary/20' : 'bg-secondary'}`}>
                    <User className="w-5 h-5" />
                  </div>
                  <div className="text-center">
                    <span className="font-semibold block">Member</span>
                    <span className="text-xs text-muted-foreground">
                      Can view and submit feedback
                    </span>
                  </div>
                </button>

                <button
                  type="button"
                  onClick={() => setRole('admin')}
                  disabled={loading || isAtSeatLimit}
                  className={`flex flex-col items-center gap-2 p-4 rounded-xl border-2 transition-all ${
                    role === 'admin'
                      ? 'border-primary bg-primary/10 text-primary'
                      : 'border-border hover:border-primary/50 text-foreground'
                  } ${loading || isAtSeatLimit ? 'opacity-50 cursor-not-allowed' : ''}`}
                >
                  <div className={`p-2 rounded-lg ${role === 'admin' ? 'bg-primary/20' : 'bg-secondary'}`}>
                    <Shield className="w-5 h-5" />
                  </div>
                  <div className="text-center">
                    <span className="font-semibold block">Admin</span>
                    <span className="text-xs text-muted-foreground">
                      Full access to all settings
                    </span>
                  </div>
                </button>
              </div>
            </div>

            {/* Error Message */}
            {error && (
              <p className="text-sm text-destructive">{error}</p>
            )}

            {/* Seat Limit Warning */}
            {isAtSeatLimit && (
              <div className="p-3 bg-amber-50 dark:bg-amber-950 border border-amber-200 dark:border-amber-800 rounded-lg">
                <p className="text-sm text-amber-800 dark:text-amber-200">
                  You have reached your team seat limit. Upgrade your plan to invite more members.
                </p>
              </div>
            )}
          </div>

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={handleClose}
              disabled={loading}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={loading || isAtSeatLimit || !email.trim()}>
              {loading ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin mr-2" />
                  Sending...
                </>
              ) : (
                <>
                  <Mail className="w-4 h-4 mr-2" />
                  Send Invite
                </>
              )}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
