/**
 * Rereflect's canonical feedback workflow statuses — the mapping *target*
 * shared by every inbound status-sync integration (Linear, Jira, Asana,
 * Zendesk). Relocated out of `lib/api/linear.ts` (mapping-editor aspect,
 * status-sync-realtime-mapping PRD) so non-Linear status-mapping editors can
 * import it without pulling in Linear-specific API types.
 */
export const REREFLECT_STATUSES = [
  { value: 'new', label: 'New' },
  { value: 'in_review', label: 'In Review' },
  { value: 'resolved', label: 'Resolved' },
  { value: 'closed', label: 'Closed' },
] as const;
