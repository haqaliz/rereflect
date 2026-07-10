"""
Tests for scripts/eval_sentiment.py — the offline sentiment eval harness
(eval-harness-and-card aspect, M5.1 disclosure layer).

Phase 1: multiclass metrics core (pure, no CSV, no providers).

TDD: RED first, then production code in scripts/eval_sentiment.py.
"""
from __future__ import annotations

import os

import pytest

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures", "sentiment_eval")
TINY_FIXTURE_PATH = os.path.join(FIXTURES_DIR, "tiny_fixture.csv")
PUBLIC_EVAL_PATH = os.path.join(FIXTURES_DIR, "public_eval.csv")
IN_DOMAIN_EVAL_PATH = os.path.join(FIXTURES_DIR, "in_domain_eval.csv")


class TestMulticlassMetrics:
    """compute_multiclass_metrics(confusion, labels) against hand-built confusion matrices.

    Confusion matrix convention: confusion[true_label][predicted_label] = count.

    Fixture matrix (rows = true, cols = predicted):
        confusion = {
          "positive": {"positive": 8, "neutral": 1, "negative": 1},
          "neutral":  {"positive": 2, "neutral": 6, "negative": 2},
          "negative": {"positive": 0, "neutral": 1, "negative": 9},
        }

    For "positive" (one-vs-rest):
      tp = confusion["positive"]["positive"] = 8
      fp = confusion["neutral"]["positive"] + confusion["negative"]["positive"] = 2 + 0 = 2
      fn = confusion["positive"]["neutral"] + confusion["positive"]["negative"] = 1 + 1 = 2
      total = sum of all cells = 8+1+1+2+6+2+0+1+9 = 30
      tn = total - tp - fp - fn = 30 - 8 - 2 - 2 = 18
      precision = 8 / (8+2) = 0.8
      recall = 8 / (8+2) = 0.8
      f1 = 2*0.8*0.8/(0.8+0.8) = 0.8

    For "neutral":
      tp = 6; fp = confusion["positive"]["neutral"] + confusion["negative"]["neutral"] = 1+1=2
      fn = confusion["neutral"]["positive"] + confusion["neutral"]["negative"] = 2+2=4
      precision = 6/8 = 0.75; recall = 6/10 = 0.6
      f1 = 2*0.75*0.6/(0.75+0.6) = 0.9/1.35 = 0.6666...

    For "negative":
      tp = 9; fp = confusion["positive"]["negative"] + confusion["neutral"]["negative"] = 1+2=3
      fn = confusion["negative"]["positive"] + confusion["negative"]["neutral"] = 0+1=1
      precision = 9/12 = 0.75; recall = 9/10 = 0.9
      f1 = 2*0.75*0.9/(0.75+0.9) = 1.35/1.65 = 0.818181...

    macro_f1 = mean(0.8, 0.666..., 0.81818...) = 0.761616...
    accuracy = trace/total = (8+6+9)/30 = 23/30 = 0.766666...
    """

    CONFUSION = {
        "positive": {"positive": 8, "neutral": 1, "negative": 1},
        "neutral": {"positive": 2, "neutral": 6, "negative": 2},
        "negative": {"positive": 0, "neutral": 1, "negative": 9},
    }
    LABELS = ["positive", "neutral", "negative"]

    def test_confusion_to_binary_counts_positive(self):
        from scripts.eval_sentiment import confusion_to_binary_counts

        tp, fp, fn, tn = confusion_to_binary_counts(self.CONFUSION, "positive", self.LABELS)
        assert (tp, fp, fn, tn) == (8, 2, 2, 18)

    def test_confusion_to_binary_counts_neutral(self):
        from scripts.eval_sentiment import confusion_to_binary_counts

        tp, fp, fn, tn = confusion_to_binary_counts(self.CONFUSION, "neutral", self.LABELS)
        assert (tp, fp, fn, tn) == (6, 2, 4, 18)

    def test_confusion_to_binary_counts_negative(self):
        from scripts.eval_sentiment import confusion_to_binary_counts

        tp, fp, fn, tn = confusion_to_binary_counts(self.CONFUSION, "negative", self.LABELS)
        assert (tp, fp, fn, tn) == (9, 3, 1, 17)

    def test_compute_multiclass_metrics_per_class_positive(self):
        from scripts.eval_sentiment import compute_multiclass_metrics

        result = compute_multiclass_metrics(self.CONFUSION, self.LABELS)
        pos = result["per_class"]["positive"]
        assert pos["precision"] == pytest.approx(0.8)
        assert pos["recall"] == pytest.approx(0.8)
        assert pos["f1"] == pytest.approx(0.8)
        assert pos["support"] == 10

    def test_compute_multiclass_metrics_per_class_neutral(self):
        from scripts.eval_sentiment import compute_multiclass_metrics

        result = compute_multiclass_metrics(self.CONFUSION, self.LABELS)
        neu = result["per_class"]["neutral"]
        assert neu["precision"] == pytest.approx(0.75)
        assert neu["recall"] == pytest.approx(0.6)
        assert neu["f1"] == pytest.approx(2 * 0.75 * 0.6 / (0.75 + 0.6))
        assert neu["support"] == 10

    def test_compute_multiclass_metrics_per_class_negative(self):
        from scripts.eval_sentiment import compute_multiclass_metrics

        result = compute_multiclass_metrics(self.CONFUSION, self.LABELS)
        neg = result["per_class"]["negative"]
        assert neg["precision"] == pytest.approx(0.75)
        assert neg["recall"] == pytest.approx(0.9)
        assert neg["f1"] == pytest.approx(2 * 0.75 * 0.9 / (0.75 + 0.9))
        assert neg["support"] == 10

    def test_macro_f1_is_mean_of_per_class_f1(self):
        from scripts.eval_sentiment import compute_multiclass_metrics

        result = compute_multiclass_metrics(self.CONFUSION, self.LABELS)
        per_class_f1 = [result["per_class"][label]["f1"] for label in self.LABELS]
        assert result["macro_f1"] == pytest.approx(sum(per_class_f1) / len(per_class_f1))

    def test_macro_precision_and_recall_are_unweighted_means(self):
        from scripts.eval_sentiment import compute_multiclass_metrics

        result = compute_multiclass_metrics(self.CONFUSION, self.LABELS)
        per_class_p = [result["per_class"][label]["precision"] for label in self.LABELS]
        per_class_r = [result["per_class"][label]["recall"] for label in self.LABELS]
        assert result["macro_precision"] == pytest.approx(sum(per_class_p) / len(per_class_p))
        assert result["macro_recall"] == pytest.approx(sum(per_class_r) / len(per_class_r))

    def test_accuracy_is_trace_over_total(self):
        from scripts.eval_sentiment import compute_multiclass_metrics

        result = compute_multiclass_metrics(self.CONFUSION, self.LABELS)
        assert result["accuracy"] == pytest.approx(23 / 30)

    def test_all_zero_confusion_returns_zeros_not_zero_division_error(self):
        from scripts.eval_sentiment import compute_multiclass_metrics

        zero_confusion = {
            "positive": {"positive": 0, "neutral": 0, "negative": 0},
            "neutral": {"positive": 0, "neutral": 0, "negative": 0},
            "negative": {"positive": 0, "neutral": 0, "negative": 0},
        }
        result = compute_multiclass_metrics(zero_confusion, self.LABELS)
        assert result["macro_precision"] == 0.0
        assert result["macro_recall"] == 0.0
        assert result["macro_f1"] == 0.0
        assert result["accuracy"] == 0.0
        for label in self.LABELS:
            assert result["per_class"][label]["precision"] == 0.0
            assert result["per_class"][label]["recall"] == 0.0
            assert result["per_class"][label]["f1"] == 0.0
            assert result["per_class"][label]["support"] == 0

    def test_single_class_only_confusion_matrix(self):
        """Every gold row and every prediction is 'positive' — perfect single-class set."""
        from scripts.eval_sentiment import compute_multiclass_metrics

        single_class_confusion = {
            "positive": {"positive": 5, "neutral": 0, "negative": 0},
            "neutral": {"positive": 0, "neutral": 0, "negative": 0},
            "negative": {"positive": 0, "neutral": 0, "negative": 0},
        }
        result = compute_multiclass_metrics(single_class_confusion, self.LABELS)
        assert result["per_class"]["positive"]["precision"] == pytest.approx(1.0)
        assert result["per_class"]["positive"]["recall"] == pytest.approx(1.0)
        assert result["per_class"]["positive"]["f1"] == pytest.approx(1.0)
        # neutral/negative never appear at all — support 0, precision/recall/f1 0 (no ZeroDivisionError)
        assert result["per_class"]["neutral"]["support"] == 0
        assert result["per_class"]["neutral"]["precision"] == 0.0
        assert result["per_class"]["negative"]["support"] == 0
        assert result["accuracy"] == pytest.approx(1.0)


