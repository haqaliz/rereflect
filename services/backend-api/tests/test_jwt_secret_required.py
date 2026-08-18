"""JWT_SECRET must be supplied, never defaulted.

`src/api/auth.py` shipped with `os.getenv("JWT_SECRET", "dev-secret-key")`.
That literal is in a public repository, `.env.example` had the variable
commented out, and `docs/SELF_HOSTING.md` did not force the point -- so on a
default install every auth token, OIDC state value and Salesforce OAuth state
value was signed with a key anyone could read off GitHub. Forging a token for
any organization required nothing but the URL.

This is the same class as the internal-events push endpoint's shared secret,
which defaulted to "dev-secret" and was fixed on
feat/integration-auth-tenancy-hardening (that endpoint has since been deleted).
That one could fail closed by rejecting requests. This one cannot -- a JWT
secret that refuses to work means nobody can log in -- so it fails LOUD
instead: the application refuses to import with an actionable message rather
than starting up quietly insecure.

Upgrade consequence, stated plainly: an operator who was relying on the default
must now set JWT_SECRET, and existing sessions are invalidated because they were
signed with a key that should never have been trusted. That is the point.

See DEV-TRACKING.md `jwt-secret-default`.
"""
import importlib
import os
import sys

import pytest


def _reload_auth_with(env: dict):
    """Re-import src.api.auth under a specific environment.

    The module reads JWT_SECRET at import time, so the guard can only be
    exercised by forcing a fresh import.

    `load_dotenv` is neutralised for the duration. auth.py calls it at import,
    which would repopulate JWT_SECRET from the developer's .env file and make
    the "genuinely unset" case untestable on any machine that has one. Real
    behaviour is unchanged: the environment or .env may supply the value, and
    if neither does, the guard fires.
    """
    from unittest.mock import patch

    saved = {k: os.environ.get(k) for k in env}
    saved_module = sys.modules.pop("src.api.auth", None)
    os.environ.update({k: v for k, v in env.items() if v is not None})
    for k, v in env.items():
        if v is None:
            os.environ.pop(k, None)
    try:
        with patch("dotenv.load_dotenv", lambda *a, **k: False):
            return importlib.import_module("src.api.auth")
    finally:
        sys.modules.pop("src.api.auth", None)
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        if saved_module is not None:
            sys.modules["src.api.auth"] = saved_module


class TestJwtSecretIsRequired:
    def test_unset_secret_refuses_to_import(self):
        with pytest.raises(RuntimeError) as exc:
            _reload_auth_with({"JWT_SECRET": None})

        message = str(exc.value)
        assert "JWT_SECRET" in message
        # The error has to tell an operator what to DO, not just what is wrong.
        assert "openssl" in message or "secrets" in message

    def test_empty_secret_refuses_to_import(self):
        """`JWT_SECRET: ${JWT_SECRET}` in docker-compose.prod.yml expands to an
        empty string when the variable is unset in the shell, so os.getenv
        returns "" rather than falling back. Empty must be rejected too."""
        with pytest.raises(RuntimeError):
            _reload_auth_with({"JWT_SECRET": ""})

    def test_the_leaked_default_is_rejected_explicitly(self):
        """Setting the old default deliberately must not be a way back in.

        The string is public; treating it as a valid secret would let an
        operator 'fix' the startup error by pasting the very value that made
        their install forgeable.
        """
        with pytest.raises(RuntimeError) as exc:
            _reload_auth_with({"JWT_SECRET": "dev-secret-key"})

        assert "no longer accepted" in str(exc.value).lower()

    def test_a_real_secret_imports_cleanly(self):
        module = _reload_auth_with({"JWT_SECRET": "a-genuinely-random-value-xyz"})
        assert module.JWT_SECRET == "a-genuinely-random-value-xyz"

    def test_source_contains_no_default_literal(self):
        """Guards against the default being reintroduced by a merge."""
        from pathlib import Path

        source = Path(__file__).resolve().parents[1] / "src" / "api" / "auth.py"
        text = source.read_text()
        assert 'os.getenv("JWT_SECRET", "dev-secret-key")' not in text
        assert "getenv('JWT_SECRET', 'dev-secret-key')" not in text
