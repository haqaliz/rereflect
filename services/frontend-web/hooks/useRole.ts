import { useAuth } from '@/contexts/AuthContext';

export function useRole() {
  const { user, isLoading } = useAuth();
  const isOwner = user?.role === 'owner';
  const isAdminOrOwner = isOwner || user?.role === 'admin';
  return { isOwner, isAdminOrOwner, isLoading };
}