class TestLoadEvalCsv:
    """load_eval_csv(path) -> list[(text, label)]."""

    def test_loads_tiny_fixture_with_exact_known_length_and_distribution(self):
        from scripts.eval_sentiment import load_eval_csv

        rows = load_eval_csv(TINY_FIXTURE_PATH)
        assert len(rows) == 9
        labels = [label for _, label in rows]
        assert labels.count("positive") == 3
        assert labels.count("neutral") == 3
        assert labels.count("negative") == 3
        for text, label in rows:
            assert isinstance(text, str) and text.strip() != ""
            assert label in ("positive", "neutral", "negative")

    def test_malformed_label_raises_value_error_naming_bad_row(self, tmp_path):
        from scripts.eval_sentiment import load_eval_csv

        bad_csv = tmp_path / "bad.csv"
        bad_csv.write_text(
            "text,label\n"
            '"This is fine.",positive\n'
            '"Typo label here.",positve\n'
        )
        with pytest.raises(ValueError, match=r"(?i)row 3|positve"):
            load_eval_csv(str(bad_csv))

    def test_missing_text_header_raises(self, tmp_path):
        from scripts.eval_sentiment import load_eval_csv

        bad_csv = tmp_path / "no_text_header.csv"
        bad_csv.write_text("body,label\n" '"whatever",positive\n')
        with pytest.raises(ValueError, match=r"(?i)header"):
            load_eval_csv(str(bad_csv))

    def test_missing_label_header_raises(self, tmp_path):
        from scripts.eval_sentiment import load_eval_csv

        bad_csv = tmp_path / "no_label_header.csv"
        bad_csv.write_text("text,sentiment\n" '"whatever",positive\n')
        with pytest.raises(ValueError, match=r"(?i)header"):
            load_eval_csv(str(bad_csv))

    def test_empty_text_row_raises(self, tmp_path):
        from scripts.eval_sentiment import load_eval_csv

        bad_csv = tmp_path / "empty_text.csv"
        bad_csv.write_text("text,label\n" ',positive\n')
        with pytest.raises(ValueError, match=r"(?i)row 2|empty"):
            load_eval_csv(str(bad_csv))


