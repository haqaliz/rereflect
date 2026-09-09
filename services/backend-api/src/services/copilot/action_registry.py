"""
Copilot action registry (copilot-suggested-actions, PRD M1/M5).

The registry is the ONLY dispatch path for copilot-suggested actions: a stable
`action` id maps to an `ActionEntry` declaring `min_role`, a params validator,
and the executor callable. An unknown action id is rejected before anything
else happens — the model never names an executor directly (structural
precedent: `sql_validator.py` + `schema_whitelist.py` on the read path).

`min_role` is enforced HERE at execute time (PRD M5), independent of whatever
the executor's underlying route dependency permits. The execute route therefore
carries no role dependency of its own; RBAC is the registry's.

Slice-1 entry: `tag_customers` (min_role "admin") executes the same logic as
`POST /api/v1/customers/bulk/tags` — `cohort_service.resolve_cohort` over the
proposal's frozen emails, then `customer_tags.apply_tags` in add-mode —
without an internal HTTP request.
"""
from dataclasses import dataclass
from typing import Any, Callable, Dict, List

from sqlalchemy.orm import Session

from src.models.organization import Organization
from src.schemas.cohort import BulkActionSummary, Cohort
from src.services.cohort_service import resolve_cohort
from src.services.customer_tags import TAG_MAX_LENGTH, apply_tags

COPILOT_ACTION_AUDIT_ACTION = "copilot_action_executed"

role_level = {"member": 1, "admin": 2, "owner": 3}


class UnknownActionError(Exception):
    """Raised when an action id is not in the registry."""


class InsufficientRoleError(Exception):
    """Raised when the user's role is below the entry's `min_role`."""


@dataclass(frozen=True)
class ActionEntry:
    """One executable action: who may run it, what params it takes, what runs."""

    action_id: str
    min_role: str
    executor: Callable[..., Any]
    params_validator: Callable[[Dict[str, Any]], Any]


def get_entry(action_id: str) -> ActionEntry:
    """Look up an action by id, raising `UnknownActionError` on a miss."""
    try:
        return ACTION_REGISTRY[action_id]
    except KeyError:
        raise UnknownActionError(action_id)


def require_role(entry: ActionEntry, user: Any) -> None:
    """Raise `InsufficientRoleError` (route: 403) when the user's role is below
    the entry's `min_role`. Only `user.role` is read, so any User-like object
    (including the SQLAlchemy User row) works."""
    if role_level.get(user.role, 0) < role_level[entry.min_role]:
        raise InsufficientRoleError(
            f"action '{entry.action_id}' requires role '{entry.min_role}'"
        )


# ---------------------------------------------------------------------------
# tag_customers — params validator + executor
# ---------------------------------------------------------------------------


def _validate_tag_params(params: Dict[str, Any]) -> str:
    """Validate/clean the user-supplied single tag (PRD M6: the user supplies
    the tag; the server never guesses one). Mirrors `BulkTagRequest._clean_tags`
    semantics for one value: trimmed; empty after strip or over 50 chars is a
    ValueError (route: 422)."""
    tag = str((params or {}).get("tag", "")).strip()
    if not tag:
        raise ValueError("tag is required")
    if len(tag) > TAG_MAX_LENGTH:
        raise ValueError(
            f"Tag '{tag[:20]}...' exceeds the {TAG_MAX_LENGTH}-character limit"
        )
    return tag


def _execute_tag_customers(
    db: Session,
    org: Organization,
    *,
    emails: List[str],
    tag: str,
) -> BulkActionSummary:
    """Apply `tag` (add-mode) to the org's customers matching the FROZEN
    proposal emails. Emails that no longer belong to the org are absorbed by
    `resolve_cohort` as `skipped`, never errors and never a cross-org write.
    Does not commit — the caller owns the transaction (failure must never
    leave a success audit row)."""
    rows, skipped = resolve_cohort(db, org, Cohort(emails=emails))
    updated, errors = apply_tags(rows, [tag], "add")
    return BulkActionSummary(
        matched=len(rows), updated=updated, skipped=skipped, errors=errors
    )


ACTION_REGISTRY: Dict[str, ActionEntry] = {
    "tag_customers": ActionEntry(
        action_id="tag_customers",
        min_role="admin",
        executor=_execute_tag_customers,
        params_validator=_validate_tag_params,
    ),
}
