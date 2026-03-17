"""
Intent Classifier — classifies user messages into data, analysis, or general intents.

Classification approach:
1. Rule-based regex patterns (fast, no LLM cost)
2. If ambiguous (low confidence), fall through to lightweight LLM call
3. Returns: { intent, confidence, parameters }
"""

import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ── Intent patterns ───────────────────────────────────────────────────────────

# High-signal keywords for each intent
_DATA_PATTERNS = [
    r"\bhow many\b",
    r"\bcount\b",
    r"\blist\b",
    r"\bshow me\b",
    r"\bshow all\b",
    r"\bwhich\b",
    r"\bwhat is the\b",
    r"\bwhat are the\b",
    r"\bgive me\b",
    r"\bget (all|me)\b",
    r"\btop \d+\b",
    r"\bnumber of\b",
    r"\btotal\b",
    r"\bfetch\b",
    r"\bfind\b",
    r"\bdisplay\b",
]

_ANALYSIS_PATTERNS = [
    r"\bwhy\b",
    r"\bcompare\b",
    r"\btrend\b",
    r"\btrends\b",
    r"\banalyze\b",
    r"\banalysis\b",
    r"\bexplain\b",
    r"\bcorrelation\b",
    r"\bpattern\b",
    r"\binsight\b",
    r"\bforecast\b",
    r"\bpredict\b",
    r"\bchange over time\b",
    r"\bover time\b",
    r"\bvs\b",
    r"\bversus\b",
    r"\bcompared to\b",
    r"\bmonth over month\b",
    r"\bweek over week\b",
    r"\bspike\b",
    r"\bdecline\b",
    r"\bincrease\b",
    r"\bdecrease\b",
]

_GENERAL_PATTERNS = [
    r"^(hi|hello|hey)\b",
    r"\bhelp\b",
    r"\bwhat can you\b",
    r"\bwhat do you\b",
    r"\bhow does this work\b",
    r"\bwhat is this\b",
    r"\bcan you\b",
]

_REPORT_PATTERNS = [
    r"\breport\b",
    r"\bgenerate\b.*\breport\b",
    r"\bcreate\b.*\breport\b",
    r"\bexecutive\s+summary\b",
    r"\bhealth\s+report\b",
    r"\bchurn\s+(risk\s+)?analysis\b",
    r"\bfeature\s+(request\s+)?prioriti",
    r"\bmonthly\s+summary\b",
    r"\bquarterly\s+review\b",
    r"\bweekly\s+summary\b",
]

# Minimum confidence for rule-based classification (below = LLM fallback)
_RULE_CONFIDENCE_THRESHOLD = 0.6


def _score_patterns(text: str, patterns: list[str]) -> float:
    """Count matching patterns and return a 0-1 normalized score."""
    text_lower = text.lower()
    matches = sum(1 for p in patterns if re.search(p, text_lower))
    if not patterns:
        return 0.0
    return min(1.0, matches / max(1, len(patterns) * 0.15))


