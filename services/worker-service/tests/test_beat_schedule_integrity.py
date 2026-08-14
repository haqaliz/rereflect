"""Every scheduled task must actually exist.

This repo has shipped the same failure more than once: code that is
registered, scheduled and visibly "on", but which does nothing. The
automations engine import swallowed by a bare `except`; the Intercom
write-back module with no caller; and -- until this test --
`sync_all_integrations`, a daily beat entry whose only job was to call two
connectors that both returned [].

The pattern is always the same shape: something is wired at one end and dead
at the other, and no test spans the join. This one does, for the beat schedule:
a scheduled task that cannot resolve is a job the operator believes is running
and which is not.

NOTE ON HOW THIS IS CHECKED. It reads `celery_app.tasks` only AFTER importing the
entry's own module (below). Celery's `include` list is lazy -- a task only appears
in that registry once its module has been imported, so in a pytest process the
registry reflects whichever test modules happened to import what, in whatever
order. (conftest.py names the same hazard "import-order roulette" for a related
reason.) A first draft of this test used that registry without the explicit
import and reported a dozen false positives, including tasks that demonstrably
run in production. Importing the module first makes the registry lookup
order-independent, and the registry check itself means what it says: a beat
entry must resolve to a task that is actually registered, not merely to a module
attribute -- an undecorated function imports cleanly yet raises `NotRegistered`
at dispatch time, exactly the operator-believes-it-runs failure above.

See docs/planning/intercom-selfhost-ingestion/cleanup-and-docs/.
"""
import importlib

import pytest

from src.celery_app import celery_app


def _beat_entries():
    return sorted(
        (name, entry["task"])
        for name, entry in celery_app.conf.beat_schedule.items()
    )


@pytest.mark.parametrize("name,task_path", _beat_entries())
def test_beat_entry_resolves_to_a_real_task(name, task_path):
    module_path, _, attr = task_path.rpartition(".")

    try:
        module = importlib.import_module(module_path)
    except ImportError as exc:  # pragma: no cover - only on a real regression
        pytest.fail(
            f"Beat entry '{name}' schedules '{task_path}', but its module "
            f"{module_path!r} cannot be imported: {exc}\n"
            "Either the module was deleted and this entry is stale, or the "
            "import is broken -- both mean the schedule is lying about what runs."
        )

    assert hasattr(module, attr), (
        f"Beat entry '{name}' schedules '{task_path}', but {module_path!r} "
        f"defines no {attr!r}. A scheduled task that cannot resolve is a job "
        "the operator believes is running and which is not."
    )

    assert task_path in celery_app.tasks, (
        f"Beat entry '{name}' schedules '{task_path}', but it is not a "
        "registered Celery task. An undecorated function imports fine yet "
        "never lands in the task registry, so Celery raises NotRegistered at "
        "dispatch time -- a job the operator believes is running and which is not."
    )


def test_beat_entry_modules_are_in_the_include_list():
    """A task module missing from `include` is never imported by the worker, so
    its beat entry silently never fires."""
    included = set(celery_app.conf.include or ())
    missing = {
        name: task.rpartition(".")[0]
        for name, task in _beat_entries()
        if task.rpartition(".")[0] not in included
    }
    assert not missing, (
        "Beat entries whose module is absent from celery_app's include list:\n"
        + "\n".join(f"  {n} -> {m}" for n, m in sorted(missing.items()))
    )


def test_the_dead_connector_beat_entry_is_gone():
    """Pins the specific removal so a merge cannot restore it.

    sync_all_integrations dispatched IntercomConnector/ZendeskConnector, both
    `return []` stubs carrying "TODO: implement in Month 2". The real pull
    paths are intercom_sync.py and zendesk_sync.py.
    """
    scheduled = {entry["task"] for entry in celery_app.conf.beat_schedule.values()}
    assert "src.tasks.integrations.sync_all_integrations" not in scheduled
