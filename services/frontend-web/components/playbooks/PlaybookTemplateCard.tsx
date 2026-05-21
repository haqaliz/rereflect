'use client';

import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Switch } from '@/components/ui/switch';
import { ListChecks, Zap, UserCheck, Bell, Bot, RefreshCcw } from 'lucide-react';
import { type Playbook, formatProbabilityRange, ACTION_TYPE_LABELS } from '@/lib/api/playbooks';

// ─── ActionTypeBadge ──────────────────────────────────────────────────────────

const ACTION_ICONS: Record<string, React.ReactNode> = {
  assign: <UserCheck className="w-3 h-3" />,
  change_status: <RefreshCcw className="w-3 h-3" />,
  send_notification: <Bell className="w-3 h-3" />,
  draft_response: <Bot className="w-3 h-3" />,
};

export function ActionTypeBadge({ type }: { type: string }) {
  const label = ACTION_TYPE_LABELS[type] ?? type;
  const icon = ACTION_ICONS[type] ?? <Zap className="w-3 h-3" />;
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs bg-muted text-muted-foreground">
      {icon}
      {label}
    </span>
  );
}

// ─── PlaybookTemplateCard ─────────────────────────────────────────────────────

interface PlaybookTemplateCardProps {
  playbook: Playbook;
  onUse: (playbook: Playbook) => void;
  onToggleActive?: (newValue: boolean) => void;
}

export function PlaybookTemplateCard({ playbook, onUse, onToggleActive }: PlaybookTemplateCardProps) {
  const probRange = formatProbabilityRange(playbook.probability_min, playbook.probability_max);
  const actionCount = playbook.action_sequence.length;

  return (
    <Card className="hover:border-primary/40 transition-colors">
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-2 min-w-0">
            <div className="p-1.5 rounded-lg bg-secondary shrink-0">
              <ListChecks className="w-4 h-4 text-primary" />
            </div>
            <CardTitle className="text-sm font-semibold leading-snug truncate">
              {playbook.name}
            </CardTitle>
          </div>
          {!playbook.is_template && onToggleActive && (
            <Switch
              checked={playbook.is_active}
              onCheckedChange={onToggleActive}
              aria-label={playbook.is_active ? 'Deactivate playbook' : 'Activate playbook'}
            />
          )}
        </div>
      </CardHeader>

      <CardContent className="space-y-3">
        {playbook.description && (
          <p className="text-xs text-muted-foreground leading-snug">{playbook.description}</p>
        )}

        <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          <Badge variant="outline" className="font-normal text-xs">
            {probRange}
          </Badge>
          <span>{actionCount} action{actionCount !== 1 ? 's' : ''}</span>
        </div>

        <div className="flex flex-wrap gap-1">
          {playbook.action_sequence.slice(0, 3).map((action, i) => (
            <ActionTypeBadge key={i} type={action.type} />
          ))}
          {playbook.action_sequence.length > 3 && (
            <span className="text-xs text-muted-foreground px-1">
              +{playbook.action_sequence.length - 3} more
            </span>
          )}
        </div>

        {playbook.is_template && (
          <div className="pt-1">
            <Button
              size="sm"
              variant="outline"
              className="w-full text-xs h-7"
              onClick={() => onUse(playbook)}
            >
              Use template
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
