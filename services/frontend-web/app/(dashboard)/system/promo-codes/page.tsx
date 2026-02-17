'use client';

import { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import {
  adminPromoAPI,
  type PromoCode,
  type PromoCodeDetail,
  type CreatePromoRequest,
} from '@/lib/api/admin-promo';
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
  Tag,
  Loader2,
  Plus,
  Eye,
  Power,
  Trash2,
} from 'lucide-react';
import { toast } from 'sonner';

// -- Quick Templates --

interface PromoTemplate {
  label: string;
  defaults: Partial<CreatePromoRequest>;
}

const QUICK_TEMPLATES: PromoTemplate[] = [
  {
    label: '3mo Free Pro',
    defaults: {
      coupon_name: '3 Months Free Pro',
      discount_type: 'percent',
      percent_off: 100,
      duration: 'repeating',
      duration_in_months: 3,
      first_time_transaction: true,
    },
  },
  {
    label: '1mo Free Pro',
    defaults: {
      coupon_name: '1 Month Free Pro',
      discount_type: 'percent',
      percent_off: 100,
      duration: 'repeating',
      duration_in_months: 1,
      first_time_transaction: true,
    },
  },
  {
    label: '50% Off 3mo',
    defaults: {
      coupon_name: '50% Off 3 Months',
      discount_type: 'percent',
      percent_off: 50,
      duration: 'repeating',
      duration_in_months: 3,
      first_time_transaction: true,
    },
  },
  {
    label: '50% Off First Month',
    defaults: {
      coupon_name: '50% Off First Month',
      discount_type: 'percent',
      percent_off: 50,
      duration: 'once',
      first_time_transaction: true,
    },
  },
];

const INITIAL_FORM: CreatePromoRequest = {
  code: '',
  coupon_name: '',
  discount_type: 'percent',
  percent_off: 100,
  duration: 'once',
  duration_in_months: undefined,
  max_redemptions: undefined,
  first_time_transaction: true,
  expires_at: null,
};

// -- Helpers --

function formatDiscount(coupon: PromoCode['coupon']): string {
  if (coupon.percent_off != null) return `${coupon.percent_off}% off`;
  if (coupon.amount_off != null) {
    const amount = coupon.amount_off / 100;
    const currency = (coupon.currency || 'usd').toUpperCase();
    return `$${amount.toFixed(2)} ${currency} off`;
  }
  return '-';
}

function formatDuration(coupon: PromoCode['coupon']): string {
  if (coupon.duration === 'once') return 'Once';
  if (coupon.duration === 'forever') return 'Forever';
  if (coupon.duration === 'repeating' && coupon.duration_in_months) {
    return `${coupon.duration_in_months} month${coupon.duration_in_months > 1 ? 's' : ''}`;
  }
  return coupon.duration;
}

function formatRedemptions(promo: PromoCode): string {
  const used = promo.times_redeemed;
  const max = promo.max_redemptions;
  return max != null ? `${used}/${max}` : `${used}`;
}

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
}

// -- Component --

