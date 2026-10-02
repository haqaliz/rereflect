"""Per-route guard: every mutation route is role-gated, or deliberately listed.

`test_integration_rbac_sweep.py` works per *module* ("does the source contain a
role marker anywhere"), which cannot see a single ungated POST/PUT/PATCH/DELETE
handler sitting next to gated ones. This guard works per *route* using `ast`.

A mutation route is gated when a role dependency (`require_admin_or_owner`,
`require_owner`, `require_system_admin`) appears in any of:
  - the decorator's `dependencies=[...]`,
  - the handler's argument defaults / annotations (`Depends(...)`),
  - the router-level `APIRouter(dependencies=[...])` it is attached to.

Anything else must be in `EXCLUDED_*` (not user-role-authenticated by design)
or `ALLOWLIST` (member-open by policy, with a reason). Stale entries fail, as
do entries that are in fact gated, so the lists cannot rot.

Limitation: `include_router(..., dependencies=...)` in main.py is invisible to
this AST scan, so `test_main_has_no_include_router_dependencies` forbids it.
"""

import ast
import shutil
from dataclasses import dataclass
from pathlib import Path

import pytest

ROUTES_DIR = Path(__file__).resolve().parents[1] / "src" / "api" / "routes"
MAIN_PY = Path(__file__).resolve().parents[1] / "src" / "api" / "main.py"

ROLE_GATES = ("require_admin_or_owner", "require_owner", "require_system_admin")
MUTATION_VERBS = ("post", "put", "patch", "delete")


# --- Detector ----------------------------------------------------------------

@dataclass(frozen=True)
class Route:
    module: str
    handler: str
    verb: str
    gated: bool


def _mentions_role_gate(node: ast.AST | None) -> bool:
    """True if `node` contains `Depends(<role gate>)` (or a bare gate name)."""
    if node is None:
        return False
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name) and sub.id in ROLE_GATES:
            return True
        if isinstance(sub, ast.Attribute) and sub.attr in ROLE_GATES:
            return True
    return False


def _router_level_gates(tree: ast.Module) -> dict[str, bool]:
    """Router variable name -> whether APIRouter(dependencies=...) has a role gate."""
    routers: dict[str, bool] = {}
    for node in tree.body:
        if not (isinstance(node, ast.Assign) and isinstance(node.value, ast.Call)):
            continue
        func = node.value.func
        name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
        if name != "APIRouter":
            continue
        gated = any(
            kw.arg == "dependencies" and _mentions_role_gate(kw.value)
            for kw in node.value.keywords
        )
        for target in node.targets:
            if isinstance(target, ast.Name):
                routers[target.id] = gated
    return routers


def scan_source(module: str, source: str) -> list[Route]:
    """Return every POST/PUT/PATCH/DELETE route handler declared in `source`."""
    tree = ast.parse(source)
    routers = _router_level_gates(tree)
    routes: list[Route] = []
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in fn.decorator_list:
            if not (isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute)):
                continue
            owner = dec.func.value
            if not (isinstance(owner, ast.Name) and owner.id in routers):
                continue
            if dec.func.attr not in MUTATION_VERBS:
                continue
            args = fn.args
            arg_nodes = [
                *args.defaults,
                *[d for d in args.kw_defaults if d is not None],
                *[a.annotation for a in (*args.posonlyargs, *args.args, *args.kwonlyargs)],
            ]
            gated = (
                routers[owner.id]
                or any(
                    kw.arg == "dependencies" and _mentions_role_gate(kw.value)
                    for kw in dec.keywords
                )
                or any(_mentions_role_gate(n) for n in arg_nodes)
            )
            routes.append(Route(module, fn.name, dec.func.attr, gated))
    return routes


def scan_routes_dir(routes_dir: Path) -> list[Route]:
    routes: list[Route] = []
    for path in sorted(routes_dir.glob("*.py")):
        routes.extend(scan_source(path.stem, path.read_text(encoding="utf-8")))
    return routes


# --- Detector self-tests (synthetic source) ---------------------------------

def _scan(src: str):
    return scan_source("synthetic", src)


def _by_handler(routes):
    return {r.handler: r for r in routes}


def test_detector_flags_ungated_post():
    src = '''
from fastapi import APIRouter, Depends
router = APIRouter()

@router.post("/x")
def make(db=Depends(get_db)):
    ...
'''
    r = _by_handler(_scan(src))["make"]
    assert r.verb == "post" and r.gated is False


def test_detector_ignores_get():
    src = '''
router = APIRouter()

@router.get("/x")
def read():
    ...
'''
    assert _scan(src) == []


def test_detector_gate_in_decorator_dependencies():
    src = '''
router = APIRouter()

@router.delete("/x", dependencies=[Depends(require_admin_or_owner)])
def rm():
    ...
'''
    assert _by_handler(_scan(src))["rm"].gated is True


