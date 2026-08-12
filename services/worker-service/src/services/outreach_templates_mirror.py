# DUPLICATED: keep in sync with the backend-api copy
# (services/backend-api/src/services/outreach_templates.py)
"""
Built-in outreach template registry — WORKER MIRROR.

The worker cannot import backend-api packages, so this module duplicates the
backend registry data verbatim (same `usage_trend_severity.py` precedent).
The backend copy is the single source of truth; the two must stay in
agreement or a seeded send_email step will render a different message than
the operator sees in the registry endpoint.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class OutreachTemplate:
    key: str
    label: str
    description: str
    subject: str
    body: str


OUTREACH_TEMPLATES: dict = {
    "re_engagement": OutreachTemplate(
        key="re_engagement",
        label="Re-engagement check-in",
        description=(
            "A friendly nudge for customers who have gone quiet — invites "
            "them to tell you what happened, no hard sell."
        ),
        subject="We'd love to hear from you",
        body=(
            "Hi {{CUSTOMER_NAME}},\n"
            "\n"
            "We noticed it's been a little while since you last used "
            "{{PRODUCT_NAME}}. We'd love to know how things are going — "
            "whether something got in the way, you found a better fit "
            "elsewhere, or life just got busy.\n"
            "\n"
            "If anything tripped you up, hit reply and a real person will "
            "get back to you. And if {{PRODUCT_NAME}} isn't the right fit "
            "anymore, no hard feelings — you can unsubscribe at the bottom "
            "of this email.\n"
            "\n"
            "Best,\n"
            "The {{PRODUCT_NAME}} team"
        ),
    ),
    "weekly_digest_entry": OutreachTemplate(
        key="weekly_digest_entry",
        label="Weekly digest entry",
        description=(
            "A short weekly check-in that keeps the relationship warm — "
            "highlights, fixes, and what's coming next."
        ),
        subject="Your weekly {{PRODUCT_NAME}} digest",
        body=(
            "Hi {{CUSTOMER_NAME}},\n"
            "\n"
            "Here's what happened in {{PRODUCT_NAME}} this week: the "
            "highlights, the fixes, and what's coming next.\n"
            "\n"
            "If you have questions or feedback, just hit reply — we read "
            "everything.\n"
            "\n"
            "Best,\n"
            "The {{PRODUCT_NAME}} team"
        ),
    ),
}


def render_outreach_template(key: str, customer_name: str, product_name: str) -> str:
    """Render a registry template's body with customer/product substitution.

    Raises KeyError for an unknown template key. Unknown ``{{PLACEHOLDER}}``
    tokens in a body are left untouched.
    """
    tpl = OUTREACH_TEMPLATES[key]
    return (
        tpl.body
        .replace("{{CUSTOMER_NAME}}", customer_name)
        .replace("{{PRODUCT_NAME}}", product_name)
    )
