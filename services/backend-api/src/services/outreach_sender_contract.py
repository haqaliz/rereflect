"""
Outreach send-path contract constants (outreach-core aspect).

The worker's `outreach_sender` and (future) backend send paths must agree on
the shared Redis cooldown key scheme — `outreach_cooldown:{org_id}:{email}` —
or a cooldown set by one path is ignored by the other. This module is the
backend's anchor for that agreement; tests in BOTH suites pin the literal,
so drift fails on whichever side moved.
"""

OUTREACH_COOLDOWN_PREFIX = "outreach_cooldown"
