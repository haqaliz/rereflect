"""
Name-consistency pin for the intercom write-back dispatch (dispatch-seams).

The five dispatch sites (3 backend routes via send_task, 2 worker writers via
.delay) all fire the task registered under

    "src.tasks.intercom_writeback.push_resolved_writeback"

If the registered name drifts from that string, every dispatch raises
NotRegistered in production while the UI keeps showing the feature enabled —
the exact "silently never fires" class this feature exists to guard (the
sibling worker-writeback-task aspect pins the registry + include from the
task side; this file pins the same contract from the dispatcher side).

Pattern: test_beat_schedule_integrity.py — import the module first (Celery's
include list is lazy; a task only appears in celery_app.tasks once its module
has been imported), then assert registry + name + include.
"""
import importlib

from src.celery_app import celery_app

DISPATCH_STRING = "src.tasks.intercom_writeback.push_resolved_writeback"


class TestIntercomWritebackDispatchName:
    def test_task_registered_with_exact_dispatch_name(self):
        importlib.import_module("src.tasks.intercom_writeback")

        assert DISPATCH_STRING in celery_app.tasks
        # Catches the churn_playbooks failure class: a name= that lacks the
        # src. prefix registers under a different string than dispatchers use.
        assert celery_app.tasks[DISPATCH_STRING].name == DISPATCH_STRING

    def test_task_module_in_celery_include(self):
        # A task module missing from `include` is never imported by the
        # worker, so send_task/delay raise NotRegistered in production.
        assert "src.tasks.intercom_writeback" in (celery_app.conf.include or ())
