import type { StatusMappingForeignKey } from '@/components/settings/StatusMappingEditor';

/**
 * Hardcoded canonical foreign-key lists for each inbound status-sync
 * provider's `StatusMappingEditor` (mapping-editor aspect). No discovery
 * endpoint — these mirror the backend's `_validate_status_mapping` allow-lists
 * exactly (jira_integration.py / asana_integration.py / zendesk_integration.py).
 *
 * Jira and Asana map at STATUS-CATEGORY granularity (not raw status names) —
 * labels say "Category" explicitly so the editor is honest about what it's
 * mapping (spec G4/M8). Zendesk maps at raw-status granularity.
 */

export const JIRA_STATUS_MAPPING_KEYS: StatusMappingForeignKey[] = [
  { key: 'new', label: 'Category: To Do (new)' },
  { key: 'indeterminate', label: 'Category: In Progress (indeterminate)' },
  { key: 'done', label: 'Category: Done' },
];

export const ASANA_STATUS_MAPPING_KEYS: StatusMappingForeignKey[] = [
  { key: 'new', label: 'Not completed' },
  { key: 'done', label: 'Completed' },
];

export const ZENDESK_STATUS_MAPPING_KEYS: StatusMappingForeignKey[] = [
  { key: 'new', label: 'New' },
  { key: 'open', label: 'Open' },
  { key: 'pending', label: 'Pending' },
  { key: 'hold', label: 'On-hold' },
  { key: 'solved', label: 'Solved' },
  { key: 'closed', label: 'Closed' },
];
