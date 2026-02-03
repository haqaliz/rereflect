# PRD: Team Management & Role-Based Access Control

## Overview

Implement team management with role-based access control (RBAC) for Rereflect, enabling organizations to invite team members, assign roles, and control access to features based on permissions.

## Goals

1. Allow organizations to invite and manage team members
2. Implement 3-tier role system: Owner, Admin, Member
3. Enforce seat limits based on subscription tier
4. Provide audit logging for Business+ tiers
5. Enable secure ownership transfer

## Non-Goals

- Multi-organization membership (users belong to one org only)
- Custom role creation
- SSO/SAML integration (separate Enterprise feature)
- Bulk user import

---

## Role Hierarchy

### Owner (1 per organization)
The organization creator. Cannot be removed, only transferred.

**Exclusive Powers:**
- Manage billing & subscription
- Delete organization
- Transfer ownership to another member

**Inherited Powers:** All Admin permissions

### Admin
Team managers who can invite users and manage settings.

**Powers:**
- Invite new members (email invite)
- Remove members from organization
- Change member roles (except Owner)
- Manage integrations (Slack, webhooks)
- Manage feedback sources
- Manage API keys (Business+)
- Resend/cancel pending invites
- View audit logs (Business+)

**Inherited Powers:** All Member permissions

### Member
Standard users with read and import access.

**Powers:**
- View dashboard & analytics
- View all feedback items
- Import feedback via CSV
- Export data (Pro+ plans)

**Cannot:**
- Invite or remove users
- Manage integrations or feedback sources
- Access billing settings
- Change any settings

---

## Permission Matrix

| Action | Owner | Admin | Member |
|--------|-------|-------|--------|
| View dashboard & analytics | ✅ | ✅ | ✅ |
| View feedback items | ✅ | ✅ | ✅ |
| Import feedback (CSV) | ✅ | ✅ | ✅ |
| Export data (Pro+) | ✅ | ✅ | ✅ |
| Manage feedback sources | ✅ | ✅ | ❌ |
| Manage integrations | ✅ | ✅ | ❌ |
| Manage API keys (Business+) | ✅ | ✅ | ❌ |
| Invite members | ✅ | ✅ | ❌ |
| Remove members | ✅ | ✅ | ❌ |
| Change member roles | ✅ | ✅ | ❌ |
| View audit logs (Business+) | ✅ | ✅ | ❌ |
| View team list | ✅ | ✅ | ✅ |
| Access billing | ✅ | ❌ | ❌ |
| Delete organization | ✅ | ❌ | ❌ |
| Transfer ownership | ✅ | ❌ | ❌ |

---

## Invitation System

### Flow
1. Admin enters email address and selects role (Admin or Member)
2. System checks seat availability
3. If seats available, create invite record and send email
4. Email contains unique invite link with token
5. Recipient clicks link → signup/login → joins organization
6. Invite marked as accepted, user added to team

### Rules
- **Expiry:** 7 days from creation
- **Who can invite:** Owner and Admins only
- **Seat check:** Only accepted members count toward limit
- **Resend:** Admins can resend expired invites (generates new token)
- **Cancel:** Admins can cancel pending invites

### Invite States
- `pending` - Sent, awaiting acceptance
- `accepted` - User joined the organization
- `expired` - Past 7-day window
- `canceled` - Manually canceled by admin

---

## Seat Management

### Limits by Tier
| Tier | Seat Limit |
|------|------------|
| Free | 2 |
| Pro | 10 |
| Business | 25 |
| Enterprise | Unlimited |

### Enforcement
- **Hard block:** Cannot send new invites when at seat limit
- **Pending invites:** Do NOT count toward limit
- **Upgrade prompt:** Show when approaching limit (80%+)

### Seat Counting
```
used_seats = count(users WHERE organization_id = org AND status = 'active')
available_seats = plan_seat_limit - used_seats
```

---

## User Removal

### Process
1. Admin/Owner initiates removal
2. System checks if target is Owner (block if yes)
3. User removed from organization
4. Resources created by user marked as "Former member"
5. Email notification sent to removed user
6. User's session invalidated

