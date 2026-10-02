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
from pathlib import Path

import pytest

ROUTES_DIR = Path(__file__).resolve().parents[1] / "src" / "api" / "routes"
MAIN_PY = Path(__file__).resolve().parents[1] / "src" / "api" / "main.py"

ROLE_GATES = ("require_admin_or_owner", "require_owner", "require_system_admin")
MUTATION_VERBS = ("post", "put", "patch", "delete")


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
