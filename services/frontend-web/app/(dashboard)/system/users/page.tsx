'use client';

import { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import {
  adminUsersAPI,
  type AdminUser,
  type AdminUserUpdate,
} from '@/lib/api/admin-users';
import { adminOrgsAPI, type AdminOrg } from '@/lib/api/admin-orgs';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogDescription,
} from '@/components/ui/dialog';
import {
  Users,
  Loader2,
  Pencil,
  Trash2,
  Search,
  ChevronLeft,
  ChevronRight,
  Shield,
} from 'lucide-react';
import { toast } from 'sonner';

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
}

function formatRelativeTime(dateStr: string | null): string {
  if (!dateStr) return 'Never';
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  if (diffMins < 1) return 'Just now';
  if (diffMins < 60) return `${diffMins}m ago`;
  const diffHours = Math.floor(diffMins / 60);
  if (diffHours < 24) return `${diffHours}h ago`;
  const diffDays = Math.floor(diffHours / 24);
  if (diffDays < 30) return `${diffDays}d ago`;
  return formatDate(dateStr);
}

const PLAN_COLORS: Record<string, 'default' | 'secondary' | 'success' | 'destructive'> = {
  free: 'secondary',
  pro: 'success',
  business: 'default',
  enterprise: 'destructive',
};

