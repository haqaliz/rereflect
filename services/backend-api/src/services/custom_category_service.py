"""
Shared CRUD for CustomCategory — used by both the internal
``/api/v1/categories/custom`` routes and the public ``/api/public/v1/categories``
routes so create/update/delete/list semantics can't drift between the two
surfaces (char-locked against the pre-existing internal route in
``src/api/routes/categories.py``).

Also hosts ``rules_referencing_category`` — a cheap, org-scoped lookup used by
the delete/rename warning: is this category name referenced by an *active*
``feedback_category_match`` automation rule?
"""

from __future__ import annotations

from typing import List, Optional

from sqlalchemy.orm import Session

from src.models.automation_rule import AutomationRule
from src.models.custom_category import CustomCategory


class DuplicateCategoryError(Exception):
    """Raised when a category with the same (org, category_type, name) already exists."""

    def __init__(self, category_type: str, name: str):
        self.category_type = category_type
        self.name = name
        super().__init__(f"A {category_type} category named '{name}' already exists")


class CategoryNotFoundError(Exception):
    """Raised when a category id doesn't exist (or belongs to a different org)."""

    def __init__(self, category_id: int):
        self.category_id = category_id
        super().__init__(f"Category {category_id} not found")


def list_categories(
    db: Session, org_id: int, category_type: Optional[str] = None
) -> List[CustomCategory]:
    """List an org's custom categories, optionally filtered by type, name-sorted."""
    query = db.query(CustomCategory).filter(CustomCategory.organization_id == org_id)
    if category_type:
        query = query.filter(CustomCategory.category_type == category_type)
    return query.order_by(CustomCategory.name).all()


def create_category(
    db: Session,
    org_id: int,
    *,
    name: str,
    description: Optional[str],
    category_type: str,
) -> CustomCategory:
    """Create a custom category. Raises ``DuplicateCategoryError`` on (org, type, name) collision."""
    existing = (
        db.query(CustomCategory)
        .filter(
            CustomCategory.organization_id == org_id,
            CustomCategory.name == name,
            CustomCategory.category_type == category_type,
        )
        .first()
    )
    if existing:
        raise DuplicateCategoryError(category_type, name)

    category = CustomCategory(
        organization_id=org_id,
        name=name,
        description=description,
        category_type=category_type,
    )
    db.add(category)
    db.commit()
    db.refresh(category)
    return category


def _get_org_category(db: Session, org_id: int, category_id: int) -> CustomCategory:
    category = (
        db.query(CustomCategory)
        .filter(
            CustomCategory.id == category_id,
            CustomCategory.organization_id == org_id,
        )
        .first()
    )
    if not category:
        raise CategoryNotFoundError(category_id)
    return category


def update_category(
    db: Session,
    org_id: int,
    category_id: int,
    *,
    name: Optional[str] = None,
    description: Optional[str] = None,
    is_active: Optional[bool] = None,
) -> CustomCategory:
    """Update name/description/is_active. ``category_type`` is not editable here.

    Raises ``CategoryNotFoundError`` (missing/other-org) or ``DuplicateCategoryError``
    (rename collision within the same org + category_type).
    """
    category = _get_org_category(db, org_id, category_id)

    if name is not None:
        existing = (
            db.query(CustomCategory)
            .filter(
                CustomCategory.organization_id == org_id,
                CustomCategory.name == name,
                CustomCategory.category_type == category.category_type,
                CustomCategory.id != category_id,
            )
            .first()
        )
        if existing:
            raise DuplicateCategoryError(category.category_type, name)
        category.name = name

    if description is not None:
        category.description = description
    if is_active is not None:
        category.is_active = is_active

    db.commit()
    db.refresh(category)
    return category


def delete_category(db: Session, org_id: int, category_id: int) -> CustomCategory:
    """Hard-delete a category. Raises ``CategoryNotFoundError`` (missing/other-org)."""
    category = _get_org_category(db, org_id, category_id)
    db.delete(category)
    db.commit()
    return category


def rules_referencing_category(db: Session, org_id: int, name: str) -> List[str]:
    """Return the names of *active* ``feedback_category_match`` automation rules
    whose ``trigger_config["categories"]`` list contains ``name``.

    The matched-category value lives under the ``categories`` key of
    ``trigger_config`` (see ``FeedbackCategoryConfig`` in
    ``src/api/routes/automations.py`` and
    ``AutomationEngine._trigger_feedback_category`` in
    ``src/services/automation_engine.py``, which reads
    ``cfg.get("categories", [])``).

    Only active rules are considered — inactive rules never fire, so they
    can't produce a false-positive delete/rename warning.
    """
    rules = (
        db.query(AutomationRule)
        .filter(
            AutomationRule.organization_id == org_id,
            AutomationRule.trigger_type == "feedback_category_match",
            AutomationRule.is_active == True,  # noqa: E712
        )
        .all()
    )
    matches: List[str] = []
    for rule in rules:
        cfg = rule.trigger_config or {}
        categories = cfg.get("categories") or []
        if name in categories:
            matches.append(rule.name)
    return matches
