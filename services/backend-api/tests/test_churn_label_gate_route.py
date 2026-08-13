"""
Tests for GET /api/v1/settings/ai/churn/label-gate (churn-label-gate-study
aspect 2). Reads the committed eval_churn_label_gate.py results artifact
(services/backend-api/eval_results/churn_label_gate.json) and serves it as a
typed, never-raising response.

TDD: RED first, then production code in
src/api/routes/churn_label_gate.py + src/schemas/churn_label_gate.py.
"""
from __future__ import annotations

import json
from datetime import datetime

import pytest

from src.api.auth import create_access_token


def _curve_point(volume: int, delta: float, promotion_rate: float = 0.5) -> dict:
    return {
        "label_volume": volume,
        "challenger_macro_f1": 0.60 + delta,
        "incumbent_macro_f1": 0.60,
        "macro_f1_delta": delta,
        "delta_ci_low": delta - 0.03,
        "delta_ci_high": delta + 0.03,
        "promotion_rate": promotion_rate,
    }


FULL_ARTIFACT = {
    "artifact_version": "1",
    "generated_at": "2026-08-14T12:00:00+00:00",
    "verdict": "keep_500",
    "target": 500,
    "method": (
        "simulated learning curves: per-org logistic challenger vs identity "
        "incumbent on churn_risk_component; leakage-free stratified holdout; "
        "3 scenario families x n simulations (fixed seeds)"
    ),
    "n_simulations": 50,
    "crossover_label_volume": 300,
    "fidelity_sensitivity": {
        "missing_fraction": 0.25,
        "crossover_label_volume": 500,
        "curves": [
            _curve_point(20, -0.05),
            _curve_point(50, -0.02),
            _curve_point(100, 0.0),
            _curve_point(200, 0.01),
            _curve_point(300, 0.02, promotion_rate=0.55),
            _curve_point(500, 0.03, promotion_rate=0.8),
            _curve_point(800, 0.035, promotion_rate=0.85),
            _curve_point(1200, 0.04, promotion_rate=0.9),
        ],
    },
    "honest_limits": [
        "Simulation is a bound, not a measurement: no real org is at label volume.",
        "The identity incumbent is a lower bound on incumbent strength; the real "
        "calibrated incumbent would be harder to beat, so the crossover is optimistic.",
    ],
    "curves": [
        _curve_point(20, -0.03),
        _curve_point(50, 0.0),
        _curve_point(100, 0.01),
        _curve_point(200, 0.015),
        _curve_point(300, 0.022, promotion_rate=0.6),
        _curve_point(500, 0.032, promotion_rate=0.85),
        _curve_point(800, 0.038, promotion_rate=0.9),
        _curve_point(1200, 0.042, promotion_rate=0.93),
    ],
}


@pytest.fixture
def patch_artifact_path(monkeypatch, tmp_path):
    """Monkeypatch the route's artifact path constant to a tmp file we control."""
    import src.api.routes.churn_label_gate as route_module

    def _set(content: str | None):
        path = tmp_path / "churn_label_gate.json"
        if content is not None:
            path.write_text(content)
        monkeypatch.setattr(route_module, "_ARTIFACT_PATH", str(path))
        return path

    return _set


class TestChurnLabelGateRoute:
    def test_missing_artifact_returns_200_has_results_false(
        self, client, auth_headers, patch_artifact_path
    ):
        patch_artifact_path(None)  # never write the file -> FileNotFoundError path

        response = client.get("/api/v1/settings/ai/churn/label-gate", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["has_results"] is False
        assert data["generated_at"] is None
        assert data["verdict"] is None
        assert data["target"] is None
        assert data["method"] is None
        assert data["n_simulations"] is None
        assert data["crossover_label_volume"] is None
        assert data["fidelity_sensitivity"] is None
        assert data["honest_limits"] is None
        assert data["curves"] is None

    def test_full_artifact_returns_parsed_verdict(
        self, client, auth_headers, patch_artifact_path
    ):
        patch_artifact_path(json.dumps(FULL_ARTIFACT))

        response = client.get("/api/v1/settings/ai/churn/label-gate", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["has_results"] is True
        assert data["artifact_version"] == "1"
        assert data["verdict"] == "keep_500"
        assert data["target"] == 500
        assert data["n_simulations"] == 50
        assert data["crossover_label_volume"] == 300
        assert data["method"] == FULL_ARTIFACT["method"]
        assert isinstance(data["honest_limits"], list) and data["honest_limits"]
        assert datetime.fromisoformat(data["generated_at"]) == datetime.fromisoformat(
            "2026-08-14T12:00:00+00:00"
        )

        curves = data["curves"]
        assert [c["label_volume"] for c in curves] == [20, 50, 100, 200, 300, 500, 800, 1200]
        assert curves[5]["macro_f1_delta"] == pytest.approx(0.032)
        assert curves[5]["promotion_rate"] == pytest.approx(0.85)

        fidelity = data["fidelity_sensitivity"]
        assert fidelity["missing_fraction"] == 0.25
        assert fidelity["crossover_label_volume"] == 500
        assert fidelity["curves"][4]["macro_f1_delta"] == pytest.approx(0.02)

    def test_malformed_json_artifact_degrades_to_has_results_false(
        self, client, auth_headers, patch_artifact_path
    ):
        patch_artifact_path("{not valid json,,,")

        response = client.get("/api/v1/settings/ai/churn/label-gate", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["has_results"] is False

    def test_requires_auth_401_without_token(self, client, patch_artifact_path):
        patch_artifact_path(json.dumps(FULL_ARTIFACT))

        response = client.get("/api/v1/settings/ai/churn/label-gate")

        assert response.status_code in (401, 403)

    def test_artifact_is_org_agnostic_static_file(
        self, client, db, test_organization, auth_headers, patch_artifact_path
    ):
        """Org-scoping is trivially satisfied: the artifact is a single static
        file, so a different org's user must see the identical payload with no
        per-org fields leaking."""
        from src.models.organization import Organization
        from src.models.user import User
        from src.api.auth import hash_password

        other_org = Organization(name="Other Company", plan="pro")
        db.add(other_org)
        db.commit()
        db.refresh(other_org)

        other_user = User(
            email="other@example.com",
            password_hash=hash_password("password123"),
            organization_id=other_org.id,
            role="member",
        )
        db.add(other_user)
        db.commit()
        db.refresh(other_user)
        other_token = create_access_token(
            {
                "user_id": other_user.id,
                "organization_id": other_org.id,
                "role": other_user.role,
            }
        )

        patch_artifact_path(json.dumps(FULL_ARTIFACT))

        response = client.get("/api/v1/settings/ai/churn/label-gate", headers=auth_headers)
        other_response = client.get(
            "/api/v1/settings/ai/churn/label-gate",
            headers={"Authorization": f"Bearer {other_token}"},
        )

        assert response.status_code == 200
        assert other_response.status_code == 200
        assert response.json() == other_response.json()
        assert response.json()["has_results"] is True
