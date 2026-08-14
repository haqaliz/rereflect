"""
Unit tests for the churn label-gate study harness core
(scripts/eval_churn_label_gate.py — importable, no DB, no CLI).

Pins the things the committed artifact depends on:
  - the DGP produces per-family churn rates in the PRD's band;
  - the learning-curve core is deterministic under a fixed seed (same seed ->
    byte-identical points, the artifact's reproducibility contract);
  - the crossover + verdict rules are the deterministic mapping documented in
    the script (and re-computed inside build_artifact);
  - the R3 fidelity defaulting replaces exactly the declared rows.
"""
from __future__ import annotations

import numpy as np
import pytest

from scripts import eval_churn_label_gate as harness


class TestDataGeneratingProcess:
    @pytest.mark.parametrize("family", harness.FAMILIES, ids=lambda f: f.name)
    def test_churn_rate_within_prd_band(self, family):
        rng = np.random.default_rng(42)
        X, y, component = harness.simulate_org_dataset(2000, family, rng)
        rate = float(y.mean())
        assert 0.05 <= rate <= 0.28
        assert X.shape == (2000, harness.N_FEATURES)
        assert component.shape == (2000,)

    def test_churn_risk_component_is_a_positive_proxy(self):
        """The incumbent's input must correlate positively with the label (high
        component = high churn risk) — the DGP's sign convention."""
        rng = np.random.default_rng(7)
        X, y, component = harness.simulate_org_dataset(2000, harness.FAMILIES[0], rng)
        assert float(np.corrcoef(component, y)[0, 1]) > 0.1

    def test_missing_snapshots_reconstruct_only_declared_rows(self):
        rng = np.random.default_rng(3)
        X, y, component = harness.simulate_org_dataset(200, harness.FAMILIES[0], rng)
        X2, component2 = harness.apply_missing_snapshots(X, y, component, 0.25, rng)
        assert (X2 != X).sum() > 0  # some rows were reconstructed
        for name in harness.FEATURE_COLUMNS[:10]:
            idx = harness.FEATURE_COLUMNS.index(name)
            changed = X2[:, idx] != X[:, idx]
            assert set(X2[changed, idx]) <= {harness._MISSING_DEFAULTS[name]}
        changed_rows = (X2[:, :10] != X[:, :10]).any(axis=1)
        assert changed_rows.sum() == int(round(200 * 0.25))


class TestDeterminismAndRules:
    def test_learning_curve_is_deterministic_under_same_seed(self):
        first = harness.run_learning_curve(20260814, n_simulations=2)
        second = harness.run_learning_curve(20260814, n_simulations=2)
        assert [p.to_dict() for p in first] == [p.to_dict() for p in second]

    def test_crossover_rule(self):
        def point(volume, delta, promo):
            return harness.CurvePoint(
                label_volume=volume,
                challenger_macro_f1=0.5 + delta,
                incumbent_macro_f1=0.5,
                macro_f1_delta=delta,
                delta_ci_low=delta - 0.05,
                delta_ci_high=delta + 0.05,
                promotion_rate=promo,
            )

        curve = [
            point(20, 0.00, 0.3),
            point(50, 0.01, 0.4),
            point(100, 0.025, 0.6),  # crosses here
            point(200, 0.03, 0.7),
        ]
        assert harness.crossover_of(curve) == 100

        never = [point(20, -0.1, 0.1), point(1200, 0.01, 0.4)]
        assert harness.crossover_of(never) is None

        delta_ok_promo_weak = [point(50, 0.05, 0.4)]
        assert harness.crossover_of(delta_ok_promo_weak) is None

    def test_verdict_rule(self):
        assert harness.determine_verdict(200, 200) == ("keep_500", 500)
        assert harness.determine_verdict(300, 800) == ("raise_to_800", 800)
        assert harness.determine_verdict(None, 300) == ("keep_500", 500)
        assert harness.determine_verdict(None, None) == ("no_defensible_gate", None)

    def test_artifact_embeds_its_own_verdict(self):
        """The artifact's verdict must be recomputable from its curves — the
        committed file can never disagree with the numbers it embeds."""
        full_curve = harness.run_learning_curve(20260814, n_simulations=2)
        fidelity_curve = harness.run_learning_curve(20260814, n_simulations=2, missing_fraction=0.25)
        artifact = harness.build_artifact(
            n_simulations=2,
            missing_fraction=0.25,
            full_curve=full_curve,
            fidelity_curve=fidelity_curve,
            full_crossover=harness.crossover_of(full_curve),
            fidelity_crossover=harness.crossover_of(fidelity_curve),
        )
        expected_verdict, expected_target = harness.determine_verdict(
            artifact["crossover_label_volume"],
            artifact["fidelity_sensitivity"]["crossover_label_volume"],
        )
        assert artifact["verdict"] == expected_verdict
        assert artifact["target"] == expected_target
        assert set(artifact.keys()) == {
            "artifact_version",
            "generated_at",
            "verdict",
            "target",
            "method",
            "n_simulations",
            "crossover_label_volume",
            "fidelity_sensitivity",
            "honest_limits",
            "curves",
        }
