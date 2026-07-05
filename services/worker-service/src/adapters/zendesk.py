"""
Zendesk adapter for handling Zendesk ticket events (pull + webhook).

Shared ingestion core consumed by both the ingestion-pull and ingestion-webhook
aspects. See docs/planning/zendesk-integration/ingestion-core/plan_20260705.md
for the locked contracts this adapter implements.
"""

import logging
from typing import Optional, Dict, Any, Tuple

from .base import BaseSourceAdapter

logger = logging.getLogger(__name__)


class ZendeskAdapter(BaseSourceAdapter):
    """
    Adapter for Zendesk ticket events.

    Handles the "ticket.created" event type (new tickets only, per PRD scope).
    Dedup key is the ticket id — one feedback item per ticket.
    """

    TICKET_CREATED = "ticket.created"

    def check_triggers(
        self,
        event_type: str,
        event_data: Dict[str, Any],
        triggers: Dict[str, Any],
    ) -> Optional[str]:
        # Filled in Phase 3.
        raise NotImplementedError

    def extract_content(
        self,
        event_data: Dict[str, Any],
        field_mapping: Dict[str, Any],
    ) -> Dict[str, Any]:
        # Filled in Phase 2.
        raise NotImplementedError

    def get_external_ids(
        self,
        event_data: Dict[str, Any],
    ) -> Tuple[str, Optional[str]]:
        ticket_id = str(event_data.get("ticket", {}).get("id"))
        return ticket_id, ticket_id

    def fetch_context(
        self,
        event_data: Dict[str, Any],
        access_token: Optional[str],
        field_mapping: Dict[str, Any],
    ) -> Dict[str, Any]:
        # Filled in Phase 4.
        return {}