def test_detector_gate_in_argument_default():
    src = '''
router = APIRouter()

@router.put("/x")
async def upd(_: bool = Depends(require_owner), db=Depends(get_db)):
    ...
'''
    assert _by_handler(_scan(src))["upd"].gated is True


def test_detector_gate_in_kwonly_default():
    src = '''
router = APIRouter()

@router.patch("/x")
def upd(*, _=Depends(require_system_admin)):
    ...
'''
    assert _by_handler(_scan(src))["upd"].gated is True


def test_detector_gate_in_annotated_annotation():
    src = '''
router = APIRouter()

@router.post("/x")
def go(_: Annotated[bool, Depends(require_admin_or_owner)]):
    ...
'''
    assert _by_handler(_scan(src))["go"].gated is True


def test_detector_router_level_gate_applies_to_that_router_only():
    src = '''
admin = APIRouter(prefix="/a", dependencies=[Depends(require_admin_or_owner)])
open_ = APIRouter(prefix="/b")

@admin.post("/x")
def gated_one():
    ...

@open_.post("/y")
def open_one():
    ...
'''
    got = _by_handler(_scan(src))
    assert got["gated_one"].gated is True
    assert got["open_one"].gated is False


def test_detector_non_role_dependency_is_not_a_gate():
    src = '''
router = APIRouter()

@router.post("/x", dependencies=[Depends(get_current_org), Depends(require_feature("a"))])
def go(user=Depends(get_current_user)):
    ...
'''
    assert _by_handler(_scan(src))["go"].gated is False


def test_detector_ignores_non_router_decorators():
    src = '''
@app.post("/x")
def not_a_router():
    ...

@something.post("/y")
def also_not():
    ...
'''
    assert _scan(src) == []


# --- Registries (real tree) ---------------------------------------------------
# Not user-role-authenticated by design. Whole modules first.
EXCLUDED_MODULES = {
    "public_api": "Public API authenticated by org API key (verify_api_key + "
    "scope), not by a user JWT, so there is no member/admin role to gate on",
    "usage_webhooks": "Usage ingest is machine-to-machine: API key with the "
    "'ingest' scope, org taken from the key, no user role involved",
    "source_webhooks": "Inbound provider webhook receivers (Slack, Intercom, "
    "Zendesk, generic) are signature-verified, not JWT-authenticated",
    "jira_webhook": "Inbound Jira webhook receiver, signature-verified, no JWT",
    "asana_webhook": "Inbound Asana webhook receiver, signature-verified, no JWT",
    "linear_webhook": "Inbound Linear webhook receiver, signature-verified, no JWT",
    "email_webhooks": "Inbound email (Resend) webhook receiver, "
    "signature-verified, no JWT",
}

# Single handlers that are pre-auth or token-authenticated.
EXCLUDED_HANDLERS = {
    ("auth", "signup"): "Pre-auth account creation; caller has no JWT yet",
    ("auth", "login"): "Pre-auth credential exchange; caller has no JWT yet",
    ("auth", "google_signup"): "Pre-auth Google OAuth signup; caller has no JWT yet",
    ("auth", "google_login"): "Pre-auth Google OAuth login; caller has no JWT yet",
    ("auth", "saml_callback"): "SAML IdP posts the assertion back; the provider "
    "has no JWT, so a role gate would break the SSO redirect flow",
    ("invites", "accept_invite"): "Invitee has no account/JWT yet; authorised by "
    "the single-use invite token in the URL",
    ("shared_links", "verify_and_get_analytics"): "Public shared-link viewer on "
    "public_router; authorised by link token and optional password, no user",
}

