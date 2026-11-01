"""
Natural Language Intent Classifier for user queries in the SIP Discovery Engine.

Classifies incoming queries into 5 structured intents:
- COUNT_QUERY
- COMPARISON_QUERY
- DRILL_DOWN
- EXPLORATION_QUERY
- REFUSAL
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from src.query.guardrails import GuardrailsChecker
from src.utils.logging import get_logger

logger = get_logger(__name__)


class IntentType(str, Enum):
    COUNT = "count_query"
    COMPARISON = "comparison_query"
    DRILL_DOWN = "drill_down"
    EXPLORATION = "exploration_query"
    REFUSAL = "refusal"


@dataclass
class QueryIntent:
    intent_type: IntentType
    raw_query: str
    dimensions: list[str] = field(default_factory=list)
    filters: dict[str, Any] = field(default_factory=dict)
    theme_focus: Optional[str] = None
    refusal_reason: Optional[str] = None
    refusal_message: Optional[str] = None
    confidence: float = 1.0


class IntentClassifier:
    """
    Rule-based and semantic intent classifier for SIP user queries.
    """

    def __init__(self, guardrails: Optional[GuardrailsChecker] = None):
        self.guardrails = guardrails or GuardrailsChecker()

    def classify(self, query: str) -> QueryIntent:
        """
        Classify a user query into structured QueryIntent.
        """
        q = query.strip()
        q_lower = q.lower()

        # 1. Guardrail / Refusal check first
        is_refusal, ref_msg, ref_reason = self.guardrails.check_query_refusal(q)
        if is_refusal:
            return QueryIntent(
                intent_type=IntentType.REFUSAL,
                raw_query=q,
                refusal_reason=ref_reason,
                refusal_message=ref_msg,
                confidence=1.0,
            )

        # Detect filter keywords
        filters: dict[str, Any] = {}
        dimensions: list[str] = []

        if "groww" in q_lower:
            filters["groww_specific"] = True
            dimensions.append("groww_specific")

        if any(w in q_lower for w in ["stop", "stopped", "cancel", "pause", "paused", "drop", "dropper"]):
            filters["outcome"] = "stopped"
            dimensions.append("outcome")
        elif any(w in q_lower for w in ["continue", "continued", "persisted", "continuer", "stay"]):
            filters["outcome"] = "continued"
            dimensions.append("outcome")

        # Lifecycle stage detection
        if any(w in q_lower for w in ["month 0", "first month", "pre-start", "onboarding", "starting"]):
            dimensions.append("lifecycle_stage")
            if "pre-start" in q_lower or "onboarding" in q_lower:
                filters["lifecycle_stage"] = "pre-start"
            elif "month 0" in q_lower or "first month" in q_lower:
                filters["lifecycle_stage"] = "month 0 to 1"
        elif any(w in q_lower for w in ["month 2", "month 3", "months 2 to 3"]):
            dimensions.append("lifecycle_stage")
            filters["lifecycle_stage"] = "months 2 to 3"

        # Demographic / Segment detection
        if any(w in q_lower for w in ["salaried", "freelance", "student", "income"]):
            dimensions.append("income_stability")
        if any(w in q_lower for w in ["age", "young", "retiree", "35+"]):
            dimensions.append("age_band")

        # Theme focus detection
        theme_focus = None
        theme_keywords = {
            "autopay": "autopay_mandate_failure",
            "mandate": "autopay_mandate_failure",
            "kyc": "onboarding_kyc_friction",
            "onboarding": "onboarding_kyc_friction",
            "xirr": "xirr_vs_absolute_confusion",
            "return": "negative_short_term_returns",
            "loss": "negative_short_term_returns",
            "volatility": "market_volatility_panic",
            "crash": "market_volatility_panic",
            "panic": "market_volatility_panic",
            "step up": "step_up_and_increment_rules",
            "increment": "step_up_and_increment_rules",
            "statement": "confusing_statements_and_taxes",
            "tax": "confusing_statements_and_taxes",
            "expense ratio": "confusing_statements_and_taxes",
            "reddit": "seeking_outside_validation",
            "suitability": "capital_safety_fear",
        }
        for kw, th in theme_keywords.items():
            if kw in q_lower:
                theme_focus = th
                break

        # 2. Count Query Detection
        count_patterns = [
            r"\bhow\s+many\b",
            r"\bcount\s+of\b",
            r"\bnumber\s+of\b",
            r"\bwhat\s+percentage\b",
            r"\bwhat\s+proportion\b",
            r"\bwhat\s+share\b",
            r"\bhow\s+often\b",
            r"\bhow\s+common\b",
        ]
        if any(re.search(pat, q_lower) for pat in count_patterns):
            return QueryIntent(
                intent_type=IntentType.COUNT,
                raw_query=q,
                dimensions=dimensions,
                filters=filters,
                theme_focus=theme_focus,
                confidence=0.95,
            )

        # 3. Comparison Query Detection
        comp_patterns = [
            r"\bcompare\b",
            r"\bcomparison\b",
            r"\bdifference\s+between\b",
            r"\bversus\b",
            r"\bvs\.?\b",
            r"\bcontinuer.*dropper\b",
            r"\bdropper.*continuer\b",
        ]
        if any(re.search(pat, q_lower) for pat in comp_patterns):
            dimensions.extend(["continuer_vs_dropper", "outcome"])
            return QueryIntent(
                intent_type=IntentType.COMPARISON,
                raw_query=q,
                dimensions=list(set(dimensions)),
                filters=filters,
                theme_focus=theme_focus,
                confidence=0.95,
            )

        # 4. Drill Down Detection
        drill_patterns = [
            r"\bshow\s+me\s+evidence\b",
            r"\bshow\s+examples?\b",
            r"\bquotes?\s+about\b",
            r"\bverbatim\b",
            r"\bsample\s+reviews?\b",
            r"\bgive\s+me\s+examples?\b",
            r"\bwhat\s+did\s+(?:users|investors)\s+say\b",
            r"\bdrill\s+down\b",
        ]
        if any(re.search(pat, q_lower) for pat in drill_patterns):
            return QueryIntent(
                intent_type=IntentType.DRILL_DOWN,
                raw_query=q,
                dimensions=dimensions,
                filters=filters,
                theme_focus=theme_focus,
                confidence=0.92,
            )

        # 5. Default: Exploration Query
        return QueryIntent(
            intent_type=IntentType.EXPLORATION,
            raw_query=q,
            dimensions=dimensions,
            filters=filters,
            theme_focus=theme_focus,
            confidence=0.85,
        )

