from __future__ import annotations
from ..base import SentimentProvider, SentimentScore


class TransformerSentimentProvider(SentimentProvider):
    """CPU transformer provider — cardiffnlp/twitter-roberta-base-sentiment-latest.

    Phase 4 stub: constructible without importing torch/transformers so
    SentimentProviderFactory.create("transformer") can be tested without a real model. Full
    scoring implementation (lazy singleton model/tokenizer load, softmax mapping) lands in
    Phase 5.
    """

    def score(self, text: str) -> SentimentScore:
        raise NotImplementedError(
            "TransformerSentimentProvider.score is implemented in Phase 5"
        )
