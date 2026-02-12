"""
Intercom write-back service for two-way sync.

Provides functions to add notes, close conversations, and fetch admin info
from the Intercom API.
"""

import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

INTERCOM_API_BASE = "https://api.intercom.io"


def _headers(access_token: str) -> dict:
    """Build authorization headers for Intercom API."""
    return {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def add_note_to_conversation(
    access_token: str,
    conversation_id: str,
    admin_id: str,
    note_body: str,
) -> bool:
    """
    Add an admin note to an Intercom conversation.

    Used when feedback status changes in Rereflect to sync back to Intercom.

    Args:
        access_token: Intercom OAuth access token
        conversation_id: Intercom conversation ID
        admin_id: Intercom admin ID for the note author
        note_body: HTML or plain text note content

    Returns:
        True if successful, False otherwise
    """
    try:
        with httpx.Client(timeout=15) as client:
            response = client.post(
                f"{INTERCOM_API_BASE}/conversations/{conversation_id}/reply",
                headers=_headers(access_token),
                json={
                    "message_type": "note",
                    "type": "admin",
                    "admin_id": admin_id,
                    "body": note_body,
                },
            )
            response.raise_for_status()
            logger.info(f"Added note to Intercom conversation {conversation_id}")
            return True
    except httpx.HTTPError as e:
        logger.error(f"Failed to add note to Intercom conversation {conversation_id}: {e}")
        return False


def close_conversation(
    access_token: str,
    conversation_id: str,
    admin_id: str,
) -> bool:
    """
    Close an Intercom conversation.

    Used when feedback is resolved in Rereflect.

    Args:
        access_token: Intercom OAuth access token
        conversation_id: Intercom conversation ID
        admin_id: Intercom admin ID performing the close

    Returns:
        True if successful, False otherwise
    """
    try:
        with httpx.Client(timeout=15) as client:
            response = client.post(
                f"{INTERCOM_API_BASE}/conversations/{conversation_id}/parts",
                headers=_headers(access_token),
                json={
                    "message_type": "close",
                    "type": "admin",
                    "admin_id": admin_id,
                },
            )
            response.raise_for_status()
            logger.info(f"Closed Intercom conversation {conversation_id}")
            return True
    except httpx.HTTPError as e:
        logger.error(f"Failed to close Intercom conversation {conversation_id}: {e}")
        return False


def get_admin_id(access_token: str) -> Optional[str]:
    """
    Get the admin ID for the authenticated Intercom app.

    Args:
        access_token: Intercom OAuth access token

    Returns:
        Admin ID string, or None if the request fails
    """
    try:
        with httpx.Client(timeout=15) as client:
            response = client.get(
                f"{INTERCOM_API_BASE}/me",
                headers=_headers(access_token),
            )
            response.raise_for_status()
            data = response.json()
            return data.get("id")
    except httpx.HTTPError as e:
        logger.error(f"Failed to get Intercom admin ID: {e}")
        return None
