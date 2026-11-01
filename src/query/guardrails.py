"""
Guardrails and boundary enforcement for the SIP Discovery Engine.

Enforces:
1. Rejection of investment advice / specific fund recommendations
2. Blocking of competitor comparisons (e.g. Groww vs Zerodha)
3. Blocking of FOMO / urgency framing
4. Evidence threshold labeling (sufficient vs directional vs insufficient)
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional

import yaml

from src.utils.logging import get_logger

logger = get_logger(__name__)

DEFAULT_GUARDRAILS_CONFIG = Path("config/guardrails.yaml")


class GuardrailsChecker:
    """
    Validates user queries and synthesized responses against compliance and safety guardrails.
    """

    def __init__(self, config_path: Optional[Path | str] = None):
        self.config_path = Path(config_path or DEFAULT_GUARDRAILS_CONFIG)
        self.investment_advice_keywords: list[str] = [
            "which fund to buy",
            "which fund should i",
            "which mutual fund should i invest in",
            "best mutual fund",
            "best sip",
            "recommend a fund",
            "should i invest in",
            "target price",
            "future return prediction",
            "which stock to buy",
            "suggest some funds",
            "where should i put my money",
        ]
        self.competitor_comparison_keywords: list[str] = [
            "groww vs zerodha",
            "zerodha vs groww",
            "groww vs angel",
            "groww vs coin",
            "which broker is better",
            "is zerodha better than groww",
        ]
        self.fomo_phrases: list[str] = [
            "invest now or miss out",
            "invest now or you'll miss out",
            "don't miss this opportunity",
            "market crash incoming",
            "guaranteed returns",
            "foolproof strategy",
            "quick rich",
            "act fast before it's too late",
        ]
        self.default_refusal_message = (
            "I'm designed to surface research findings about investor behavior, not to recommend specific "
            "funds or investments. Based on the corpus, I can help you understand reasons first-time investors "
            "pause or stop their SIPs. Would you like to explore that?"
        )
        self.load_config(self.config_path)

    def load_config(self, path: Path | str) -> None:
        """Load guardrail patterns from YAML."""
        p = Path(path)
        if p.is_file():
            with open(p, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}

            adv = data.get("investment_advice", {})
            if "trigger_keywords" in adv:
                self.investment_advice_keywords = adv["trigger_keywords"]
            if "refusal_message" in adv:
                self.default_refusal_message = adv["refusal_message"]

            tone = data.get("tone_and_framing", {})
            if "forbidden_phrases" in tone:
                for phrase in tone["forbidden_phrases"]:
                    if phrase not in self.fomo_phrases:
                        self.fomo_phrases.append(phrase)

            logger.info("Loaded guardrails config from %s", p)

    def check_query_refusal(self, query: str) -> tuple[bool, Optional[str], str]:
        """
        Check if an incoming user query should be refused.

        Returns:
            (is_refusal: bool, refusal_message: Optional[str], reason: str)
        """
        q_clean = query.strip().lower()

        # 1. Direct fund advice & portfolio recommendation request
        for kw in self.investment_advice_keywords:
            if kw.lower() in q_clean:
                return True, self.default_refusal_message, "investment_advice"

        # Regex check for variations: "which (mutual fund|fund|sip) should i (buy|invest|choose)"
        if re.search(r"\bwhich\s+(?:mutual\s+fund|fund|sip|stocks?)\s+should\s+i\b", q_clean):
            return True, self.default_refusal_message, "investment_advice"

        if re.search(r"\bshould\s+i\s+(?:buy|invest\s+in|choose|pick)\b", q_clean):
            return True, self.default_refusal_message, "investment_advice"

        if re.search(r"\b(?:best|top)\s+(?:[\w\s]{0,40})?(?:funds?|sips?|stocks?)\b", q_clean):
            return True, self.default_refusal_message, "investment_advice"

        if re.search(r"\b(?:recommend|suggest)\s+(?:me\s+)?(?:\d+\s+)?(?:[\w\s]{0,40})?(?:funds?|sips?|stocks?)\b", q_clean):
            return True, self.default_refusal_message, "investment_advice"

        if re.search(r"\b(?:manage\s+my\s+(?:investment\s+)?portfolio|trading\s+tips|stock\s+tips)\b", q_clean):
            return True, self.default_refusal_message, "investment_advice"

        if re.search(r"\bguarantee\b.*\breturn", q_clean):
            return True, self.default_refusal_message, "investment_advice"

        # 2. Competitor head-to-head comparison
        for kw in self.competitor_comparison_keywords:
            if kw.lower() in q_clean:
                msg = (
                    "I cannot provide head-to-head competitor platform comparisons (e.g. Groww vs Zerodha). "
                    "I can, however, provide insights into platform-agnostic SIP behavioral patterns or Groww-specific "
                    "user feedback from our research corpus."
                )
                return True, msg, "competitor_comparison"

        platforms = r"(?:groww|zerodha|coin|angel|upstox|kuvera|paytm|indmoney)"
        if re.search(rf"\b{platforms}\s+vs\s+\w+\b", q_clean) or re.search(rf"\b\w+\s+vs\s+{platforms}\b", q_clean):
            msg = (
                "I cannot provide head-to-head competitor platform comparisons. I can only surface "
                "behavioral insights from public SIP investor discussions in our corpus."
            )
            return True, msg, "competitor_comparison"

        if re.search(rf"\b(?:is\s+)?{platforms}\s+better\s+than\b", q_clean):
            return True, "I cannot provide head-to-head competitor platform comparisons.", "competitor_comparison"

        if re.search(rf"\bswitch\s+(?:from\s+{platforms}\s+to|to\s+{platforms}\s+from)\b", q_clean):
            return True, "I cannot provide head-to-head competitor platform comparisons.", "competitor_comparison"

        if re.search(r"\brank\b.*\b(?:brokers?|platforms?|apps?)\b", q_clean):
            return True, "I cannot rank or compare broker platforms.", "competitor_comparison"

        # 3. FOMO / predatory urgency framing in query
        for phrase in self.fomo_phrases:
            if phrase.lower() in q_clean:
                msg = (
                    "This system adheres to strict neutrality guardrails and blocks FOMO, panic, "
                    "or urgency framing. All insights reflect historical public feedback without promotional bias."
                )
                return True, msg, "fomo_framing"

        if (
            re.search(r"\binvest\s+now\s+or\s+(?:you(?:'ll|\s+will)\s+)?miss\s+out\b", q_clean)
            or re.search(r"\b(?:hurry\s+up|double\s+your\s+money|don'?t\s+miss\s+out)\b", q_clean)
            or re.search(r"\bbefore\s+(?:market\s+reaches|it'?s\s+too\s+late)\b", q_clean)
        ):
            msg = (
                "This system adheres to strict neutrality guardrails and blocks FOMO, panic, "
                "or urgency framing. All insights reflect historical public feedback without promotional bias."
            )
            return True, msg, "fomo_framing"

        return False, None, "allowed"

    def sanitize_response(self, text: str) -> str:
        """
        Scan and sanitize outbound synthesized response to ensure no FOMO phrasing escapes.
        """
        sanitized = text
        for phrase in self.fomo_phrases:
            pattern = re.compile(re.escape(phrase), re.IGNORECASE)
            sanitized = pattern.sub("[neutral framing required]", sanitized)

        sanitized = re.sub(
            r"\binvest\s+now\s+or\s+(?:you(?:'ll|\s+will)\s+)?miss\s+out\b",
            "[neutral framing required]",
            sanitized,
            flags=re.IGNORECASE,
        )

        # Check for direct recommendation statements
        adv_patterns = [
            r"\byou should invest in\s+[A-Z][a-zA-Z0-9\s]+fund\b",
            r"\bi recommend buying\s+[A-Z][a-zA-Z0-9\s]+fund\b",
        ]
        for p in adv_patterns:
            sanitized = re.sub(p, "[recommendation removed per compliance rules]", sanitized, flags=re.IGNORECASE)

        return sanitized

    def get_evidence_level(self, n: int, num_sources: int = 1) -> str:
        """Assign evidence tier string."""
        if n >= 30 and num_sources >= 2:
            return "sufficient"
        elif n >= 10 or num_sources >= 1:
            return "directional"
        else:
            return "insufficient"

