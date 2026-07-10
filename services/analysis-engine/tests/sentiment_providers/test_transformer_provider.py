"""Tests for TransformerSentimentProvider — mocked model/tokenizer, no real weights/download
(AC4, AC10, AC11)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import torch

import src.analyzer.sentiment_providers.providers.transformer as transformer_module
from src.analyzer.sentiment_providers.providers.transformer import (
    TransformerSentimentProvider,
)


@pytest.fixture(autouse=True)
def reset_singleton():
    """Ensure each test starts with a clean per-process singleton so mocked from_pretrained
    call counts are test-isolated."""
    transformer_module._singleton_model = None
    transformer_module._singleton_tokenizer = None
    yield
    transformer_module._singleton_model = None
    transformer_module._singleton_tokenizer = None


def _make_mock_tokenizer():
    tokenizer = MagicMock()
    tokenizer.return_value = {"input_ids": torch.tensor([[1, 2, 3]])}
    return tokenizer


def _make_mock_model(logits: list):
    """Build a mock model whose __call__ returns an object with a `.logits` tensor that
    softmaxes to the desired [neg, neu, pos] probabilities."""
    model = MagicMock()
    output = MagicMock()
    output.logits = torch.tensor([logits])
    model.return_value = output
    return model


@patch("transformers.AutoModelForSequenceClassification.from_pretrained")
@patch("transformers.AutoTokenizer.from_pretrained")
def test_score_maps_softmax_to_contract(mock_tok_from_pretrained, mock_model_from_pretrained):
    # logits chosen so softmax([neg, neu, pos]) ~= [0.7, 0.2, 0.1]
    # (approximate values; assert via pytest.approx with reasonably loose tolerance)
    import math

    def logit_for(p):
        return math.log(p)

    logits = [logit_for(0.7), logit_for(0.2), logit_for(0.1)]

    mock_tok_from_pretrained.return_value = _make_mock_tokenizer()
    mock_model_from_pretrained.return_value = _make_mock_model(logits)

    provider = TransformerSentimentProvider()
    result = provider.score("This is fine.")

    assert result["neg"] == pytest.approx(0.7, abs=1e-3)
    assert result["neu"] == pytest.approx(0.2, abs=1e-3)
    assert result["pos"] == pytest.approx(0.1, abs=1e-3)
    assert result["compound"] == pytest.approx(0.1 - 0.7, abs=1e-6)


@patch("transformers.AutoModelForSequenceClassification.from_pretrained")
@patch("transformers.AutoTokenizer.from_pretrained")
def test_model_is_per_process_singleton_across_instances(
    mock_tok_from_pretrained, mock_model_from_pretrained
):
    mock_tok_from_pretrained.return_value = _make_mock_tokenizer()
    mock_model_from_pretrained.return_value = _make_mock_model([1.0, 0.0, -1.0])

    provider_a = TransformerSentimentProvider()
    provider_b = TransformerSentimentProvider()

    provider_a.score("text one")
    provider_b.score("text two")
    provider_a.score("text three")

    assert mock_tok_from_pretrained.call_count == 1
    assert mock_model_from_pretrained.call_count == 1


@patch("transformers.AutoModelForSequenceClassification.from_pretrained")
@patch("transformers.AutoTokenizer.from_pretrained")
def test_score_is_deterministic_for_identical_input(
    mock_tok_from_pretrained, mock_model_from_pretrained
):
    mock_tok_from_pretrained.return_value = _make_mock_tokenizer()
    mock_model_from_pretrained.return_value = _make_mock_model([0.5, 0.3, -0.2])

    provider = TransformerSentimentProvider()

    result_1 = provider.score("identical text")
    result_2 = provider.score("identical text")

    assert result_1 == result_2


@patch("transformers.AutoModelForSequenceClassification.from_pretrained")
@patch("transformers.AutoTokenizer.from_pretrained")
def test_model_eval_mode_is_set(mock_tok_from_pretrained, mock_model_from_pretrained):
    mock_tok_from_pretrained.return_value = _make_mock_tokenizer()
    mock_model = _make_mock_model([0.1, 0.1, 0.1])
    mock_model_from_pretrained.return_value = mock_model

    provider = TransformerSentimentProvider()
    provider.score("text")

    mock_model.eval.assert_called_once()
