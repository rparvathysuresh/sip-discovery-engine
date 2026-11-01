"""
src/preprocessing/relevance_classifier.py — Zero-shot relevance filter.

Determines whether an item is relevant to mutual fund SIP investing,
retention, barriers, or app user experiences. Uses a fast-path heuristic
combined with Groq zero-shot LLM classification for ambiguous content.
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional

from src.models.schemas import RawItem
from src.utils.groq_client import GroqClient
from src.utils.logging import get_logger

logger = get_logger(__name__)

# High-confidence positive SIP/mutual fund domain keywords
SIP_KEYWORDS = [
    r"\bsip\b",
    r"\bsips\b",
    r"\bmutual\s*funds?\b",
    r"\bindex\s*funds?\b",
    r"\bflexi\s*cap\b",
    r"\bsmall\s*cap\b",
    r"\bmid\s*cap\b",
    r"\blarge\s*cap\b",
    r"\bfolio\b",
    r"\bautopay\b",
    r"\bmandate\b",
    r"\bnach\b",
    r"\bamc\b",
    r"\bnav\b",
    r"\bxirr\b",
    r"\bcagr\b",
    r"\blumpsum\b",
    r"\bdisinvest\b",
    r"\bredeem\b",
    r"\bexit\s*load\b",
    r"\block[- ]?in\b",
    r"\bportfolio\b",
    r"\bnominee\b",
    r"\bnominate\b",
    r"\basset\s*allocation\b",
    r"\bstep\s*up\b",
    r"\belss\b",
    r"\bmf\s*central\b",
    r"\bppfas\b",
    r"\bparag\s*parikh\b",
    r"\bnippon\b",
]

# Irrelevant domain keywords (intraday trading, pure options/crypto)
EXCLUDE_KEYWORDS = [
    r"\bintraday\b",
    r"\bf&o\b",
    r"\bfutures?\s*(?:and|&)?\s*options?\b",
    r"\boptions?\s+trading\b",
    r"\boption\s+chain\b",
    r"\boption\s+buyer\b",
    r"\boption\s+trading\b",
    r"\bcall\s+(?:and|&)?\s*put\b",
    r"\bcall\s+option\b",
    r"\bput\s+option\b",
    r"\bce\s*/\s*pe\b",
    r"\bstrike\s*price\b",
    r"\bnifty\s*options?\b",
    r"\bbank\s*nifty\b",
    r"\bscalping\b",
    r"\btrading\s*view\b",
    r"\bcandlestick\b",
    r"\bcandle\s*chart\b",
    r"\bstop\s*loss\s*(?:trailing|trigger)?\b",
    r"\bbracket\s*order\b",
    r"\bcover\s*order\b",
    r"\bforex\b",
    r"\bcrypto\b",
    r"\bbitcoin\b",
    r"\bbinance\b",
    r"\busdt\b",
    r"\b1\s*lot\b",
    r"\bbasket\s*order\b",
    r"\bspot-based\s*trigger\b",
]

SIP_PATTERN = re.compile("|".join(SIP_KEYWORDS), re.IGNORECASE)
EXCLUDE_PATTERN = re.compile("|".join(EXCLUDE_KEYWORDS), re.IGNORECASE)


FINANCIAL_OPERATIONAL_TERMS = (
    "sip", "mutual fund", "fund", "funds", "folio", "mandate", "autopay",
    "nav", "unit", "units", "redeem", "redemption", "amc", "cams", "kfintech",
    "kyc", "bank", "deduct", "deducted", "deduction", "deposit", "withdraw",
    "withdrawal", "charges", "fee", "penalty", "tax", "stcg", "ltcg", "elss",
    "step up", "step-up", "portfolio", "returns", "return", "investment",
    "invest", "investing", "investor", "demat", "bounced", "bounce", "ecs", "nach",
    "money", "payment", "loss", "profit",
)


class RelevanceClassifier:
    """
    Classifies whether raw items are relevant to SIP / mutual fund retention analysis.
    """

    def __init__(self, groq_client: Optional[GroqClient] = None, use_llm: bool = True):
        self.groq_client = groq_client
        self.use_llm = use_llm
        self.stats = {
            "total_checked": 0,
            "relevant": 0,
            "irrelevant": 0,
            "heuristic_passed": 0,
            "llm_evaluated": 0,
        }

    def _get_groq_client(self) -> Optional[GroqClient]:
        """Lazy load GroqClient if not provided and LLM is enabled."""
        if not self.use_llm:
            return None
        if self.groq_client is None:
            try:
                self.groq_client = GroqClient()
            except Exception as e:
                logger.warning("Could not initialize GroqClient for relevance check: %s. Using heuristics.", e)
                self.use_llm = False
                return None
        return self.groq_client

    def classify(self, text: str, source: Optional[Any] = None) -> tuple[bool, float, str]:
        """
        Evaluate relevance of text to mutual fund SIP discovery.

        Returns:
            (is_relevant, confidence, reason)
        """
        self.stats["total_checked"] += 1
        clean = text.lower()

        has_sip = bool(SIP_PATTERN.search(clean))
        has_exclude = bool(EXCLUDE_PATTERN.search(clean))

        # Fast path 1: Clear positive (has SIP keywords, no exclude keywords)
        if has_sip and not has_exclude:
            self.stats["relevant"] += 1
            self.stats["heuristic_passed"] += 1
            return True, 0.95, "heuristic_sip_keyword_match"

        # Fast path 2: Pure trading/crypto without any SIP mention
        if has_exclude and not has_sip:
            self.stats["irrelevant"] += 1
            return False, 0.90, "heuristic_pure_trading_or_crypto"

        # Fast path 3: App store reviews on Groww or explicit Groww mentions
        src_val = str(source.value if hasattr(source, "value") else source).lower() if source else ""
        is_groww_source = src_val in ("playstore", "appstore")
        if (is_groww_source or "groww" in clean) and any(term in clean for term in FINANCIAL_OPERATIONAL_TERMS):
            self.stats["relevant"] += 1
            self.stats["heuristic_passed"] += 1
            return True, 0.85, "heuristic_groww_investment_match"

        # Ambiguous items: evaluate with LLM if client available
        client = self._get_groq_client()
        if client:
            try:
                self.stats["llm_evaluated"] += 1
                prompt = (
                    "You are a relevance classifier for a research project on Indian Mutual Fund SIP (Systematic Investment Plan) "
                    "investors and their behavioral retention/churn.\n\n"
                    "Determine if the following text is RELEVANT (true) or IRRELEVANT (false).\n"
                    "Text must relate to mutual funds, SIPs, personal investment journeys, fund selection, app experience, or financial anxiety.\n"
                    "Items strictly about options/intraday trading, crypto, or unrelated app tech issues are IRRELEVANT.\n\n"
                    f"Text: \"{text[:1000]}\"\n\n"
                    "Respond with ONLY a JSON object: {\"relevant\": boolean, \"confidence\": float (0.0 to 1.0), \"reason\": string}"
                )
                res = client.chat_completion(
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=100,
                    response_format="json_object",
                )
                parsed = json.loads(res["content"])
                is_rel = bool(parsed.get("relevant", False))
                conf = float(parsed.get("confidence", 0.7))
                reason = str(parsed.get("reason", "llm_classified"))

                if is_rel:
                    self.stats["relevant"] += 1
                else:
                    self.stats["irrelevant"] += 1
                return is_rel, conf, f"llm_{reason}"

            except Exception as e:
                logger.debug("LLM relevance evaluation failed (%s). Falling back to heuristic decision.", e)

        # Fallback decision if LLM unavailable
        is_rel = has_sip
        conf = 0.60
        reason = "heuristic_fallback"
        if is_rel:
            self.stats["relevant"] += 1
        else:
            self.stats["irrelevant"] += 1
        return is_rel, conf, reason

    def process_items(
        self, items: list[RawItem]
    ) -> tuple[list[RawItem], list[dict[str, Any]]]:
        """
        Filter RawItems by relevance.

        Returns:
            (retained_items, rejected_records)
        """
        retained: list[RawItem] = []
        rejected: list[dict[str, Any]] = []

        for item in items:
            is_rel, conf, reason = self.classify(item.text, source=item.source)
            if is_rel:
                retained.append(item)
            else:
                rejected.append({
                    "raw_id": item.raw_id,
                    "reason": f"irrelevant_{reason}",
                    "confidence": conf,
                    "source": item.source.value,
                    "preview": item.text[:60],
                })

        return retained, rejected