class _FakeProvider:
    """Fixed/scripted-label fake sentiment provider for TestRunProvider/TestRunEvalSet.

    Matches the real SentimentProvider contract: .score(text) -> {compound, pos, neu, neg}
    (sentiment_providers/base.py). run_provider derives a label from compound via the same
    ±0.05 thresholds SentimentAnalyzer._classify_label uses, so scripted_labels below are
    expressed directly as compound scores that land unambiguously in each bucket.
    """

    #: text -> compound score to return
    _COMPOUND_BY_TEXT = {}

    def __init__(self, compound_by_text: dict):
        self._compound_by_text = compound_by_text

    def score(self, text: str) -> dict:
        compound = self._compound_by_text[text]
        if compound > 0:
            pos, neu, neg = abs(compound), 1 - abs(compound), 0.0
        elif compound < 0:
            pos, neu, neg = 0.0, 1 - abs(compound), abs(compound)
        else:
            pos, neu, neg = 0.0, 1.0, 0.0
        return {"compound": compound, "pos": pos, "neu": neu, "neg": neg}


class TestRunProvider:
    def test_confusion_matrix_matches_hand_counted_true_predicted_pairs(self):
        from scripts.eval_sentiment import load_eval_csv, run_provider

        rows = load_eval_csv(TINY_FIXTURE_PATH)
        # Fake provider always predicts "positive" (compound = 0.9) regardless of text.
        compound_by_text = {text: 0.9 for text, _ in rows}
        fake = _FakeProvider(compound_by_text)

        result = run_provider(fake, rows, provider_name="fake")

        assert result.provider == "fake"
        assert result.n == 9
        # every true label routed to predicted="positive"
        true_counts = {}
        for _, true_label in rows:
            true_counts[true_label] = true_counts.get(true_label, 0) + 1
        for true_label, count in true_counts.items():
            assert result.confusion_matrix[true_label]["positive"] == count
            for other in ("neutral", "negative"):
                assert result.confusion_matrix[true_label][other] == 0

    def test_confusion_matrix_initialized_for_all_label_pairs_even_unseen(self):
        from scripts.eval_sentiment import SENTIMENT_LABELS, load_eval_csv, run_provider

        rows = load_eval_csv(TINY_FIXTURE_PATH)
        compound_by_text = {text: 0.9 for text, _ in rows}
        fake = _FakeProvider(compound_by_text)
        result = run_provider(fake, rows, provider_name="fake")

        for true_label in SENTIMENT_LABELS:
            for pred_label in SENTIMENT_LABELS:
                assert pred_label in result.confusion_matrix[true_label]


