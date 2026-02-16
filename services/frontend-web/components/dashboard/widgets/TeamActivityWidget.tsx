'use client';

import { Users } from 'lucide-react';
import { TeamMember } from '@/lib/api/dashboard-v2';

interface TeamActivityWidgetProps {
  members: TeamMember[];
}

function getInitials(email: string): string {
  const name = email.split('@')[0];
  const parts = name.split(/[._-]/);
  if (parts.length >= 2) {
    return (parts[0][0] + parts[1][0]).toUpperCase();
  }
  return name.slice(0, 2).toUpperCase();
}

function getRelativeTime(dateStr: string | null): string {
  if (!dateStr) return 'Never';
  const now = Date.now();
  const then = new Date(dateStr).getTime();
  const diffMs = now - then;
  const diffSec = Math.floor(diffMs / 1000);

  if (diffSec < 60) return 'Just now';
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  const diffDay = Math.floor(diffHr / 24);
  return `${diffDay}d ago`;
}

const roleBadgeColors: Record<string, string> = {
  owner: 'var(--chart-1)',
  admin: 'var(--chart-2)',
  member: 'var(--chart-3)',
};

export function TeamActivityWidget({ members }: TeamActivityWidgetProps) {
  // Sort by most active first (actions_count + feedback_imported_count)
  const sorted = [...members].sort(
    (a, b) => (b.actions_count + b.feedback_imported_count) - (a.actions_count + a.feedback_imported_count)
  );

  const avatarColors = [
    'var(--chart-1)',
    'var(--chart-2)',
    'var(--chart-4)',
    'var(--chart-5)',
    'var(--chart-6)',
    'var(--chart-7)',
  ];

  return sorted.length > 0 ? (
    <div className="flex-1 overflow-y-auto">
            {sorted.map((member, index) => {
              const avatarColor = avatarColors[index % avatarColors.length];
              const roleColor = roleBadgeColors[member.role] || 'var(--muted-foreground)';

              return (
                <div
                  key={member.user_id}
                  className="flex items-center gap-3 px-4 py-3 border-b last:border-b-0"
                  style={{ borderBottomColor: 'var(--border)' }}
                >
                  {/* Avatar */}
                  <div
                    className="w-9 h-9 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0"
                    style={{
                      backgroundColor: `color-mix(in oklch, ${avatarColor} 20%, transparent)`,
                      color: avatarColor,
                    }}
                  >
                    {getInitials(member.email)}
                  </div>

                  {/* Name + Role */}
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-foreground truncate">{member.email}</p>
                    <div className="flex items-center gap-2 mt-0.5">
                      <span
                        className="text-xs font-semibold px-1.5 py-0.5 rounded capitalize"
                        style={{
                          backgroundColor: `color-mix(in oklch, ${roleColor} 15%, transparent)`,
                          color: roleColor,
                        }}
                      >
                        {member.role}
                      </span>
                      <span className="text-xs text-muted-foreground">
                        {getRelativeTime(member.last_active_at)}
                      </span>
                    </div>
                  </div>

                  {/* Activity counts */}
                  <div className="flex items-center gap-3 flex-shrink-0">
                    <div className="text-center">
                      <p className="text-sm font-bold font-mono text-foreground">{member.feedback_imported_count}</p>
                      <p className="text-xs text-muted-foreground">imports</p>
                    </div>
                    <div className="text-center">
                      <p className="text-sm font-bold font-mono text-foreground">{member.actions_count}</p>
                      <p className="text-xs text-muted-foreground">actions</p>
                    </div>
                  </div>
                </div>
              );
            })}
    </div>
  ) : (
    <div className="flex flex-col items-center justify-center text-muted-foreground min-h-[300px]">
      <Users className="w-12 h-12 mb-3 opacity-20" />
      <p className="text-sm">No team activity data available</p>
    </div>
  );
}