export default function AdminUsersPage() {
  const { user } = useAuth();
  const router = useRouter();

  // List state
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [isLoading, setIsLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [orgFilter, setOrgFilter] = useState<string>('all');

  // Orgs for filter/edit
  const [orgs, setOrgs] = useState<AdminOrg[]>([]);

  // Edit dialog
  const [editingUser, setEditingUser] = useState<AdminUser | null>(null);
  const [editForm, setEditForm] = useState<AdminUserUpdate>({});
  const [isSaving, setIsSaving] = useState(false);

  // Delete dialog
  const [deletingUser, setDeletingUser] = useState<AdminUser | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);

  const PAGE_SIZE = 50;

  // Auth guard
  useEffect(() => {
    if (user && !user.is_system_admin) {
      router.push('/dashboard');
    }
  }, [user, router]);

  // Fetch orgs for filter dropdown
  useEffect(() => {
    if (user?.is_system_admin) {
      adminOrgsAPI.list({ page_size: 100 }).then(data => {
        setOrgs(data.organizations);
      }).catch(() => {});
    }
  }, [user]);

  // Fetch users
  const fetchUsers = useCallback(async () => {
    try {
      setIsLoading(true);
      const params: Record<string, unknown> = { page, page_size: PAGE_SIZE };
      if (search) params.search = search;
      if (orgFilter !== 'all') params.organization_id = Number(orgFilter);
      const data = await adminUsersAPI.list(params as Parameters<typeof adminUsersAPI.list>[0]);
      setUsers(data.users);
      setTotal(data.total);
    } catch {
      toast.error('Failed to load users');
    } finally {
      setIsLoading(false);
    }
  }, [page, search, orgFilter]);

  useEffect(() => {
    if (user?.is_system_admin) {
      fetchUsers();
    }
  }, [user, fetchUsers]);

  // Debounced search
  const [searchInput, setSearchInput] = useState('');
  useEffect(() => {
    const timer = setTimeout(() => {
      setSearch(searchInput);
      setPage(1);
    }, 300);
    return () => clearTimeout(timer);
  }, [searchInput]);

  const handleEdit = (u: AdminUser) => {
    setEditingUser(u);
    setEditForm({
      organization_id: u.organization_id,
      role: u.role,
      is_system_admin: u.is_system_admin,
    });
  };

  const handleSave = async () => {
    if (!editingUser) return;
    setIsSaving(true);
    try {
      const update: AdminUserUpdate = {};
      if (editForm.organization_id !== editingUser.organization_id) {
        update.organization_id = editForm.organization_id;
      }
      if (editForm.role !== editingUser.role) {
        update.role = editForm.role;
      }
      if (editForm.is_system_admin !== editingUser.is_system_admin) {
        update.is_system_admin = editForm.is_system_admin;
      }

      if (Object.keys(update).length === 0) {
        toast.info('No changes to save');
        setEditingUser(null);
        return;
      }

      const updated = await adminUsersAPI.update(editingUser.id, update);
      setUsers(prev => prev.map(u => (u.id === updated.id ? updated : u)));
      toast.success(`Updated ${updated.email}`);
      setEditingUser(null);
    } catch (err: unknown) {
      const axiosErr = err as { response?: { data?: { detail?: string } } };
      toast.error(axiosErr?.response?.data?.detail || 'Failed to update user');
    } finally {
      setIsSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!deletingUser) return;
    setIsDeleting(true);
    try {
      await adminUsersAPI.delete(deletingUser.id);
      setUsers(prev => prev.filter(u => u.id !== deletingUser.id));
      setTotal(prev => prev - 1);
      toast.success(`Deleted ${deletingUser.email}`);
      setDeletingUser(null);
    } catch (err: unknown) {
      const axiosErr = err as { response?: { data?: { detail?: string } } };
      toast.error(axiosErr?.response?.data?.detail || 'Failed to delete user');
    } finally {
      setIsDeleting(false);
    }
  };

  const totalPages = Math.ceil(total / PAGE_SIZE);

  if (!user?.is_system_admin) return null;

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Users</h1>
        <p className="text-muted-foreground">Manage all users across organizations. {total} total.</p>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-3">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <Input
            placeholder="Search by email..."
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            className="pl-9"
          />
        </div>
        <Select value={orgFilter} onValueChange={(v) => { setOrgFilter(v); setPage(1); }}>
          <SelectTrigger className="w-[220px]">
            <SelectValue placeholder="All organizations" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All organizations</SelectItem>
            {orgs.map(org => (
              <SelectItem key={org.id} value={String(org.id)}>
                {org.name} ({org.plan})
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Users className="w-5 h-5" />
            All Users
          </CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="flex justify-center py-12">
              <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
            </div>
          ) : users.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">
              No users found.
            </div>
          ) : (
            <>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Email</TableHead>
                    <TableHead>Role</TableHead>
                    <TableHead>Organization</TableHead>
                    <TableHead>Plan</TableHead>
                    <TableHead>Last Active</TableHead>
                    <TableHead className="text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {users.map(u => (
                    <TableRow key={u.id}>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <span className="font-medium">{u.email}</span>
                          {u.is_system_admin && (
                            <span title="System Admin"><Shield className="w-3.5 h-3.5 text-primary" /></span>
                          )}
                        </div>
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline" className="capitalize">{u.role}</Badge>
                      </TableCell>
                      <TableCell className="text-muted-foreground">{u.organization_name}</TableCell>
                      <TableCell>
                        <Badge variant={PLAN_COLORS[u.plan] || 'secondary'} className="capitalize">
                          {u.plan}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-muted-foreground text-sm">
                        {formatRelativeTime(u.last_active_at)}
                      </TableCell>
                      <TableCell className="text-right">
                        <div className="flex items-center justify-end gap-1">
                          <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => handleEdit(u)}
                            title="Edit user"
                          >
                            <Pencil className="w-4 h-4" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => setDeletingUser(u)}
                            title="Delete user"
                            className="text-destructive hover:text-destructive"
                          >
                            <Trash2 className="w-4 h-4" />
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>

              {/* Pagination */}
              {totalPages > 1 && (
                <div className="flex items-center justify-between mt-4">
                  <span className="text-sm text-muted-foreground">
                    Page {page} of {totalPages}
                  </span>
                  <div className="flex gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={page <= 1}
                      onClick={() => setPage(p => p - 1)}
                    >
                      <ChevronLeft className="w-4 h-4" />
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={page >= totalPages}
                      onClick={() => setPage(p => p + 1)}
                    >
                      <ChevronRight className="w-4 h-4" />
                    </Button>
                  </div>
                </div>
              )}
            </>
          )}
        </CardContent>
      </Card>

      {/* Edit User Dialog */}
      <Dialog open={!!editingUser} onOpenChange={(open) => !open && setEditingUser(null)}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Edit User</DialogTitle>
            <DialogDescription>
              {editingUser?.email}
            </DialogDescription>
          </DialogHeader>
          {editingUser && (
            <div className="space-y-4">
              {/* Organization */}
              <div>
                <Label>Organization</Label>
                <Select
                  value={String(editForm.organization_id)}
                  onValueChange={(v) => setEditForm(prev => ({ ...prev, organization_id: Number(v) }))}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {orgs.map(org => (
                      <SelectItem key={org.id} value={String(org.id)}>
                        {org.name} ({org.plan})
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {editForm.organization_id !== editingUser.organization_id && (
                  <p className="text-xs text-amber-500 mt-1">
                    Moving to a different org will reset role to &quot;member&quot;
                  </p>
                )}
              </div>

              {/* Role */}
              <div>
                <Label>Role</Label>
                <Select
                  value={editForm.role || editingUser.role}
                  onValueChange={(v) => setEditForm(prev => ({ ...prev, role: v }))}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="owner">Owner</SelectItem>
                    <SelectItem value="admin">Admin</SelectItem>
                    <SelectItem value="member">Member</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {/* System Admin */}
              <div className="flex items-center gap-3">
                <Switch
                  id="sys_admin"
                  checked={editForm.is_system_admin ?? editingUser.is_system_admin}
                  onCheckedChange={(checked) =>
                    setEditForm(prev => ({ ...prev, is_system_admin: checked }))
                  }
                />
                <Label htmlFor="sys_admin">System Admin</Label>
              </div>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditingUser(null)}>Cancel</Button>
            <Button onClick={handleSave} disabled={isSaving}>
              {isSaving && <Loader2 className="w-4 h-4 animate-spin mr-2" />}
              Save Changes
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <Dialog open={!!deletingUser} onOpenChange={(open) => !open && setDeletingUser(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete User</DialogTitle>
          </DialogHeader>
          <p className="text-muted-foreground">
            Are you sure you want to delete <span className="font-medium text-foreground">{deletingUser?.email}</span>?
            This will remove all their personal data and cannot be undone.
          </p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeletingUser(null)}>Cancel</Button>
            <Button variant="destructive" onClick={handleDelete} disabled={isDeleting}>
              {isDeleting && <Loader2 className="w-4 h-4 animate-spin mr-2" />}
              Delete User
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