### Resource Handling
- Feedback sources: Keep, set `created_by_name = "Former member"`
- Integrations: Keep, transfer to removing admin
- Feedback items: Keep (org data, not user data)

### Restrictions
- Cannot remove Owner (must transfer first)
- Owner can remove all Admins (no minimum Admin requirement)
- Removed users cannot rejoin without new invite

---

## Ownership Transfer

### Process
1. Owner initiates transfer, selects target member
2. System creates pending transfer request
3. Email sent to target user with accept/decline link
4. Target accepts → roles swapped (new Owner, old becomes Admin)
5. Target declines or ignores → transfer expires after 7 days

### Rules
- Only Owner can initiate
- Can transfer to any member (Admin or Member)
- New Owner inherits billing access
- Old Owner becomes Admin
- Owner cannot delete account until transfer complete

---

## Email Notifications

### Triggered Events
| Event | Recipient | Template |
|-------|-----------|----------|
| Invite sent | Invitee | `team_invite` |
| Invite accepted | Admins | `invite_accepted` |
| Role changed | Affected user | `role_changed` |
| Removed from team | Removed user | `team_removal` |
| Ownership transfer request | Target user | `ownership_transfer` |
| Ownership transfer complete | Both users | `ownership_transferred` |

---

## Activity Tracking

### Last Active
- Update `last_active_at` on each authenticated API request
- Display in team list: "Active now", "5 min ago", "2 hours ago", "Yesterday", "Jan 15"

### Audit Logs (Business+ only)
Track the following events:
- User invited
- User joined
- User removed
- Role changed
- Ownership transferred
- Integration created/modified/deleted
- Feedback source created/modified/deleted
- API key created/revoked
- Data exported

Log entry fields:
```
{
  id, organization_id, user_id, user_email,
  action, target_type, target_id,
  details (JSON), ip_address, user_agent,
  created_at
}
```

---

## UI Design

### Location
`/settings/team` - Dedicated team management page

### Team Page Layout
```
┌─────────────────────────────────────────────────────┐
│ Team Members                        [+ Invite]      │
│ Manage your team and permissions                    │
├─────────────────────────────────────────────────────┤
│ ┌─────────────────────────────────────────────────┐ │
│ │ 👤 John Doe (you)           Owner    Active now │ │
│ │    john@company.com                             │ │
│ ├─────────────────────────────────────────────────┤ │
│ │ 👤 Jane Smith               Admin    2h ago    │ │
│ │    jane@company.com         [Change Role ▾] [×] │ │
│ ├─────────────────────────────────────────────────┤ │
│ │ 👤 Bob Wilson               Member   Yesterday │ │
│ │    bob@company.com          [Change Role ▾] [×] │ │
│ └─────────────────────────────────────────────────┘ │
├─────────────────────────────────────────────────────┤
│ Pending Invites (1)                                 │
│ ┌─────────────────────────────────────────────────┐ │
│ │ ✉️  alice@company.com       Member   Expires 5d │ │
│ │                             [Resend] [Cancel]   │ │
│ └─────────────────────────────────────────────────┘ │
├─────────────────────────────────────────────────────┤
│ Seats: 3/10 used                    [Upgrade Plan] │
└─────────────────────────────────────────────────────┘
```

### Invite Modal
```
┌──────────────────────────────────────┐
│ Invite Team Member                 × │
├──────────────────────────────────────┤
│ Email address                        │
│ ┌──────────────────────────────────┐ │
│ │ teammate@company.com             │ │
│ └──────────────────────────────────┘ │
│                                      │
│ Role                                 │
│ ○ Admin - Can manage team & settings │
│ ● Member - View and import only      │
│                                      │
│ [Cancel]              [Send Invite]  │
└──────────────────────────────────────┘
```

### Ownership Transfer (Owner only)
Located in Settings > Team > "Transfer Ownership" button (danger zone)

---

## Data Models

### User (existing, modified)
```python
class User:
    # ... existing fields ...
    role: str  # 'owner', 'admin', 'member'
    last_active_at: datetime
    invited_by_id: int | None
    joined_at: datetime
```

