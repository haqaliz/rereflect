"""
TDD guard: asserts that ALL Stripe billing machinery has been removed from
worker-service/src/.

RED phase: these tests FAIL against the current code (billing.py exists, beat
entries are present, stripe import exists).
GREEN phase: after deleting src/tasks/billing.py and cleaning up celery_app.py
and any stripe imports, all three assertions become True.
"""

import importlib
import sys
import types
import os
import glob


# ---------------------------------------------------------------------------
# 1. src.tasks.billing must NOT exist (module deleted)
# ---------------------------------------------------------------------------

def test_billing_module_does_not_exist():
    """Importing src.tasks.billing must raise ModuleNotFoundError.

    Before deletion this test FAILS because the file exists and is importable.
    After deletion it PASSES.
    """
    # Remove from sys.modules cache so we get a fresh import attempt.
    sys.modules.pop("src.tasks.billing", None)

    try:
        importlib.import_module("src.tasks.billing")
        raise AssertionError(
            "src.tasks.billing was importable — the module file must be deleted"
        )
    except ModuleNotFoundError:
        pass  # expected post-deletion


# ---------------------------------------------------------------------------
# 2. beat_schedule must contain NO billing.* task entries
# ---------------------------------------------------------------------------

_BILLING_TASK_PREFIXES = (
    "billing.",
)

_EXPECTED_ABSENT_BEAT_KEYS = {
    "check-trial-expirations",
    "send-trial-ending-reminders",
    "report-overages-to-stripe",
    "check-usage-warnings",
}


def test_beat_schedule_has_no_billing_entries():
    """celery_app.conf.beat_schedule must contain no tasks whose name starts
    with 'billing.'.

    Before removal this FAILS because all four billing beat entries are present.
    After cleanup it PASSES.
    """
    # Ensure a fresh import so we see the real current state.
    sys.modules.pop("src.celery_app", None)

    import src.celery_app as ca

    beat = ca.celery_app.conf.beat_schedule

    billing_entries = {
        key: entry
        for key, entry in beat.items()
        if any(entry.get("task", "").startswith(prefix) for prefix in _BILLING_TASK_PREFIXES)
    }

    assert not billing_entries, (
        f"beat_schedule still contains billing.* tasks: {list(billing_entries.keys())}. "
        "Remove the billing beat entries from src/celery_app.py."
    )


def test_beat_schedule_absent_beat_keys():
    """The specific beat schedule *keys* for billing must not appear."""
    sys.modules.pop("src.celery_app", None)

    import src.celery_app as ca

    beat = ca.celery_app.conf.beat_schedule
    found = _EXPECTED_ABSENT_BEAT_KEYS & set(beat.keys())

    assert not found, (
        f"These billing beat keys are still present: {found}. "
        "Remove them from src/celery_app.py."
    )


# ---------------------------------------------------------------------------
# 3. No 'stripe' import anywhere in services/worker-service/src/
# ---------------------------------------------------------------------------

def _find_stripe_imports_in_src() -> list[str]:
    """Return a list of 'file:line' strings where 'stripe' is imported."""
    worker_src = os.path.join(
        os.path.dirname(__file__),  # tests/
        "..",
        "src",
    )
    worker_src = os.path.normpath(worker_src)

    hits = []
    for py_file in glob.glob(os.path.join(worker_src, "**", "*.py"), recursive=True):
        with open(py_file, encoding="utf-8") as fh:
            for lineno, line in enumerate(fh, start=1):
                stripped = line.strip()
                # Match: import stripe  /  from stripe import ...  / import stripe.
                if stripped.startswith("import stripe") or stripped.startswith("from stripe"):
                    hits.append(f"{os.path.relpath(py_file, worker_src)}:{lineno}: {stripped}")
    return hits


def test_no_stripe_import_in_worker_src():
    """No file under worker-service/src/ may import the stripe library.

    Before deletion of billing.py this FAILS because billing.py imports stripe.
    After deletion it PASSES.
    """
    hits = _find_stripe_imports_in_src()
    assert not hits, (
        "Found stripe imports in worker-service/src/:\n"
        + "\n".join(f"  {h}" for h in hits)
    )
