'use client';

import React, { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { PlaySquare, ChevronDown, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { useAuth } from '@/contexts/AuthContext';
import { listPlaybooks, runPlaybook, type Playbook, formatProbabilityRange } from '@/lib/api/playbooks';

interface RunPlaybookDropdownProps {
  customerEmail: string;
  churnProbability: number | null | undefined;
}

export function RunPlaybookDropdown({ customerEmail, churnProbability }: RunPlaybookDropdownProps) {
  const { user } = useAuth();
  const [playbooks, setPlaybooks] = useState<Playbook[]>([]);
  const [running, setRunning] = useState<number | null>(null);

  const isBusiness = user?.plan === 'business' || user?.plan === 'enterprise';

  useEffect(() => {
    if (!isBusiness || churnProbability == null) return;
    listPlaybooks()
      .then((all) => {
        const matching = all.filter(
          (p) =>
            !p.is_template &&
            p.is_active &&
            churnProbability >= p.probability_min &&
            churnProbability <= p.probability_max
        );
        setPlaybooks(matching);
      })
      .catch(() => {
        // silently ignore; dropdown stays empty
      });
  }, [isBusiness, churnProbability]);

  // Not rendered for non-Business plans or when probability is unknown
  if (!isBusiness || churnProbability == null) return null;

  const handleRun = async (playbook: Playbook) => {
    setRunning(playbook.id);
    try {
      const execution = await runPlaybook(playbook.id, customerEmail);
      toast.success(`Playbook queued (#${execution.id})`);
    } catch {
      toast.error('Failed to queue playbook. Please try again.');
    } finally {
      setRunning(null);
    }
  };

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="sm" className="flex items-center gap-1.5">
          <PlaySquare className="w-3.5 h-3.5" />
          Run Playbook
          <ChevronDown className="w-3 h-3 text-muted-foreground" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-56">
        {playbooks.length === 0 ? (
          <DropdownMenuItem disabled className="text-muted-foreground text-xs">
            No matching playbooks for {Math.round(churnProbability * 100)}% probability
          </DropdownMenuItem>
        ) : (
          playbooks.map((pb) => (
            <DropdownMenuItem
              key={pb.id}
              onClick={() => handleRun(pb)}
              disabled={running === pb.id}
              className="flex items-center justify-between"
            >
              <span className="truncate">{pb.name}</span>
              <span className="text-xs text-muted-foreground ml-2 shrink-0">
                {formatProbabilityRange(pb.probability_min, pb.probability_max)}
              </span>
              {running === pb.id && <Loader2 className="w-3.5 h-3.5 animate-spin ml-2 shrink-0" />}
            </DropdownMenuItem>
          ))
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