class IntentClassifier:
    """
    Classifies user messages into one of four intents:
    - data: Requests for specific data/metrics
    - analysis: Requests for interpretation/trends
    - general: Help, greetings, meta-questions
    - report: Requests to generate structured reports
    """

    def classify(self, query: str) -> dict:
        """
        Classify a user query into intent + confidence + parameters.

        Returns:
            {
                "intent": "data" | "analysis" | "general" | "report",
                "confidence": float (0-1),
                "parameters": dict
            }
        """
        if not query or not query.strip():
            return {"intent": "general", "confidence": 1.0, "parameters": {}}

        # 1. Try rule-based classification
        result = self._classify_rule_based(query)

        # 2. If confidence is too low, try LLM
        if result["confidence"] < _RULE_CONFIDENCE_THRESHOLD:
            try:
                llm_result = self._classify_with_llm(query)
                if llm_result and llm_result.get("confidence", 0) > result["confidence"]:
                    return llm_result
            except Exception as e:
                logger.warning(f"LLM classification failed: {e}")
                # Fall through to rule-based result

        return result

    def _classify_rule_based(self, query: str) -> dict:
        """Apply regex patterns to classify the query."""
        data_score = _score_patterns(query, _DATA_PATTERNS)
        analysis_score = _score_patterns(query, _ANALYSIS_PATTERNS)
        general_score = _score_patterns(query, _GENERAL_PATTERNS)
        report_score = _score_patterns(query, _REPORT_PATTERNS)

        # Boost: "how many" and similar are unambiguous data queries
        text_lower = query.lower()
        if re.search(r"\bhow many\b", text_lower):
            data_score = max(data_score, 0.9)
        if re.search(r"\bcount\b", text_lower):
            data_score = max(data_score, 0.85)
        if re.search(r"^(hi|hello|hey)\b", text_lower):
            general_score = max(general_score, 0.9)
        if re.search(r"\bwhat can you\b|\bwhat do you\b|\bhow does this work\b", text_lower):
            general_score = max(general_score, 0.9)
        if re.search(r"\bhelp\b", text_lower) and not re.search(r"\b(count|list|show|how many)\b", text_lower):
            general_score = max(general_score, 0.8)
        if re.search(r"\bwhy\b", text_lower):
            analysis_score = max(analysis_score, 0.85)
        if re.search(r"\bcompare\b|\btrend[s]?\b|\banalyze\b|\banalysis\b|\bexplain\b", text_lower):
            analysis_score = max(analysis_score, 0.85)
        # If analysis keywords are strong, override weaker data signals
        if analysis_score >= 0.85 and data_score < analysis_score:
            data_score = min(data_score, 0.3)
        # Boost: report-specific high-signal patterns
        if re.search(r"\bexecutive\s+summary\b|\bhealth\s+report\b|\bchurn\s+(risk\s+)?analysis\b", text_lower):
            report_score = max(report_score, 0.9)
        if re.search(r"\bgenerate\b.*\breport\b|\bcreate\b.*\breport\b", text_lower):
            report_score = max(report_score, 0.9)
        # If a strong report signal exists, suppress data/analysis scores
        if report_score >= 0.85:
            data_score = min(data_score, 0.3)
            analysis_score = min(analysis_score, 0.3)

        scores = {
            "data": data_score,
            "analysis": analysis_score,
            "general": general_score,
            "report": report_score,
        }

        best_intent = max(scores, key=lambda k: scores[k])
        best_score = scores[best_intent]

        # If no strong signal, default to data (most common case)
        if best_score < 0.1:
            best_intent = "data"
            best_score = 0.4

        # Scale confidence: raw pattern score → 0.6-1.0 range
        confidence = 0.6 + (best_score * 0.4)
        confidence = min(1.0, confidence)

        return {
            "intent": best_intent,
            "confidence": confidence,
            "parameters": self._extract_parameters(query),
        }

    def _classify_with_llm(self, query: str) -> dict:
        """
        Use a lightweight LLM call to classify ambiguous queries.
        This is a stub — in production, use the org's configured LLM.
        """
        # Placeholder: in production, call GPT-4o-mini or similar
        # For now, raise NotImplementedError to signal LLM needed
        raise NotImplementedError("LLM classification not configured")

    def _extract_parameters(self, query: str) -> dict:
        """Extract useful parameters from the query (e.g., time references)."""
        params = {}
        text_lower = query.lower()

        # Extract time references
        if re.search(r"\bthis week\b", text_lower):
            params["time_range"] = "this_week"
        elif re.search(r"\bthis month\b", text_lower):
            params["time_range"] = "this_month"
        elif re.search(r"\blast (\d+) days?\b", text_lower):
            match = re.search(r"\blast (\d+) days?\b", text_lower)
            if match:
                params["time_range"] = f"last_{match.group(1)}_days"
        elif re.search(r"\btoday\b", text_lower):
            params["time_range"] = "today"

        # Extract limit hints
        limit_match = re.search(r"\btop (\d+)\b", text_lower)
        if limit_match:
            params["limit"] = int(limit_match.group(1))

        # Extract sentiment hints
        if re.search(r"\bnegative\b", text_lower):
            params["sentiment"] = "negative"
        elif re.search(r"\bpositive\b", text_lower):
            params["sentiment"] = "positive"
        elif re.search(r"\bneutral\b", text_lower):
            params["sentiment"] = "neutral"

        # Extract urgency hint
        if re.search(r"\burgent\b", text_lower):
            params["is_urgent"] = True

        return params