### TeamInvite (new)
```python
class TeamInvite:
    id: int
    organization_id: int
    email: str
    role: str  # 'admin', 'member'
    token: str  # unique invite token
    invited_by_id: int
    status: str  # 'pending', 'accepted', 'expired', 'canceled'
    created_at: datetime
    expires_at: datetime
    accepted_at: datetime | None
```

### OwnershipTransfer (new)
```python
class OwnershipTransfer:
    id: int
    organization_id: int
    from_user_id: int
    to_user_id: int
    token: str
    status: str  # 'pending', 'accepted', 'declined', 'expired'
    created_at: datetime
    expires_at: datetime
    resolved_at: datetime | None
```

### AuditLog (new, Business+)
```python
class AuditLog:
    id: int
    organization_id: int
    user_id: int
    user_email: str
    action: str
    target_type: str | None
    target_id: int | None
    details: dict  # JSON
    ip_address: str
    user_agent: str
    created_at: datetime
```

---

## API Endpoints

### Team Management
```
GET    /api/v1/team                    # List team members
POST   /api/v1/team/invite             # Send invite
GET    /api/v1/team/invites            # List pending invites
POST   /api/v1/team/invites/:id/resend # Resend invite
DELETE /api/v1/team/invites/:id        # Cancel invite
PATCH  /api/v1/team/:user_id/role      # Change role
DELETE /api/v1/team/:user_id           # Remove member
```

### Ownership
```
POST   /api/v1/team/transfer-ownership      # Initiate transfer
POST   /api/v1/team/transfer-ownership/accept  # Accept transfer
POST   /api/v1/team/transfer-ownership/decline # Decline transfer
```

### Invite Acceptance (public)
```
GET    /api/v1/invites/:token          # Get invite details
POST   /api/v1/invites/:token/accept   # Accept invite
```

### Audit Logs (Business+)
```
GET    /api/v1/audit-logs              # List audit logs (paginated)
```

---

## Implementation Phases

### Phase 1: Core RBAC (MVP) ✅ COMPLETE
- [x] Add `role` field to User model
- [x] Implement permission checking middleware (`require_admin_or_owner`, `require_owner`)
- [x] Update existing endpoints with role checks
- [x] Create team list endpoint
- [x] Frontend tab visibility by role (`SettingsTabs.tsx`)
- [x] Frontend route protection (billing, integrations pages redirect unauthorized users)
- [x] Conditional UI rendering (hide actions for members)

### Phase 2: Invitations ✅ COMPLETE
- [x] TeamInvite model and migration
- [x] Invite creation, listing, resend, cancel
- [x] Email sending for invites (Resend integration)
- [x] Invite acceptance flow (new/existing users)
- [x] `/invite/[token]` public page for accepting invites

### Phase 3: Team Management UI ✅ COMPLETE
- [x] Team settings page (`/settings/team`)
- [x] Invite modal (`InviteMemberModal.tsx`)
- [x] Role change dropdown
- [x] Remove member confirmation
- [x] Seat usage display
- [x] Pending invites section
- [x] Actions column hidden for members

### Phase 4: Ownership & Advanced ✅ COMPLETE
- [x] Ownership transfer flow (with TRANSFER confirmation)
- [x] Audit logging (Business+)
- [x] Last active tracking
- [x] Email notifications for invites (via Resend)

### Next Steps / Future Enhancements
- [ ] Email notifications for role changes, removals
- [ ] OAuth signup integration (Google Sign-In)
- [ ] SSO/SAML for Enterprise tier
- [ ] Custom roles (Enterprise feature)

---

## Success Metrics

- Team invite acceptance rate > 70%
- Average time to accept invite < 24 hours
- Support tickets about permissions < 5/month
- Seat utilization rate per tier

---

## Security Considerations

1. **Invite tokens:** Cryptographically random, single-use
2. **Rate limiting:** Max 10 invites per hour per org
3. **Session invalidation:** Immediate on role change or removal
4. **Audit log immutability:** Append-only, no deletion
5. **Owner protection:** Cannot be removed via any endpoint

---

## Open Questions

1. Should we allow role-specific API keys in the future?
2. Do we need a "suspended" user state for temporary access revocation?
3. Should audit logs be exportable?
