"""Repo-wide guard: every integration/config route module must be role-gated.

The class of defect this guards against: a route module that deals with
integrations, SSO config or API credentials regressing into the "zero role
dependencies" class — i.e. every endpoint is reachable by any authenticated
member, or worse, by nobody authenticated at all.

That defect was found and fixed one module at a time (integrations.py,
linear_integration.py, feedback_sources.py), and the same hole had to be
audited across zendesk/jira/asana/intercom/hubspot/salesforce integrations,
OIDC/SAML config, API keys, custom webhooks, automations, response templates
and AI settings. A per-route test cannot catch that class of drift. This one
can:

1. Every module listed as "gated" must contain `require_admin_or_owner` or
   `require_owner` in its source.
2. Every module listed as "exempt" must NOT contain either marker — the
   exemption is deliberate (JWT-less by design), so if an exempt module ever
   grows role-gated endpoints, this test fails and forces the author to
   reclassify it.
3. A directory sweep: any NEW module that looks like an integration/config
   module but is missing from the registry fails immediately.
4. The JWT-less OAuth callbacks that live inside otherwise-gated modules are
   pinned explicitly so they cannot silently acquire a role gate that would
   break the provider's redirect flow.

Deliberate exemptions (all JWT-less by design, documented per entry):
  - Inbound webhook receivers are signature-verified, not JWT-authenticated
    (see test_webhook_verifiers_fail_closed.py for the fail-closed contract).
  - The webhooks module's GET list/get/deliveries are member-open by design;
    its writes are gated.
  - OAuth callbacks inside gated modules are called by the provider, which
    has no JWT to present.
"""

from pathlib import Path

import pytest

ROUTES_DIR = Path(__file__).resolve().parents[1] / "src" / "api" / "routes"

ROLE_DEP_MARKERS = ("require_admin_or_owner", "require_owner")

# --- Registry ---------------------------------------------------------------
# module (without .py) -> "gated" | "exempt:<reason>".
# "gated" modules must contain a role marker; "exempt" modules must not.
# The value string is assert-free documentation: edit it as the truth changes,
# but changing a module's status between "gated" and "exempt" is exactly the
# kind of change this test is here to force you to make deliberately.
ROUTE_MODULES = {
    # ---- Gated: must contain require_admin_or_owner / require_owner --------
    "integrations": "gated",
    "linear_integration": "gated",
    "feedback_sources": "gated",
    "zendesk_integration": "gated",
    "jira_integration": "gated",
    "asana_integration": "gated",
    "intercom_integration": "gated",
    "hubspot_integration": "gated",
    "salesforce_integration": "gated",
    "oidc_config": "gated",
    "saml_config": "gated",
    "api_keys": "gated",
    "webhooks": "gated: write/update/delete/test/rotate gated with "
    "require_admin_or_owner; GET list/get/deliveries member-open via "
    "get_current_org by design",
    "automations": "gated",
    "response_templates": "gated",
    "ai_settings": "gated",
    # ---- Exempt: JWT-less by design ----------------------------------------
    "source_webhooks": "exempt: inbound provider webhook receiver — "
    "signature-verified, no JWT (see test_webhook_verifiers_fail_closed.py)",
    "jira_webhook": "exempt: inbound Jira webhook receiver — "
    "signature-verified, no JWT",
    "asana_webhook": "exempt: inbound Asana webhook receiver — "
    "signature-verified, no JWT",
    "linear_webhook": "exempt: inbound Linear webhook receiver — "
    "signature-verified, no JWT",
    "email_webhooks": "exempt: inbound email (Resend) webhook receiver — "
    "signature-verified, no JWT",
    "usage_webhooks": "exempt: product-usage ingest receiver — API-key "
    "scoped, no JWT",
    "notifications": "exempt: user-scoped per-user preferences, no "
    "org-level admin surface",
}

GATED_MODULES = [name for name, status in ROUTE_MODULES.items() if status.startswith("gated")]
EXEMPT_MODULES = [name for name, status in ROUTE_MODULES.items() if status.startswith("exempt")]

# --- JWT-less OAuth callbacks inside otherwise-gated modules ------------------
# (module, path) pairs. The provider calls these back after the user's OAuth
# consent, so no JWT is (or can be) presented. Pinned here so they cannot
# silently acquire a role dependency that would break the redirect flow.
OAUTH_CALLBACKS = [
    ("integrations", "/slack/oauth/callback"),
    ("integrations", "/intercom/oauth/callback"),
    ("linear_integration", "/callback"),
    ("salesforce_integration", "/callback"),
]


def _module_source(module: str) -> str:
    return (ROUTES_DIR / f"{module}.py").read_text(encoding="utf-8")


