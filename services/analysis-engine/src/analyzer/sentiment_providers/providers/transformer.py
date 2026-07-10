from __future__ import annotations
import threading
from ..base import SentimentProvider, SentimentScore

_MODEL_NAME = "cardiffnlp/twitter-roberta-base-sentiment-latest"
# TODO(model-packaging / eval-harness-and-card): pin to a specific commit SHA once the real
# weights are downloaded and license-checked (see PRD Risks — model licensing/provenance;
# spec.md OQ2). "main" is a placeholder, not a final pin.
_MODEL_REVISION = "main"
# cardiffnlp/twitter-roberta-base-sentiment-latest label order (model card): 0=negative,
# 1=neutral, 2=positive — matches PRD must-have #3's stated softmax order.
_MAX_TOKEN_LENGTH = 512

_singleton_lock = threading.Lock()
_singleton_model = None
_singleton_tokenizer = None


def _get_model_and_tokenizer():
    """Lazily load + cache the model/tokenizer once per process (double-checked locking).
    Imports torch/transformers here, NOT at module level — this function is the only place
    in the whole sentiment_providers package that touches those heavy deps."""
    global _singleton_model, _singleton_tokenizer
    if _singleton_model is None:
        with _singleton_lock:
            if _singleton_model is None:
                from transformers import (
                    AutoModelForSequenceClassification,
                    AutoTokenizer,
                )
                tokenizer = AutoTokenizer.from_pretrained(_MODEL_NAME, revision=_MODEL_REVISION)
                model = AutoModelForSequenceClassification.from_pretrained(
                    _MODEL_NAME, revision=_MODEL_REVISION
                )
                model.eval()
                _singleton_tokenizer = tokenizer
                _singleton_model = model
    return _singleton_model, _singleton_tokenizer


class TransformerSentimentProvider(SentimentProvider):
    """CPU transformer provider — cardiffnlp/twitter-roberta-base-sentiment-latest.

    Model loads once per process on first score() call (module-level singleton, shared
    across every provider instance — PRD #9). Deterministic: eval() mode, no sampling.
    """

    MODEL_NAME = _MODEL_NAME

    def score(self, text: str) -> SentimentScore:
        import torch  # deferred — see _get_model_and_tokenizer docstring

        model, tokenizer = _get_model_and_tokenizer()
        inputs = tokenizer(
            text or "", return_tensors="pt", truncation=True, max_length=_MAX_TOKEN_LENGTH
        )
        with torch.no_grad():
            logits = model(**inputs).logits
        p_neg, p_neu, p_pos = torch.softmax(logits, dim=-1)[0].tolist()
        return {
            "compound": p_pos - p_neg,
            "pos": p_pos,
            "neu": p_neu,
            "neg": p_neg,
        }
