"""R8 sweep-guard: no integration route may write a credential column unencrypted.

The DB contract (DEV-TRACKING ``oauth-tokens-stored-plaintext`` +
``linear-webhook-secret-plaintext``) is that every credential column —
``webhook_secret``, ``oauth_access_token``, ``signing_secret`` — holds Fernet
ciphertext at rest, and that any route writing one of those columns goes through
``encrypt_api_key`` from ``src.utils.encryption``. A route that assigns the column
directly (``existing.webhook_secret = raw``) or passes it as a constructor keyword
(``LinearIntegration(webhook_secret=raw)``) without importing the helper is the
plaintext-at-rest bug class this sweep pins. It is deliberately mechanical (AST
only, no imports, no DB): a future route that writes a credential column without
the encrypt helper fails here with the module and column named, in the same spirit
as ``worker-service/tests/test_worker_import_sweep.py``.
"""
import ast
from pathlib import Path

# Credential columns that must never be written as plaintext.
CREDENTIAL_COLUMNS = {"webhook_secret", "oauth_access_token", "signing_secret"}

ROUTES_DIR = Path(__file__).resolve().parents[1] / "src" / "api" / "routes"
MODELS_DIR = Path(__file__).resolve().parents[1] / "src" / "models"
LINEAR_MODEL = MODELS_DIR / "linear_integration.py"


def _imports_encrypt_api_key(tree: ast.AST) -> bool:
    """True if the module imports ``encrypt_api_key`` (import or from-import)."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(alias.name == "src.utils.encryption" for alias in node.names):
                return True
        elif isinstance(node, ast.ImportFrom):
            if any(alias.name == "encrypt_api_key" for alias in node.names):
                return True
    return False


def _credential_writes(tree: ast.AST):
    """Yield (lineno, column) for every write of a credential column.

    Two shapes are detected:
    - attribute assignment: ``existing.webhook_secret = ...``
    - constructor keyword arg: ``LinearIntegration(webhook_secret=...)``
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Attribute) and target.attr in CREDENTIAL_COLUMNS:
                    yield node.lineno, target.attr
        elif isinstance(node, ast.keyword) and node.arg in CREDENTIAL_COLUMNS:
            yield node.lineno, node.arg


def test_credential_writes_import_encrypt_helper():
    violations = []
    for py in sorted(ROUTES_DIR.rglob("*.py")):
        tree = ast.parse(py.read_text())
        if _imports_encrypt_api_key(tree):
            continue
        for lineno, column in _credential_writes(tree):
            rel = py.relative_to(ROUTES_DIR)
            violations.append(f"{rel}:{lineno}: writes {column!r}")

    assert not violations, (
        "route module writes a credential column without importing encrypt_api_key "
        "from src.utils.encryption (plaintext-at-rest bug class):\n"
        + "\n".join(violations)
    )


def test_linear_webhook_secret_column_documents_encryption():
    column_line = None
    for line in LINEAR_MODEL.read_text().splitlines():
        if "webhook_secret" in line and "Column(" in line:
            column_line = line
            break

    assert column_line is not None, (
        f"{LINEAR_MODEL.relative_to(MODELS_DIR)} has no webhook_secret column definition"
    )
    assert "encrypt" in column_line.lower() or "Fernet" in column_line, (
        "models/linear_integration.py webhook_secret column must carry an encryption "
        "comment (contains 'encrypt' or 'Fernet'), so the at-rest contract is visible "
        "next to the column: "
        + column_line
    )