def _route_slice(source: str, decorator_fragment: str) -> str:
    """Decorator line containing `fragment` up to the next @router.* decorator."""
    lines = source.splitlines()
    start = next(i for i, line in enumerate(lines) if decorator_fragment in line)
    end = next(
        (i for i in range(start + 1, len(lines)) if lines[i].lstrip().startswith("@router.")),
        len(lines),
    )
    return "\n".join(lines[start:end])


def _in_sweep_scope(module_name: str) -> bool:
    """A module that looks like an integration/config surface must be registered."""
    if module_name.startswith("_"):
        return False
    if any(k in module_name for k in ("integration", "webhook", "config")):
        return True
    return module_name in {
        "api_keys",
        "automations",
        "response_templates",
        "ai_settings",
        "feedback_sources",
        "notifications",
    }


class TestIntegrationRouteRbacSweep:
    @pytest.mark.parametrize("module", GATED_MODULES, ids=GATED_MODULES)
    def test_gated_module_contains_role_dependency(self, module):
        """A gated module must reference require_admin_or_owner or require_owner.

        This is the core guard: if every role dependency is removed from a
        gated module (or the dependency is never wired into a route), the
        module falls back into the 'zero role dependencies' class and this
        fails.
        """
        source = _module_source(module)
        assert any(marker in source for marker in ROLE_DEP_MARKERS), (
            f"{module}.py is registered as GATED but contains none of "
            f"{ROLE_DEP_MARKERS}. Every integration/config surface must be "
            f"admin/owner-gated. If this module is deliberately member-open "
            f"or JWT-less, move it to the EXEMPT section of ROUTE_MODULES "
            f"with a reason."
        )

    @pytest.mark.parametrize("module", EXEMPT_MODULES, ids=EXEMPT_MODULES)
    def test_exempt_module_has_no_role_dependency(self, module):
        """Exemptions are deliberate and must stay JWT-less.

        An exempt module that gains a role dependency is no longer purely
        JWT-less: reclassify it as gated (and keep its JWT-less endpoints
        as documented exceptions) rather than leaving it exempt.
        """
        source = _module_source(module)
        assert not any(marker in source for marker in ROLE_DEP_MARKERS), (
            f"{module}.py is registered as EXEMPT ({ROUTE_MODULES[module]}) "
            f"but now references {ROLE_DEP_MARKERS}. An exempt module is "
            f"JWT-less by design; if it gained role-gated endpoints, move it "
            f"to the GATED section of ROUTE_MODULES instead of keeping it "
            f"exempt."
        )

    @pytest.mark.parametrize(
        "module,path", OAUTH_CALLBACKS, ids=[f"{m}:{p}" for m, p in OAUTH_CALLBACKS]
    )
    def test_oauth_callback_route_is_jwtless(self, module, path):
        """The provider-initiated OAuth callbacks must not be role-gated."""
        source = _module_source(module)
        body = _route_slice(source, f'@router.get("{path}")')
        assert body, (
            f"could not find a @router.get({path!r}) route in {module}.py — "
            f"did the callback path change? Update OAUTH_CALLBACKS."
        )
        assert not any(marker in body for marker in ROLE_DEP_MARKERS), (
            f"OAuth callback {module}.py:{path} is JWT-less by design (the "
            f"provider redirects here with no JWT to present) but now "
            f"references {ROLE_DEP_MARKERS}. Remove the role dependency; "
            f"the callback must not be admin-gated."
        )

    def test_sweep_covers_every_integration_or_config_module(self):
        """A NEW integration/config module must be registered before this passes.

        Scans the routes directory for any module that looks like an
        integration/config surface and fails if it is missing from
        ROUTE_MODULES — so a new webhook/integration/config module cannot
        ship with zero role dependencies without being consciously added to
        the registry first.
        """
        registered = set(ROUTE_MODULES)
        discovered = {
            path.stem for path in ROUTES_DIR.glob("*.py") if _in_sweep_scope(path.stem)
        }
        unregistered = discovered - registered
        assert not unregistered, (
            f"Unregistered integration/config route modules: "
            f"{sorted(unregistered)}. Add each to ROUTE_MODULES as "
            f"\"gated\" (with require_admin_or_owner/require_owner) or "
            f"\"exempt:<reason>\" in {__file__}."
        )

    def test_registry_statuses_are_valid(self):
        """Status values must be 'gated' or 'gated: <exception>' or 'exempt:<reason>'."""
        invalid = {
            name: status
            for name, status in ROUTE_MODULES.items()
            if not (
                status == "gated"
                or status.startswith("gated: ")
                or status.startswith("exempt: ")
            )
        }
        assert not invalid, (
            f"ROUTE_MODULES entries with invalid status: {invalid}. Use "
            f"\"gated\", \"gated: <exception>\" or \"exempt:<reason>\"."
        )
