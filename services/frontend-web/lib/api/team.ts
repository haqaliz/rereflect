import apiClient from '../api-client';

// Team member types
export interface TeamMember {
  id: number;
  email: string;
  role: 'owner' | 'admin' | 'member';
  last_active_at: string | null;
  joined_at: string | null;
  invited_by_id: number | null;
}

export interface TeamMembersResponse {
  members: TeamMember[];
  total: number;
  seats_used: number;
  seats_limit: number | null;
}

// Team invite types
export interface TeamInvite {
  id: number;
  email: string;
  role: 'admin' | 'member';
  status: 'pending' | 'accepted' | 'expired' | 'canceled';
  created_at: string;
  expires_at: string;
  invited_by_id: number;
}

export interface TeamInvitesResponse {
  invites: TeamInvite[];
}

// Request types
export interface InviteMemberRequest {
  email: string;
  role: 'admin' | 'member';
}

export interface UpdateRoleRequest {
  role: 'admin' | 'member';
}

export const teamAPI = {
  /**
   * Get all team members for the organization
   */
  getTeam: async (): Promise<TeamMembersResponse> => {
    const response = await apiClient.get('/api/v1/team/members');
    return response.data;
  },

  /**
   * Get all pending invites for the organization
   */
  getInvites: async (): Promise<TeamInvitesResponse> => {
    const response = await apiClient.get('/api/v1/team/invites');
    return response.data;
  },

  /**
   * Invite a new member to the organization
   */
  inviteMember: async (data: InviteMemberRequest): Promise<TeamInvite> => {
    const response = await apiClient.post('/api/v1/team/invites', data);
    return response.data;
  },

  /**
   * Update a member's role
   */
  updateRole: async (userId: number, data: UpdateRoleRequest): Promise<TeamMember> => {
    const response = await apiClient.patch(`/api/v1/team/members/${userId}/role`, data);
    return response.data;
  },

  /**
   * Remove a member from the organization
   */
  removeMember: async (userId: number): Promise<void> => {
    await apiClient.delete(`/api/v1/team/members/${userId}`);
  },

  /**
   * Resend an invite email
   */
  resendInvite: async (inviteId: number): Promise<TeamInvite> => {
    const response = await apiClient.post(`/api/v1/team/invites/${inviteId}/resend`);
    return response.data;
  },

  /**
   * Cancel a pending invite
   */
  cancelInvite: async (inviteId: number): Promise<void> => {
    await apiClient.delete(`/api/v1/team/invites/${inviteId}`);
  },

  /**
   * Transfer organization ownership to another member
   */
  transferOwnership: async (userId: number): Promise<TeamMember> => {
    const response = await apiClient.post(`/api/v1/team/transfer-ownership`, { user_id: userId });
    return response.data;
  },
};

// Helper functions
export function getRoleLabel(role: 'owner' | 'admin' | 'member'): string {
  switch (role) {
    case 'owner':
      return 'Owner';
    case 'admin':
      return 'Admin';
    case 'member':
      return 'Member';
    default:
      return role;
  }
}

export function getRoleColor(role: 'owner' | 'admin' | 'member'): string {
  switch (role) {
    case 'owner':
      return 'text-amber-600 border-amber-600/30 bg-amber-50 dark:bg-amber-950';
    case 'admin':
      return 'text-blue-600 border-blue-600/30 bg-blue-50 dark:bg-blue-950';
    case 'member':
      return 'text-green-600 border-green-600/30 bg-green-50 dark:bg-green-950';
    default:
      return 'text-muted-foreground';
  }
}

export function getInviteStatusLabel(status: TeamInvite['status']): string {
  switch (status) {
    case 'pending':
      return 'Pending';
    case 'accepted':
      return 'Accepted';
    case 'expired':
      return 'Expired';
    case 'canceled':
      return 'Canceled';
    default:
      return status;
  }
}

export function getInviteStatusColor(status: TeamInvite['status']): string {
  switch (status) {
    case 'pending':
      return 'text-yellow-600 border-yellow-600/30 bg-yellow-50 dark:bg-yellow-950';
    case 'accepted':
      return 'text-green-600 border-green-600/30 bg-green-50 dark:bg-green-950';
    case 'expired':
      return 'text-red-600 border-red-600/30 bg-red-50 dark:bg-red-950';
    case 'canceled':
      return 'text-muted-foreground border-muted-foreground/30 bg-muted';
    default:
      return 'text-muted-foreground';
  }
}

export function formatRelativeTime(dateString: string | null): string {
  if (!dateString) return 'Never';

  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);

  if (diffMins < 1) return 'Just now';
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;

  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: date.getFullYear() !== now.getFullYear() ? 'numeric' : undefined,
  });
}
