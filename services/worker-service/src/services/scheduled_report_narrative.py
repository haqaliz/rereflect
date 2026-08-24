"""
scheduled_report_narrative — concise data-led LLM narrative for scheduled reports.

The scheduled-report narrative is a short data-led summary (a few short
paragraphs citing the section data), NOT a re-streamed on-demand essay. It is
data-first: sections render their data regardless; narrative is added on top
only when an LLM resolves (BYOK per-org, via src.llm.org_resolver).

Contract:
    generate_report_narrative(report_data, org_id, db) -> Optional[str]

Follows the worker LLM pattern (src/llm_client.py): resolve org LLM via
org_resolver.call_llm_for_org (non-streaming completion, org_id-scoped),
return None on any absence/failure — NEVER raise.
"""

import logging
from typing import Optional

from sqlalchemy.orm import Session

from src.llm.org_resolver import call_llm_for_org
from src.llm.types import LLMRequest

logger = logging.getLogger(__name__)

# OrgAIConfig model column used for the narrative completion (same as insights).
_NARRATIVE_MODEL_COLUMN = "model_insights"
_DEFAULT_PROVIDER = "openai"
_DEFAULT_MODEL = "gpt-4o-mini"

NARRATIVE_PROMPT = (
    "You are a customer feedback analyst writing the narrative for a scheduled "
    "report. Write a concise, data-led summary in plain text. Cite the section "
    "headings and their headline numbers exactly as given. Use one short "
    "paragraph per section. Do not invent numbers. Keep it under ~200 words. "
    "Do not use markdown.\n\n"
    "Report sections:\n{sections}"
)


def _configured_model(org_id: int, db: Session) -> tuple[str, str]:
    """Resolve (provider, model) for the narrative completion from OrgAIConfig."""
    from src.models import OrgAIConfig

    config = db.query(OrgAIConfig).filter_by(organization_id=org_id).first()
    provider = config.default_provider if config else _DEFAULT_PROVIDER
    model = getattr(config, _NARRATIVE_MODEL_COLUMN, None) if config else None
    return provider, model or _DEFAULT_MODEL


def resolve_narrative_model(org_id: int, db: Session) -> Optional[str]:
    """Return the model the narrative writer would use, or None when unset.

    Lets the scheduled-generation task record `model_used` in the Report
    metadata without duplicating the OrgAIConfig lookup. Mirrors the default
    resolution inside generate_report_narrative.
    """
    if org_id is None or db is None:
        return None
    try:
        _, model = _configured_model(org_id, db)
        return model
    except Exception:
        logger.error("Failed to resolve narrative model for org %s", org_id)
        return None


def generate_report_narrative(
    report_data: dict,
    org_id: Optional[int],
    db: Optional[Session],
) -> Optional[str]:
    """
    Generate a concise data-led narrative summary of `report_data`.

    Args:
        report_data: Report dict from ReportGenerator.generate() — {title, sections}.
        org_id: Organization ID (needed to look up org AI config + BYOK key).
        db: Database session.

    Returns:
        Narrative text on success, None when no LLM is configured, the
        resolver returns None, or the completion fails. Never raises.
    """
    if org_id is None or db is None:
        logger.warning("generate_report_narrative called without org_id/db — skipped")
        return None

    provider, model = _configured_model(org_id, db)

    sections = report_data.get("sections") or []
    section_lines = []
    for section in sections:
        if not isinstance(section, dict):
            continue
        heading = section.get("heading") or "Section"
        data = section.get("data") or {}
        numbers = _headline_numbers(data)
        line = heading
        if numbers:
            line += f": {', '.join(numbers)}"
        section_lines.append(f"- {line}")

    if not section_lines:
        return None

    prompt = NARRATIVE_PROMPT.format(sections="\n".join(section_lines))

    request = LLMRequest(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=400,
        json_mode=False,
    )

    try:
        response = call_llm_for_org(
            org_id=org_id,
            task_type="report_narrative",
            request=request,
            provider=provider,
            model=model,
            db=db,
        )
        if response is None or not response.content:
            return None
        return response.content.strip()
    except Exception as e:
        logger.error("Unexpected error generating report narrative: %s", e)
        return None


def _headline_numbers(data: dict) -> list[str]:
    """Extract headline numbers from a section's data for the prompt."""
    numbers: list[str] = []
    data_type = data.get("type")

    if data_type == "table":
        columns = data.get("columns") or []
        rows = data.get("rows") or []
        if columns and rows:
            # First two columns of the first row(s): e.g. "Total Feedback: 3".
            for row in rows[:3]:
                if isinstance(row, (list, tuple)) and len(row) >= 2:
                    numbers.append(f"{row[0]}: {row[1]}")
                elif isinstance(row, dict):
                    vals = [str(v) for v in list(row.values())[:2]]
                    if vals:
                        numbers.append(" / ".join(vals))
    elif data_type == "series":
        rows = data.get("rows") or []
        if rows:
            numbers.append(f"{len(rows)} data points")

    return numbers