export default function AdminPromoCodesPage() {
  const { user } = useAuth();
  const router = useRouter();

  // List state
  const [promoCodes, setPromoCodes] = useState<PromoCode[]>([]);
  const [total, setTotal] = useState(0);
  const [isLoading, setIsLoading] = useState(true);

  // Create dialog
  const [showCreate, setShowCreate] = useState(false);
  const [createForm, setCreateForm] = useState<CreatePromoRequest>({ ...INITIAL_FORM });
  const [isCreating, setIsCreating] = useState(false);

  // Detail dialog
  const [detailPromo, setDetailPromo] = useState<PromoCodeDetail | null>(null);
  const [isLoadingDetail, setIsLoadingDetail] = useState(false);

  // Deactivate dialog
  const [deactivatingPromo, setDeactivatingPromo] = useState<PromoCode | null>(null);
  const [isDeactivating, setIsDeactivating] = useState(false);

  // Delete dialog
  const [deletingPromo, setDeletingPromo] = useState<PromoCode | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);

  // Auth guard
  useEffect(() => {
    if (user && !user.is_system_admin) {
      router.push('/dashboard');
    }
  }, [user, router]);

  // Fetch promo codes
  const fetchPromoCodes = useCallback(async () => {
    try {
      setIsLoading(true);
      const data = await adminPromoAPI.list();
      setPromoCodes(data.promo_codes);
      setTotal(data.total);
    } catch {
      toast.error('Failed to load promo codes');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (user?.is_system_admin) {
      fetchPromoCodes();
    }
  }, [user, fetchPromoCodes]);

  // -- Handlers --

  const handleTemplateClick = (template: PromoTemplate) => {
    setCreateForm({
      ...INITIAL_FORM,
      ...template.defaults,
    });
  };

  const handleCreate = async () => {
    if (!createForm.code.trim()) {
      toast.error('Promo code is required');
      return;
    }
    if (!createForm.coupon_name.trim()) {
      toast.error('Coupon name is required');
      return;
    }
    if (createForm.discount_type === 'percent' && (createForm.percent_off == null || createForm.percent_off <= 0 || createForm.percent_off > 100)) {
      toast.error('Percent off must be between 1 and 100');
      return;
    }
    if (createForm.discount_type === 'amount' && (createForm.amount_off == null || createForm.amount_off <= 0)) {
      toast.error('Amount off must be greater than 0');
      return;
    }
    if (createForm.duration === 'repeating' && (createForm.duration_in_months == null || createForm.duration_in_months <= 0)) {
      toast.error('Duration in months is required for repeating discounts');
      return;
    }

    setIsCreating(true);
    try {
      const payload: CreatePromoRequest = {
        code: createForm.code.toUpperCase().trim(),
        coupon_name: createForm.coupon_name.trim(),
        discount_type: createForm.discount_type,
        duration: createForm.duration,
        first_time_transaction: createForm.first_time_transaction,
      };

      if (createForm.discount_type === 'percent') {
        payload.percent_off = createForm.percent_off;
      } else {
        payload.amount_off = createForm.amount_off;
        payload.currency = 'usd';
      }

      if (createForm.duration === 'repeating') {
        payload.duration_in_months = createForm.duration_in_months;
      }

      if (createForm.max_redemptions != null && createForm.max_redemptions > 0) {
        payload.max_redemptions = createForm.max_redemptions;
      }

      if (createForm.expires_at) {
        payload.expires_at = createForm.expires_at;
      }

      await adminPromoAPI.create(payload);
      toast.success(`Promo code ${payload.code} created`);
      setShowCreate(false);
      setCreateForm({ ...INITIAL_FORM });
      fetchPromoCodes();
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to create promo code';
      const axiosErr = err as { response?: { data?: { detail?: string } } };
      toast.error(axiosErr?.response?.data?.detail || message);
    } finally {
      setIsCreating(false);
    }
  };

  const handleViewDetail = async (promo: PromoCode) => {
    setIsLoadingDetail(true);
    setDetailPromo(null);
    try {
      const detail = await adminPromoAPI.get(promo.id);
      setDetailPromo(detail);
    } catch {
      toast.error('Failed to load promo code details');
    } finally {
      setIsLoadingDetail(false);
    }
  };

  const handleDeactivate = async () => {
    if (!deactivatingPromo) return;
    setIsDeactivating(true);
    try {
      const updated = await adminPromoAPI.deactivate(deactivatingPromo.id);
      setPromoCodes(prev => prev.map(p => p.id === updated.id ? updated : p));
      toast.success(`${deactivatingPromo.code} deactivated`);
      setDeactivatingPromo(null);
    } catch {
      toast.error('Failed to deactivate promo code');
    } finally {
      setIsDeactivating(false);
    }
  };

  const handleDelete = async () => {
    if (!deletingPromo) return;
    setIsDeleting(true);
    try {
      await adminPromoAPI.delete(deletingPromo.id);
      setPromoCodes(prev => prev.filter(p => p.id !== deletingPromo.id));
      setTotal(prev => prev - 1);
      toast.success(`${deletingPromo.code} deleted`);
      setDeletingPromo(null);
    } catch {
      toast.error('Failed to delete promo code');
    } finally {
      setIsDeleting(false);
    }
  };

  if (!user?.is_system_admin) {
    return null;
  }

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Promo Codes</h1>
          <p className="text-muted-foreground">Manage Stripe promotion codes. {total} total.</p>
        </div>
        <Button onClick={() => setShowCreate(true)}>
          <Plus className="w-4 h-4 mr-2" />
          Create Promo
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Tag className="w-5 h-5" />
            Promotion Codes
          </CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="flex justify-center py-12">
              <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
            </div>
          ) : promoCodes.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">
              No promo codes found. Create one to get started.
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Code</TableHead>
                  <TableHead>Discount</TableHead>
                  <TableHead>Duration</TableHead>
                  <TableHead>Redemptions</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {promoCodes.map(promo => (
                  <TableRow key={promo.id}>
                    <TableCell className="font-mono font-medium">{promo.code}</TableCell>
                    <TableCell>{formatDiscount(promo.coupon)}</TableCell>
                    <TableCell>{formatDuration(promo.coupon)}</TableCell>
                    <TableCell>{formatRedemptions(promo)}</TableCell>
                    <TableCell>
                      <Badge variant={promo.active ? 'success' : 'secondary'}>
                        {promo.active ? 'Active' : 'Inactive'}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex items-center justify-end gap-1">
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => handleViewDetail(promo)}
                          title="View details"
                        >
                          <Eye className="w-4 h-4" />
                        </Button>
                        {promo.active && (
                          <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => setDeactivatingPromo(promo)}
                            title="Deactivate"
                          >
                            <Power className="w-4 h-4" />
                          </Button>
                        )}
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => setDeletingPromo(promo)}
                          title="Delete"
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
          )}
        </CardContent>
      </Card>

      {/* Create Promo Dialog */}
      <Dialog open={showCreate} onOpenChange={(open) => {
        if (!open) {
          setShowCreate(false);
          setCreateForm({ ...INITIAL_FORM });
        }
      }}>
        <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Create Promo Code</DialogTitle>
            <DialogDescription>
              Use a quick template or customize all fields.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-5">
            {/* Quick Templates */}
            <div>
              <Label className="text-sm font-medium">Quick Templates</Label>
              <div className="flex flex-wrap gap-2 mt-2">
                {QUICK_TEMPLATES.map(tpl => (
                  <Button
                    key={tpl.label}
                    variant="outline"
                    size="sm"
                    onClick={() => handleTemplateClick(tpl)}
                  >
                    {tpl.label}
                  </Button>
                ))}
              </div>
            </div>

            <div className="border-t pt-4 space-y-4">
              {/* Code */}
              <div>
                <Label htmlFor="code">Promo Code</Label>
                <Input
                  id="code"
                  placeholder="e.g. EARLYPRO3"
                  value={createForm.code}
                  onChange={e => setCreateForm(prev => ({ ...prev, code: e.target.value.toUpperCase() }))}
                  className="font-mono"
                />
              </div>

              {/* Coupon Name */}
              <div>
                <Label htmlFor="coupon_name">Coupon Name</Label>
                <Input
                  id="coupon_name"
                  placeholder="e.g. Early Adopter - 3 Months Free Pro"
                  value={createForm.coupon_name}
                  onChange={e => setCreateForm(prev => ({ ...prev, coupon_name: e.target.value }))}
                />
              </div>

              {/* Discount Type */}
              <div>
                <Label>Discount Type</Label>
                <Select
                  value={createForm.discount_type}
                  onValueChange={(value: 'percent' | 'amount') =>
                    setCreateForm(prev => ({ ...prev, discount_type: value }))
                  }
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="percent">Percentage</SelectItem>
                    <SelectItem value="amount">Fixed Amount</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {/* Discount Value */}
              {createForm.discount_type === 'percent' ? (
                <div>
                  <Label htmlFor="percent_off">Percent Off</Label>
                  <div className="relative">
                    <Input
                      id="percent_off"
                      type="number"
                      min={1}
                      max={100}
                      value={createForm.percent_off ?? ''}
                      onChange={e => setCreateForm(prev => ({
                        ...prev,
                        percent_off: e.target.value ? Number(e.target.value) : undefined,
                      }))}
                    />
                    <span className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground text-sm">%</span>
                  </div>
                </div>
              ) : (
                <div>
                  <Label htmlFor="amount_off">Amount Off (cents)</Label>
                  <div className="relative">
                    <Input
                      id="amount_off"
                      type="number"
                      min={1}
                      value={createForm.amount_off ?? ''}
                      onChange={e => setCreateForm(prev => ({
                        ...prev,
                        amount_off: e.target.value ? Number(e.target.value) : undefined,
                      }))}
                    />
                    <span className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground text-sm">cents</span>
                  </div>
                </div>
              )}

              {/* Duration */}
              <div>
                <Label>Duration</Label>
                <Select
                  value={createForm.duration}
                  onValueChange={(value: 'once' | 'repeating' | 'forever') =>
                    setCreateForm(prev => ({ ...prev, duration: value }))
                  }
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="once">Once</SelectItem>
                    <SelectItem value="repeating">Repeating</SelectItem>
                    <SelectItem value="forever">Forever</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {/* Duration in Months (when repeating) */}
              {createForm.duration === 'repeating' && (
                <div>
                  <Label htmlFor="duration_months">Duration (months)</Label>
                  <Input
                    id="duration_months"
                    type="number"
                    min={1}
                    value={createForm.duration_in_months ?? ''}
                    onChange={e => setCreateForm(prev => ({
                      ...prev,
                      duration_in_months: e.target.value ? Number(e.target.value) : undefined,
                    }))}
                  />
                </div>
              )}

              {/* Max Redemptions */}
              <div>
                <Label htmlFor="max_redemptions">Max Redemptions</Label>
                <Input
                  id="max_redemptions"
                  type="number"
                  min={1}
                  placeholder="Empty = unlimited"
                  value={createForm.max_redemptions ?? ''}
                  onChange={e => setCreateForm(prev => ({
                    ...prev,
                    max_redemptions: e.target.value ? Number(e.target.value) : undefined,
                  }))}
                />
              </div>

              {/* First-time only */}
              <div className="flex items-center gap-3">
                <Switch
                  id="first_time"
                  checked={createForm.first_time_transaction ?? true}
                  onCheckedChange={checked => setCreateForm(prev => ({
                    ...prev,
                    first_time_transaction: checked,
                  }))}
                />
                <Label htmlFor="first_time">First-time transaction only</Label>
              </div>

              {/* Expires At */}
              <div>
                <Label htmlFor="expires_at">Expires At</Label>
                <Input
                  id="expires_at"
                  type="datetime-local"
                  value={createForm.expires_at ?? ''}
                  onChange={e => setCreateForm(prev => ({
                    ...prev,
                    expires_at: e.target.value || null,
                  }))}
                />
              </div>
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => {
              setShowCreate(false);
              setCreateForm({ ...INITIAL_FORM });
            }}>
              Cancel
            </Button>
            <Button onClick={handleCreate} disabled={isCreating}>
              {isCreating && <Loader2 className="w-4 h-4 animate-spin mr-2" />}
              Create Promo Code
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Detail Dialog */}
      <Dialog open={isLoadingDetail || !!detailPromo} onOpenChange={(open) => {
        if (!open) {
          setDetailPromo(null);
          setIsLoadingDetail(false);
        }
      }}>
        <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Promo Code Details</DialogTitle>
          </DialogHeader>
          {isLoadingDetail ? (
            <div className="flex justify-center py-8">
              <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
            </div>
          ) : detailPromo && (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-3 text-sm">
                <div>
                  <span className="text-muted-foreground">Code</span>
                  <p className="font-mono font-medium">{detailPromo.code}</p>
                </div>
                <div>
                  <span className="text-muted-foreground">Status</span>
                  <p>
                    <Badge variant={detailPromo.active ? 'success' : 'secondary'}>
                      {detailPromo.active ? 'Active' : 'Inactive'}
                    </Badge>
                  </p>
                </div>
                <div>
                  <span className="text-muted-foreground">Discount</span>
                  <p className="font-medium">{formatDiscount(detailPromo.coupon)}</p>
                </div>
                <div>
                  <span className="text-muted-foreground">Duration</span>
                  <p>{formatDuration(detailPromo.coupon)}</p>
                </div>
                <div>
                  <span className="text-muted-foreground">Coupon Name</span>
                  <p>{detailPromo.coupon.name || '-'}</p>
                </div>
                <div>
                  <span className="text-muted-foreground">Redemptions</span>
                  <p>{formatRedemptions(detailPromo)}</p>
                </div>
                <div>
                  <span className="text-muted-foreground">First-time Only</span>
                  <p>{detailPromo.first_time_transaction ? 'Yes' : 'No'}</p>
                </div>
                <div>
                  <span className="text-muted-foreground">Created</span>
                  <p>{formatDate(detailPromo.created)}</p>
                </div>
                {detailPromo.expires_at && (
                  <div>
                    <span className="text-muted-foreground">Expires</span>
                    <p>{formatDate(detailPromo.expires_at)}</p>
                  </div>
                )}
              </div>

              {/* Redemption List */}
              {detailPromo.redeemed_by.length > 0 && (
                <div>
                  <h3 className="text-sm font-medium mb-2">Redeemed By</h3>
                  <div className="border rounded-md divide-y">
                    {detailPromo.redeemed_by.map(r => (
                      <div key={r.organization_id} className="px-3 py-2 text-sm flex items-center justify-between">
                        <span>{r.organization_name}</span>
                        <span className="text-muted-foreground text-xs">
                          {r.redeemed_at ? formatDate(r.redeemed_at) : '-'}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setDetailPromo(null)}>
              Close
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Deactivate Confirmation Dialog */}
      <Dialog open={!!deactivatingPromo} onOpenChange={(open) => !open && setDeactivatingPromo(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Deactivate Promo Code</DialogTitle>
          </DialogHeader>
          <p className="text-muted-foreground">
            Are you sure you want to deactivate <span className="font-mono font-medium text-foreground">{deactivatingPromo?.code}</span>? It will no longer be usable by customers.
          </p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeactivatingPromo(null)}>Cancel</Button>
            <Button variant="destructive" onClick={handleDeactivate} disabled={isDeactivating}>
              {isDeactivating && <Loader2 className="w-4 h-4 animate-spin mr-2" />}
              Deactivate
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <Dialog open={!!deletingPromo} onOpenChange={(open) => !open && setDeletingPromo(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete Promo Code</DialogTitle>
          </DialogHeader>
          <p className="text-muted-foreground">
            Are you sure you want to delete <span className="font-mono font-medium text-foreground">{deletingPromo?.code}</span>? This will deactivate the promo code and delete the associated coupon if unused.
          </p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeletingPromo(null)}>Cancel</Button>
            <Button variant="destructive" onClick={handleDelete} disabled={isDeleting}>
              {isDeleting && <Loader2 className="w-4 h-4 animate-spin mr-2" />}
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
