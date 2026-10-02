import { describe, it, expect, vi } from 'vitest';
import { renderHook } from '@testing-library/react';

const authMock = vi.hoisted(() => ({
  user: { role: 'owner' } as { role: string } | null,
  isLoading: false,
}));
vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({ user: authMock.user, isLoading: authMock.isLoading }),
}));

import { useRole } from '@/hooks/useRole';

describe('useRole', () => {
  it('owner is owner and admin-or-owner', () => {
    authMock.user = { role: 'owner' };
    const { result } = renderHook(() => useRole());
    expect(result.current.isOwner).toBe(true);
    expect(result.current.isAdminOrOwner).toBe(true);
  });

  it('admin is admin-or-owner but not owner', () => {
    authMock.user = { role: 'admin' };
    const { result } = renderHook(() => useRole());
    expect(result.current.isOwner).toBe(false);
    expect(result.current.isAdminOrOwner).toBe(true);
  });

  it('member has neither', () => {
    authMock.user = { role: 'member' };
    const { result } = renderHook(() => useRole());
    expect(result.current.isOwner).toBe(false);
    expect(result.current.isAdminOrOwner).toBe(false);
  });

  it('no user has neither and passes isLoading through', () => {
    authMock.user = null;
    authMock.isLoading = true;
    const { result } = renderHook(() => useRole());
    expect(result.current.isOwner).toBe(false);
    expect(result.current.isAdminOrOwner).toBe(false);
    expect(result.current.isLoading).toBe(true);
    authMock.isLoading = false;
  });
});
