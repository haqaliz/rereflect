"""
Drift-pin for the worker UserAlertPreference mirror.

worker-service cannot import backend-api, so its model layer is a deliberate,
hand-maintained duplicate of the backend models. The mirror has drifted before
(channel_intercom was missing until Aug 2026; channel_discord landed with
discord-channel-preferences). Every channel column is pinned here so a future
missing column fails loudly instead of silently gating dispatches to the
wrong default.
"""


def test_user_alert_preference_mirror_has_channel_teams_column(db, test_user):
    """Drift pin: the mirror must carry channel_teams and default it to True."""
    from src.models import UserAlertPreference

    pref = UserAlertPreference(
        user_id=test_user.id,
        alert_type="urgent_feedback",
    )
    db.add(pref)
    db.commit()
    db.refresh(pref)

    assert pref.channel_teams is True