# Authenticated mutation routes that are deliberately open to every member.
ALLOWLIST = {
    ("account", "request_deletion"): "Personal: a user requests deletion of their own account",
    ("account", "cancel_deletion"): "Personal: a user cancels their own pending account deletion",
    ("ai_corrections", "submit_correction"): "Member-open per PRD: any member can submit a correction on AI labels",
    ("ai_settings", "validate_api_key"): "Member-open per PRD: stateless provider key check (ai_settings keys/validate), nothing persisted",
    ("ai_settings", "test_model"): "Member-open per PRD: ai_settings test-model probe, stores no configuration",
    ("analyze", "analyze_feedback"): "Member-open per PRD: single-item POST /analyze/; only the batch route is admin/owner",
    ("anomalies", "resolve_anomaly"): "Member-open per PRD: any member may mark an anomaly resolved",
    ("auth", "update_preferences"): "Personal: user edits their own auth preferences",
    ("churn_events", "delete_churn_event"): "Inline check by design (PRD): author within 24h, system admin, or org admin/owner; no blanket dependency gate",
    ("conversation_folders", "create_folder"): "Personal: copilot conversation folders belong to the calling user",
    ("conversation_folders", "update_folder"): "Personal: copilot conversation folders belong to the calling user",
    ("conversation_folders", "delete_folder"): "Personal: copilot conversation folders belong to the calling user",
    ("conversations", "create_conversation"): "Personal: copilot conversations belong to the calling user",
    ("conversations", "update_conversation"): "Personal: copilot conversations belong to the calling user",
    ("conversations", "delete_conversation"): "Personal: copilot conversations belong to the calling user",
    ("copilot_actions", "execute_copilot_action"): "Member-open per PRD: each action enforces its own min_role at execution time",
    ("customers", "analyze_customer"): "Member-open per PRD: on-demand customer analysis is a member workflow",
    ("customers", "update_action_item"): "Member-open per PRD: members work customer action items",
    ("dashboard_layout", "save_layout"): "Personal: the user's own dashboard layout",
    ("dashboard_layout", "reset_layout"): "Personal: the user's own dashboard layout",
    ("feedback", "create_feedback"): "Member-open per PRD: members create feedback items",
    ("feedback", "update_feedback"): "Member-open per PRD: members edit feedback items; only delete is admin/owner",
    ("feedback", "set_feedback_urgent"): "Member-open per PRD: members flag feedback as urgent",
    ("feedback", "import_csv"): "Member-open per PRD: CLAUDE.md RBAC matrix allows members to import CSV",
    ("feedback_responses", "generate_ai_response"): "Member-open per PRD: members draft AI responses to feedback",
    ("feedback_responses", "send_response"): "Member-open per PRD: members send feedback responses",
    ("notifications", "mark_read"): "Personal: the user's own notification state",
    ("notifications", "mark_all_read"): "Personal: the user's own notification state",
    ("notifications", "dismiss"): "Personal: the user's own notification state",
    ("notifications", "restore"): "Personal: the user's own notification state",
    ("notifications", "update_preferences"): "Personal: the user's own notification preferences",
    ("notifications", "update_retention"): "Personal: notification retention setting for the user's own inbox",
    ("organizations", "update_my_organization"): "Deliberately not dependency-gated: inline role != 'admin' check rejects "
    "owners, a known bug tracked as PRD O4 (out of scope, separate fix)",
    ("pending_feedback", "approve_pending_feedback"): "Member-open per PRD: members triage the pending-feedback queue",
    ("pending_feedback", "reject_pending_feedback"): "Member-open per PRD: members triage the pending-feedback queue",
    ("pending_feedback", "bulk_approve_pending_feedback"): "Member-open per PRD: members triage the pending-feedback queue",
    ("pending_feedback", "bulk_reject_pending_feedback"): "Member-open per PRD: members triage the pending-feedback queue",
    ("response_templates", "suggest_template"): "Member-open per PRD: response_templates /suggest only reads and ranks templates",
    ("saved_views", "create_saved_view"): "Personal: saved views belong to the calling user",
    ("saved_views", "update_saved_view"): "Personal: saved views belong to the calling user",
    ("saved_views", "delete_saved_view"): "Personal: saved views belong to the calling user",
    ("saved_views", "reorder_saved_views"): "Personal: saved views belong to the calling user",
    ("shared_links", "create_shared_link"): "Member-open per PRD: members share their analytics views via link",
    ("shared_links", "deactivate_shared_link"): "Member-open per PRD: members manage shared links",
    ("workflow", "change_status"): "Member-open per PRD: workflow status changes are a member action",
    ("workflow", "assign_feedback"): "Member-open per PRD: manual assignment is a member action",
    ("workflow", "create_note"): "Member-open per PRD: members add feedback notes",
    ("workflow", "update_note"): "Member-open per PRD: members edit feedback notes",
    ("workflow", "delete_note"): "Member-open per PRD: members delete feedback notes",
}

_GENERIC_REASONS = {"member-open", "member open", "todo", "tbd", "n/a", "excluded", "allowlisted"}


def check_tree(
    routes_dir: Path,
    allowlist: dict = ALLOWLIST,
    excluded_modules: dict = EXCLUDED_MODULES,
    excluded_handlers: dict = EXCLUDED_HANDLERS,
) -> list[str]:
    """Return a list of human-readable problems; empty means the tree is clean."""
    routes = scan_routes_dir(routes_dir)
    by_key = {(r.module, r.handler): r for r in routes}
    modules_with_routes = {r.module for r in routes}
    problems: list[str] = []

    for r in routes:
        key = (r.module, r.handler)
        listed = (
            r.module in excluded_modules or key in excluded_handlers or key in allowlist
        )
        if not r.gated and not listed:
            problems.append(
                f"UNGATED: {r.module}.{r.handler} ({r.verb.upper()}) has no role gate "
                "and is not in ALLOWLIST/EXCLUDED"
            )
        if r.gated and listed:
            problems.append(
                f"STALE-GATED: {r.module}.{r.handler} is listed but already role-gated; "
                "remove the entry"
            )

    for module in excluded_modules:
        if module not in modules_with_routes:
            problems.append(f"STALE: excluded module {module} has no mutation routes")
    for registry_name, registry in (("EXCLUDED_HANDLERS", excluded_handlers), ("ALLOWLIST", allowlist)):
        for key in registry:
            if key not in by_key:
                problems.append(f"STALE: {registry_name} entry {key} matches no mutation route")
    return problems