class TestRunEvalSet:
    def test_both_providers_populated_with_scripted_metrics(self):
        from scripts.eval_sentiment import load_eval_csv, run_eval_set

        rows = load_eval_csv(TINY_FIXTURE_PATH)
        vader_compounds = {text: 0.9 if label == "positive" else (-0.9 if label == "negative" else 0.0) for text, label in rows}
        transformer_compounds = {text: 0.9 for text, _ in rows}  # always predicts positive

        vader = _FakeProvider(vader_compounds)
        transformer = _FakeProvider(transformer_compounds)

        result = run_eval_set(
            "in_domain", TINY_FIXTURE_PATH, vader_provider=vader, transformer_provider=transformer
        )

        assert result.set_name == "in_domain"
        assert result.n == 9
        assert result.vader is not None
        assert result.transformer is not None
        assert result.macro_f1_delta == pytest.approx(
            result.transformer.macro_f1 - result.vader.macro_f1
        )

    def test_meets_target_only_computed_for_in_domain_set(self):
        from scripts.eval_sentiment import load_eval_csv, run_eval_set

        rows = load_eval_csv(TINY_FIXTURE_PATH)
        vader_compounds = {text: 0.0 for text, _ in rows}
        transformer_compounds = {text: 0.9 if label == "positive" else (-0.9 if label == "negative" else 0.0) for text, label in rows}
        vader = _FakeProvider(vader_compounds)
        transformer = _FakeProvider(transformer_compounds)

        in_domain_result = run_eval_set(
            "in_domain", TINY_FIXTURE_PATH, vader_provider=vader, transformer_provider=transformer
        )
        assert in_domain_result.meets_target == (in_domain_result.macro_f1_delta >= 0.05)

        public_result = run_eval_set(
            "public", TINY_FIXTURE_PATH, vader_provider=vader, transformer_provider=transformer
        )
        assert public_result.meets_target is None

    def test_graceful_skip_when_transformer_provider_is_none(self):
        from scripts.eval_sentiment import load_eval_csv, run_eval_set

        rows = load_eval_csv(TINY_FIXTURE_PATH)
        vader_compounds = {text: 0.0 for text, _ in rows}
        vader = _FakeProvider(vader_compounds)

        result = run_eval_set(
            "in_domain", TINY_FIXTURE_PATH, vader_provider=vader, transformer_provider=None
        )
        assert result.vader is not None
        assert result.transformer is None
        assert result.macro_f1_delta is None
        assert result.meets_target is None


