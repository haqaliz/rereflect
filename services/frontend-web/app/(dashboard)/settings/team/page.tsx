'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { Card, CardHeader, CardContent, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  teamAPI,
  TeamMember,
  TeamInvite,
  getRoleLabel,
  getRoleColor,
  getInviteStatusColor,
  formatRelativeTime,
} from '@/lib/api/team';
import { InviteMemberModal } from '@/components/InviteMemberModal';
import {
  Users,
  UserPlus,
  Crown,
  Shield,
  User,
  MoreHorizontal,
  Mail,
  RefreshCw,
  X,
  Trash2,
  ChevronLeft,
  Loader2,
  Clock,
} from 'lucide-react';
import { toast } from 'sonner';

export default function TeamSettingsPage() {
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [members, setMembers] = useState<TeamMember[]>([]);
  const [invites, setInvites] = useState<TeamInvite[]>([]);
  const [seatsUsed, setSeatsUsed] = useState(0);
  const [seatsLimit, setSeatsLimit] = useState<number | null>(null);

  // Modal states
  const [inviteModalOpen, setInviteModalOpen] = useState(false);
  const [removeDialogOpen, setRemoveDialogOpen] = useState(false);
  const [roleDialogOpen, setRoleDialogOpen] = useState(false);
  const [cancelInviteDialogOpen, setCancelInviteDialogOpen] = useState(false);

  // Selected items for actions
  const [selectedMember, setSelectedMember] = useState<TeamMember | null>(null);
  const [selectedInvite, setSelectedInvite] = useState<TeamInvite | null>(null);
  const [newRole, setNewRole] = useState<'admin' | 'member'>('member');

  // Loading states for actions
  const [actionLoading, setActionLoading] = useState(false);
  const [resendingInvite, setResendingInvite] = useState<number | null>(null);

  // Get current user ID from token (in real app, this would come from auth context)
  const [currentUserId, setCurrentUserId] = useState<number | null>(null);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const token = localStorage.getItem('access_token');
        if (!token) {
          router.push('/login');
          return;
        }

        // Parse the JWT to get the current user ID
        try {
          const payload = JSON.parse(atob(token.split('.')[1]));
          setCurrentUserId(payload.sub || payload.user_id);
        } catch {
          console.error('Failed to parse token');
        }

        const [teamRes, invitesRes] = await Promise.all([
          teamAPI.getTeam(),
          teamAPI.getInvites(),
        ]);

        setMembers(teamRes.members);
        setSeatsUsed(teamRes.seats_used);
        setSeatsLimit(teamRes.seats_limit);
        setInvites(invitesRes.invites.filter(i => i.status === 'pending'));
      } catch (err) {
        console.error('Failed to load team data:', err);
        toast.error('Failed to load team data');
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, [router]);

  const handleInviteSent = (invite: TeamInvite) => {
    setInvites(prev => [invite, ...prev]);
    setSeatsUsed(prev => prev + 1);
  };

  const handleRoleChange = async () => {
    if (!selectedMember) return;

    setActionLoading(true);
    try {
      const updated = await teamAPI.updateRole(selectedMember.id, { role: newRole });
      setMembers(prev => prev.map(m => m.id === updated.id ? updated : m));
      toast.success(`${selectedMember.email}'s role updated to ${getRoleLabel(newRole)}`);
      setRoleDialogOpen(false);
      setSelectedMember(null);
    } catch (err: unknown) {
      const error = err as { response?: { data?: { detail?: string } } };
      const message = error.response?.data?.detail || 'Failed to update role';
      toast.error(message);
    } finally {
      setActionLoading(false);
    }
  };

  const handleRemoveMember = async () => {
    if (!selectedMember) return;

    setActionLoading(true);
    try {
      await teamAPI.removeMember(selectedMember.id);
      setMembers(prev => prev.filter(m => m.id !== selectedMember.id));
      setSeatsUsed(prev => prev - 1);
      toast.success(`${selectedMember.email} has been removed from the team`);
      setRemoveDialogOpen(false);
      setSelectedMember(null);
    } catch (err: unknown) {
      const error = err as { response?: { data?: { detail?: string } } };
      const message = error.response?.data?.detail || 'Failed to remove member';
      toast.error(message);
    } finally {
      setActionLoading(false);
    }
  };

  const handleResendInvite = async (invite: TeamInvite) => {
    setResendingInvite(invite.id);
    try {
      const updated = await teamAPI.resendInvite(invite.id);
      setInvites(prev => prev.map(i => i.id === updated.id ? updated : i));
      toast.success(`Invitation resent to ${invite.email}`);
    } catch (err: unknown) {
      const error = err as { response?: { data?: { detail?: string } } };
      const message = error.response?.data?.detail || 'Failed to resend invitation';
      toast.error(message);
    } finally {
      setResendingInvite(null);
    }
  };

  const handleCancelInvite = async () => {
    if (!selectedInvite) return;

    setActionLoading(true);
    try {
      await teamAPI.cancelInvite(selectedInvite.id);
      setInvites(prev => prev.filter(i => i.id !== selectedInvite.id));
      setSeatsUsed(prev => prev - 1);
      toast.success(`Invitation to ${selectedInvite.email} has been canceled`);
      setCancelInviteDialogOpen(false);
      setSelectedInvite(null);
    } catch (err: unknown) {
      const error = err as { response?: { data?: { detail?: string } } };
      const message = error.response?.data?.detail || 'Failed to cancel invitation';
      toast.error(message);
    } finally {
      setActionLoading(false);
    }
  };

  const getRoleIcon = (role: 'owner' | 'admin' | 'member') => {
    switch (role) {
      case 'owner':
        return Crown;
      case 'admin':
        return Shield;
      case 'member':
        return User;
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
          <p className="text-muted-foreground font-medium">Loading team...</p>
        </div>
      </div>
    );
  }

  const pendingInvites = invites.filter(i => i.status === 'pending');

  return (
    <div className="min-h-screen pattern-bg">
      <main className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
        {/* Back button and Header */}
        <div className="animate-fade-in">
          <Link
            href="/settings"
            className="inline-flex items-center text-sm text-muted-foreground hover:text-foreground mb-4 transition-colors"
          >
            <ChevronLeft className="w-4 h-4 mr-1" />
            Back to Settings
          </Link>
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <div className="p-3 bg-secondary rounded-xl">
                <Users className="w-8 h-8 text-primary" />
              </div>
              <div>
                <h1 className="text-4xl font-bold text-foreground">Team Members</h1>
                <p className="text-muted-foreground text-lg">Manage your organization's team</p>
              </div>
            </div>
            <Button onClick={() => setInviteModalOpen(true)}>
              <UserPlus className="w-4 h-4 mr-2" />
              Invite Member
            </Button>
          </div>
        </div>

        {/* Seat Usage */}
        <Card className="animate-slide-up stagger-1">
          <CardContent className="py-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Users className="w-5 h-5 text-muted-foreground" />
                <span className="font-medium text-foreground">Team Seats</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-2xl font-bold text-foreground">{seatsUsed}</span>
                <span className="text-muted-foreground">/ {seatsLimit || 'Unlimited'}</span>
                {seatsLimit && seatsUsed >= seatsLimit && (
                  <Badge variant="outline" className="ml-2 text-amber-600 border-amber-600/30 bg-amber-50 dark:bg-amber-950">
                    Limit Reached
                  </Badge>
                )}
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Team Members Table */}
        <Card className="animate-slide-up stagger-2">
          <CardHeader className="border-b border-border">
            <div className="flex items-center space-x-2">
              <div className="p-2 bg-secondary rounded-lg">
                <Users className="w-5 h-5 text-primary" />
              </div>
              <div>
                <CardTitle>Members</CardTitle>
                <CardDescription>{members.length} team member{members.length !== 1 ? 's' : ''}</CardDescription>
              </div>
            </div>
          </CardHeader>
          <CardContent className="pt-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[40%]">User</TableHead>
                  <TableHead>Role</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {members.map((member) => {
                  const RoleIcon = getRoleIcon(member.role);
                  const isCurrentUser = currentUserId === member.id;
                  const canModify = member.role !== 'owner' && !isCurrentUser;

                  return (
                    <TableRow key={member.id}>
                      <TableCell>
                        <div className="flex items-center gap-3">
                          <div className="flex items-center justify-center w-10 h-10 rounded-lg bg-primary/10 text-primary font-semibold">
                            {member.email.charAt(0).toUpperCase()}
                          </div>
                          <div>
                            <p className="font-medium text-foreground">
                              {member.email}
                              {isCurrentUser && (
                                <span className="ml-2 text-xs text-muted-foreground">(You)</span>
                              )}
                            </p>
                            <p className="text-sm text-muted-foreground">
                              Joined {formatRelativeTime(member.joined_at)}
                            </p>
                          </div>
                        </div>
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline" className={getRoleColor(member.role)}>
                          <RoleIcon className="w-3 h-3 mr-1" />
                          {getRoleLabel(member.role)}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-1 text-sm text-muted-foreground">
                          <Clock className="w-3 h-3" />
                          {formatRelativeTime(member.last_active_at)}
                        </div>
                      </TableCell>
                      <TableCell className="text-right">
                        {canModify && (
                          <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                              <Button variant="ghost" size="icon">
                                <MoreHorizontal className="w-4 h-4" />
                              </Button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent align="end">
                              <DropdownMenuItem
                                onClick={() => {
                                  setSelectedMember(member);
                                  setNewRole(member.role === 'admin' ? 'member' : 'admin');
                                  setRoleDialogOpen(true);
                                }}
                              >
                                <Shield className="w-4 h-4 mr-2" />
                                Change Role
                              </DropdownMenuItem>
                              <DropdownMenuSeparator />
                              <DropdownMenuItem
                                className="text-destructive focus:text-destructive"
                                onClick={() => {
                                  setSelectedMember(member);
                                  setRemoveDialogOpen(true);
                                }}
                              >
                                <Trash2 className="w-4 h-4 mr-2" />
                                Remove Member
                              </DropdownMenuItem>
                            </DropdownMenuContent>
                          </DropdownMenu>
                        )}
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </CardContent>
        </Card>

        {/* Pending Invites */}
        {pendingInvites.length > 0 && (
          <Card className="animate-slide-up stagger-3">
            <CardHeader className="border-b border-border">
              <div className="flex items-center space-x-2">
                <div className="p-2 bg-secondary rounded-lg">
                  <Mail className="w-5 h-5 text-primary" />
                </div>
                <div>
                  <CardTitle>Pending Invites</CardTitle>
                  <CardDescription>{pendingInvites.length} pending invitation{pendingInvites.length !== 1 ? 's' : ''}</CardDescription>
                </div>
              </div>
            </CardHeader>
            <CardContent className="pt-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-[40%]">Email</TableHead>
                    <TableHead>Role</TableHead>
                    <TableHead>Expires</TableHead>
                    <TableHead className="text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {pendingInvites.map((invite) => (
                    <TableRow key={invite.id}>
                      <TableCell>
                        <div className="flex items-center gap-3">
                          <div className="flex items-center justify-center w-10 h-10 rounded-lg bg-amber-100 dark:bg-amber-900/30 text-amber-600">
                            <Mail className="w-5 h-5" />
                          </div>
                          <p className="font-medium text-foreground">{invite.email}</p>
                        </div>
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline" className={getRoleColor(invite.role as 'admin' | 'member')}>
                          {getRoleLabel(invite.role as 'owner' | 'admin' | 'member')}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-1 text-sm text-muted-foreground">
                          <Clock className="w-3 h-3" />
                          {new Date(invite.expires_at).toLocaleDateString('en-US', {
                            month: 'short',
                            day: 'numeric',
                          })}
                        </div>
                      </TableCell>
                      <TableCell className="text-right">
                        <div className="flex items-center justify-end gap-2">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleResendInvite(invite)}
                            disabled={resendingInvite === invite.id}
                          >
                            {resendingInvite === invite.id ? (
                              <Loader2 className="w-4 h-4 animate-spin" />
                            ) : (
                              <RefreshCw className="w-4 h-4" />
                            )}
                            <span className="ml-1 hidden sm:inline">Resend</span>
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="text-destructive hover:text-destructive"
                            onClick={() => {
                              setSelectedInvite(invite);
                              setCancelInviteDialogOpen(true);
                            }}
                          >
                            <X className="w-4 h-4" />
                            <span className="ml-1 hidden sm:inline">Cancel</span>
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        )}

        {/* Invite Member Modal */}
        <InviteMemberModal
          open={inviteModalOpen}
          onOpenChange={setInviteModalOpen}
          onInviteSent={handleInviteSent}
          seatsUsed={seatsUsed}
          seatsLimit={seatsLimit}
        />

        {/* Change Role Dialog */}
        <Dialog open={roleDialogOpen} onOpenChange={setRoleDialogOpen}>
          <DialogContent className="sm:max-w-md">
            <DialogHeader>
              <DialogTitle>Change Role</DialogTitle>
              <DialogDescription>
                Update the role for {selectedMember?.email}
              </DialogDescription>
            </DialogHeader>
            <div className="py-4">
              <Select
                value={newRole}
                onValueChange={(value) => setNewRole(value as 'admin' | 'member')}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Select a role" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="admin">
                    <div className="flex items-center gap-2">
                      <Shield className="w-4 h-4 text-blue-600" />
                      Admin - Full access to all settings
                    </div>
                  </SelectItem>
                  <SelectItem value="member">
                    <div className="flex items-center gap-2">
                      <User className="w-4 h-4 text-green-600" />
                      Member - Can view and submit feedback
                    </div>
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>
            <DialogFooter>
              <Button
                variant="outline"
                onClick={() => setRoleDialogOpen(false)}
                disabled={actionLoading}
              >
                Cancel
              </Button>
              <Button onClick={handleRoleChange} disabled={actionLoading}>
                {actionLoading ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin mr-2" />
                    Updating...
                  </>
                ) : (
                  'Update Role'
                )}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        {/* Remove Member Dialog */}
        <Dialog open={removeDialogOpen} onOpenChange={setRemoveDialogOpen}>
          <DialogContent className="sm:max-w-md">
            <DialogHeader>
              <DialogTitle>Remove Team Member</DialogTitle>
              <DialogDescription>
                Are you sure you want to remove {selectedMember?.email} from your team?
                They will lose access to all organization data.
              </DialogDescription>
            </DialogHeader>
            <DialogFooter>
              <Button
                variant="outline"
                onClick={() => setRemoveDialogOpen(false)}
                disabled={actionLoading}
              >
                Cancel
              </Button>
              <Button
                variant="destructive"
                onClick={handleRemoveMember}
                disabled={actionLoading}
              >
                {actionLoading ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin mr-2" />
                    Removing...
                  </>
                ) : (
                  <>
                    <Trash2 className="w-4 h-4 mr-2" />
                    Remove Member
                  </>
                )}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        {/* Cancel Invite Dialog */}
        <Dialog open={cancelInviteDialogOpen} onOpenChange={setCancelInviteDialogOpen}>
          <DialogContent className="sm:max-w-md">
            <DialogHeader>
              <DialogTitle>Cancel Invitation</DialogTitle>
              <DialogDescription>
                Are you sure you want to cancel the invitation to {selectedInvite?.email}?
                They will no longer be able to join your organization using this invite.
              </DialogDescription>
            </DialogHeader>
            <DialogFooter>
              <Button
                variant="outline"
                onClick={() => setCancelInviteDialogOpen(false)}
                disabled={actionLoading}
              >
                Keep Invite
              </Button>
              <Button
                variant="destructive"
                onClick={handleCancelInvite}
                disabled={actionLoading}
              >
                {actionLoading ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin mr-2" />
                    Canceling...
                  </>
                ) : (
                  <>
                    <X className="w-4 h-4 mr-2" />
                    Cancel Invite
                  </>
                )}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </main>
    </div>
  );
}