# --- Real-tree tests ------------------------------------------------------------

def test_every_mutation_route_is_gated_or_listed():
    assert check_tree(ROUTES_DIR) == []


def test_registries_do_not_overlap():
    overlap = set(ALLOWLIST) & set(EXCLUDED_HANDLERS)
    assert not overlap
    assert not {m for m, _ in ALLOWLIST} & set(EXCLUDED_MODULES)


@pytest.mark.parametrize(
    "name,registry",
    [
        ("ALLOWLIST", ALLOWLIST),
        ("EXCLUDED_HANDLERS", EXCLUDED_HANDLERS),
        ("EXCLUDED_MODULES", EXCLUDED_MODULES),
    ],
)
def test_every_entry_has_a_specific_reason(name, registry):
    for key, reason in registry.items():
        assert len(reason.strip()) >= 15, f"{name}{key}: reason too short"
        assert reason.strip().lower() not in _GENERIC_REASONS, f"{name}{key}: generic reason"
        assert " " in reason.strip(), f"{name}{key}: reason must be a sentence"


def test_update_my_organization_allowlisted_with_o4_reason():
    reason = ALLOWLIST[("organizations", "update_my_organization")]
    assert "O4" in reason


def test_gated_playbooks_are_actually_detected_as_gated():
    # Guards against the detector silently returning "ungated" for everything
    # (which the allowlist would then mask) or "gated" for everything.
    playbooks = [r for r in scan_routes_dir(ROUTES_DIR) if r.module == "playbooks"]
    assert playbooks and all(r.gated for r in playbooks)
    ungated = [r for r in scan_routes_dir(ROUTES_DIR) if not r.gated]
    assert ungated, "expected some member-open routes to be detected"


def test_main_has_no_include_router_dependencies():
    # The AST scan cannot see gates attached at include time.
    tree = ast.parse(MAIN_PY.read_text(encoding="utf-8"))
    offenders = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "include_router"
        and any(kw.arg == "dependencies" for kw in node.keywords)
    ]
    assert offenders == [], f"include_router(dependencies=...) at main.py lines {offenders}"


# --- Sensitivity: the guard must actually fail --------------------------------------

@pytest.fixture
def routes_copy(tmp_path):
    dest = tmp_path / "routes"
    shutil.copytree(ROUTES_DIR, dest, ignore=shutil.ignore_patterns("__pycache__"))
    return dest


def test_copy_of_real_tree_is_clean(routes_copy):
    assert check_tree(routes_copy) == []


def test_guard_fails_when_gate_removed_from_gated_route(routes_copy):
    path = routes_copy / "playbooks.py"
    src = path.read_text(encoding="utf-8")
    for gate in ROLE_GATES:
        src = src.replace(gate, "get_current_org")
    path.write_text(src, encoding="utf-8")
    problems = check_tree(routes_copy)
    assert any(p.startswith("UNGATED: playbooks.") for p in problems), problems


def test_guard_fails_when_unlisted_ungated_route_added(routes_copy):
    path = routes_copy / "playbooks.py"
    path.write_text(
        path.read_text(encoding="utf-8")
        + '\n\n@router.post("/__sneaky")\ndef sneaky(db=Depends(get_db)):\n    return {}\n',
        encoding="utf-8",
    )
    problems = check_tree(routes_copy)
    assert any("UNGATED: playbooks.sneaky" in p for p in problems), problems


def test_guard_fails_on_stale_allowlist_entry():
    stale = {**ALLOWLIST, ("notifications", "no_such_handler"): "Personal: handler that was deleted long ago"}
    assert any("STALE" in p and "no_such_handler" in p for p in check_tree(ROUTES_DIR, allowlist=stale))


def test_guard_fails_on_allowlist_entry_that_is_actually_gated():
    wrong = {**ALLOWLIST, ("playbooks", "create_playbook"): "Mistakenly listed although this route is gated"}
    problems = check_tree(ROUTES_DIR, allowlist=wrong)
    assert any(p.startswith("STALE-GATED: playbooks.create_playbook") for p in problems), problems
