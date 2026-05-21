'use client';

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Label } from '@/components/ui/label';
import type { ChurnReasonCode } from '@/lib/api/churn-events';
import { CHURN_REASON_CODES, CHURN_REASON_LABELS } from '@/lib/constants/churn';

interface ReasonCodeSelectProps {
  value: ChurnReasonCode | '';
  onChange: (value: ChurnReasonCode) => void;
  id?: string;
  label?: string;
}

export function ReasonCodeSelect({
  value,
  onChange,
  id = 'reason-code',
  label = 'Reason',
}: ReasonCodeSelectProps) {
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>{label}</Label>
      <Select value={value || undefined} onValueChange={(v) => onChange(v as ChurnReasonCode)}>
        <SelectTrigger id={id}>
          <SelectValue placeholder="Select a reason..." />
        </SelectTrigger>
        <SelectContent>
          {CHURN_REASON_CODES.map((code) => (
            <SelectItem key={code} value={code}>
              {CHURN_REASON_LABELS[code]}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}