class TestEvalSetShape:
    """Locks the shape of the two real, committed eval-set CSVs."""

    @pytest.mark.parametrize("path", [PUBLIC_EVAL_PATH, IN_DOMAIN_EVAL_PATH])
    def test_at_least_150_rows(self, path):
        from scripts.eval_sentiment import load_eval_csv

        rows = load_eval_csv(path)
        assert len(rows) >= 150, f"{path} has only {len(rows)} rows, need >= 150"

    @pytest.mark.parametrize("path", [PUBLIC_EVAL_PATH, IN_DOMAIN_EVAL_PATH])
    def test_all_labels_valid(self, path):
        from scripts.eval_sentiment import SENTIMENT_LABELS, load_eval_csv

        rows = load_eval_csv(path)
        for _, label in rows:
            assert label in SENTIMENT_LABELS

    @pytest.mark.parametrize("path", [PUBLIC_EVAL_PATH, IN_DOMAIN_EVAL_PATH])
    def test_no_duplicate_exact_text_rows(self, path):
        from scripts.eval_sentiment import load_eval_csv

        rows = load_eval_csv(path)
        texts = [text for text, _ in rows]
        assert len(texts) == len(set(texts)), "duplicate exact-text rows found"

    @pytest.mark.parametrize("path", [PUBLIC_EVAL_PATH, IN_DOMAIN_EVAL_PATH])
    def test_each_class_at_least_20_percent_represented(self, path):
        from scripts.eval_sentiment import SENTIMENT_LABELS, load_eval_csv

        rows = load_eval_csv(path)
        n = len(rows)
        counts = {label: 0 for label in SENTIMENT_LABELS}
        for _, label in rows:
            counts[label] += 1
        for label in SENTIMENT_LABELS:
            assert counts[label] / n >= 0.20, (
                f"{path}: class {label!r} has only {counts[label]}/{n} "
                f"({counts[label] / n:.1%}) rows, need >= 20%"
            )


class TestMainCli:
    def test_main_writes_artifact_with_expected_top_level_keys(self, tmp_path, monkeypatch):
        from dataclasses import replace
        import scripts.eval_sentiment as eval_sentiment_module

        fake_public = eval_sentiment_module.EvalSetResult(
            set_name="public",
            n=150,
            vader=eval_sentiment_module.ProviderEvalResult(
                provider="vader", n=150, macro_precision=0.5, macro_recall=0.5,
                macro_f1=0.5, accuracy=0.5, per_class={}, confusion_matrix={},
            ),
            transformer=eval_sentiment_module.ProviderEvalResult(
                provider="transformer", n=150, macro_precision=0.6, macro_recall=0.6,
                macro_f1=0.6, accuracy=0.6, per_class={}, confusion_matrix={},
            ),
            macro_f1_delta=0.1,
            meets_target=None,
        )
        fake_in_domain = replace(fake_public, set_name="in_domain", macro_f1_delta=0.07, meets_target=True)

        monkeypatch.setattr(
            eval_sentiment_module, "run_eval_set",
            lambda set_name, csv_path, vader_provider, transformer_provider: (
                fake_public if set_name == "public" else fake_in_domain
            ),
        )
        monkeypatch.setattr(
            eval_sentiment_module, "_build_providers", lambda: (object(), object())
        )

        output_path = tmp_path / "sentiment_accuracy.json"
        exit_code = eval_sentiment_module.main(["--output", str(output_path)])

        assert exit_code == 0
        assert output_path.exists()

        import json
        data = json.loads(output_path.read_text())
        assert set(["generated_at", "model_id", "model_revision", "public", "in_domain"]).issubset(data.keys())
        assert data["public"]["vader"]["macro_f1"] == pytest.approx(0.5)
        assert data["public"]["transformer"]["macro_f1"] == pytest.approx(0.6)
        assert data["in_domain"]["macro_f1_delta"] == pytest.approx(0.07)
        assert data["in_domain"]["meets_target"] is True
