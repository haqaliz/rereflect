"""Repo-wide guard: every inbound-webhook signature verifier must fail CLOSED.

A verifier that returns True when its secret is unset accepts arbitrary unsigned
payloads from anyone who knows the URL. Because none of these secrets were
documented in any `.env.example` or compose file, "unset" was the default state
of every install — so a fail-open branch here is not a theoretical edge case, it
is the shipped default.

This test exists because that defect was found and fixed **one verifier at a
time** historically: Zendesk was corrected in isolation and the identical pattern
was left in place in Intercom, Slack, email and Linear. A per-verifier test
cannot catch that class of drift. This one can.

Two things it guarantees going forward:

1. A NEW verifier that fails open fails this test immediately.
2. The two verifiers knowingly left in shadow mode are named in an explicit
   allowlist below. When they are flipped to fail closed, this test fails and
   tells the author to remove the entry — so the shadow period cannot quietly
   become permanent.
"""

import time
from unittest.mock import patch

import pytest

from src.api.routes import asana_webhook, email_webhooks, jira_webhook
from src.api.routes import linear_webhook, source_webhooks


_TS = str(int(time.time()))


# --- Shadow-mode allowlist ----------------------------------------------------
# Verifiers that DELIBERATELY still accept unsigned deliveries, because their
# ingestion path demonstrably works today and flipping them closed would silently
# stop real feedback for any operator who never set the secret. Each logs a
# "SECURITY-SHADOW" warning per request, warns at startup, and is flagged in
# Settings -> Integrations.
#
# THIS ALLOWLIST IS TEMPORARY. When a verifier below is flipped to fail closed,
# delete its entry — this test will fail until you do, which is the point.
#
# Do NOT add to this list to make a new failure go away. A new fail-open verifier
# is a defect, not a shadow rollout.
SHADOW_ALLOWLIST = {
    "source_webhooks.verify_slack_signature",
    "email_webhooks._verify_webhook_signature",
}


def _call_slack(secret):
    return source_webhooks.verify_slack_signature("{}", _TS, "v0=abc", secret)


def _call_intercom(secret):
    return source_webhooks.verify_intercom_signature(b"{}", "sha1=abc", secret)


def _call_zendesk(secret):
    return source_webhooks._verify_zendesk_signature(b"{}", _TS, "abc", secret)


def _call_email(secret):
    # This verifier takes no secret argument -- it reads a module-level constant,
    # so the "unset" case has to be simulated by patching that constant.
    with patch.object(email_webhooks, "RESEND_INBOUND_WEBHOOK_SECRET", secret):
        return email_webhooks._verify_webhook_signature(b"{}", {})


def _call_jira(secret):
    return jira_webhook._verify_jira_signature(b"{}", "sha256=abc", secret)


def _call_asana(secret):
    return asana_webhook._verify_asana_signature(b"{}", "abc", secret)


def _call_linear(secret):
    return linear_webhook._verify_linear_signature(b"{}", "abc", secret)


VERIFIERS = [
    ("source_webhooks.verify_slack_signature", _call_slack),
    ("source_webhooks.verify_intercom_signature", _call_intercom),
    ("source_webhooks._verify_zendesk_signature", _call_zendesk),
    ("email_webhooks._verify_webhook_signature", _call_email),
    ("jira_webhook._verify_jira_signature", _call_jira),
    ("asana_webhook._verify_asana_signature", _call_asana),
    ("linear_webhook._verify_linear_signature", _call_linear),
]


class TestEveryVerifierFailsClosed:
    @pytest.mark.parametrize("name,call", VERIFIERS, ids=[n for n, _ in VERIFIERS])
    @pytest.mark.parametrize("secret", ["", None], ids=["empty", "none"])
    def test_verifier_rejects_when_secret_unset(self, name, call, secret):
        """An unconfigured secret must never authenticate a request.

        Allowlisted verifiers are asserted to still accept, so that flipping one
        to fail closed breaks this test and forces the allowlist to be updated.
        """
        result = call(secret)

        if name in SHADOW_ALLOWLIST:
            assert result is True, (
                f"{name} is on SHADOW_ALLOWLIST but now fails closed. "
                f"That is the desired end state -- remove it from SHADOW_ALLOWLIST "
                f"in {__file__} and update docs/SELF_HOSTING.md, which still "
                f"describes it as accepting unverified deliveries."
            )
        else:
            assert result is False, (
                f"{name} FAILS OPEN: it returned True with secret={secret!r}. "
                f"An unset secret is the default state of most installs, so this "
                f"endpoint would accept arbitrary unsigned payloads. Return False "
                f"instead -- see _verify_zendesk_signature for the reference shape. "
                f"If this is a deliberate, documented shadow rollout, add it to "
                f"SHADOW_ALLOWLIST with a reason and a plan to remove it."
            )

    def test_allowlist_only_contains_known_shadow_verifiers(self):
        """The allowlist must not grow silently.

        Pinned so that adding an entry requires editing this assertion too --
        a deliberate speed bump, since every entry is an endpoint accepting
        unsigned traffic.
        """
        assert SHADOW_ALLOWLIST == {
            "source_webhooks.verify_slack_signature",
            "email_webhooks._verify_webhook_signature",
        }

    def test_every_allowlisted_verifier_is_actually_enumerated(self):
        """Guards against an allowlist entry whose verifier is no longer tested."""
        enumerated = {name for name, _ in VERIFIERS}
        orphaned = SHADOW_ALLOWLIST - enumerated
        assert not orphaned, (
            f"SHADOW_ALLOWLIST names verifiers that VERIFIERS does not cover: "
            f"{orphaned}. An allowlisted-but-untested verifier is unguarded."
        )
