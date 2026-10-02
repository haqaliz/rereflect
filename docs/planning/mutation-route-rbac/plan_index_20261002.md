# Execution order
1. backend-gating (Phases 0-3) -> 2. sweep-guard -> 3. frontend-gating (parallelizable with 2) -> 4. docs-tracking.
Tasks 2 and 3 are independent and can be dispatched as parallel agents after 1 is merged on the branch; each agent works strict TDD (RED test first, commit RED, then GREEN).
Shared-file caution: backend-gating owns `tests/conftest.py`; sweep-guard and frontend-gating must not edit it.
