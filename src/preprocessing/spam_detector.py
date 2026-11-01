"""
src/preprocessing/spam_detector.py — Heuristic spam and low-quality filter.

Filters out promotional bot messages, referral code spam, Telegram/WhatsApp groups,
excessive character repetition, gibberish, and uninformative low-content items.
"""

from __future__ import annotations

import html
import re
from typing import Any, Optional

from src.models.schemas import RawItem
from src.utils.logging import get_logger

logger = get_logger(__name__)

# Promotional & spam patterns
PROMO_PATTERNS = [
    re.compile(r"\b(?:join|subscribe)\b.*?\b(?:telegram|tg\s*channel|whatsapp|wa\s*group)\b", re.IGNORECASE),
    re.compile(r"\b(?:referral\s*code|invite\s*code|promo\s*code|use\s*my\s*code)\b", re.IGNORECASE),
    re.compile(r"\b(?:guaranteed\s*returns|100%\s*profit|jackpot\s*tips|calls\s*and\s*tips)\b", re.IGNORECASE),
    re.compile(r"\b(?:crypto\s*airdrop|binance\s*giveaway|forex\s*trading\s*bot)\b", re.IGNORECASE),
    re.compile(r"\b(?:earn\s*\$?\d+\s*daily|work\s*from\s*home\s*part\s*time)\b", re.IGNORECASE),
]

# Character repetition like "faaaaail", "scaaaam", "growwwwww"
REPETITION_REGEX = re.compile(r"(.)\1{5,}")


class SpamDetector:
    """
    Detects low-information, bot-generated, or promotional spam items.
    """

    def __init__(self, min_text_length: int = 30, max_text_length: int = 15000):
        self.min_text_length = min_text_length
        self.max_text_length = max_text_length
        self.stats = {
            "total_checked": 0,
            "spam_detected": 0,
            "passed": 0,
            "by_reason": {},
        }

    def check_spam(self, text: str) -> tuple[bool, Optional[str]]:
        """
        Check if the text is spam or noise.

        Returns:
            (is_spam, reason)
        """
        self.stats["total_checked"] += 1
        stripped = text.strip()

        # 1. Length checks
        if len(stripped) < self.min_text_length:
            return self._record_spam("too_short")
        if len(stripped) > self.max_text_length:
            return self._record_spam("too_long")

        # 2. Promotional / Scam keywords
        for pattern in PROMO_PATTERNS:
            if pattern.search(stripped):
                return self._record_spam("promo_or_referral")

        # 3. Excessive character repetition (e.g., 'scaaaaaaaam')
        if REPETITION_REGEX.search(stripped):
            return self._record_spam("excessive_character_repetition")

        # 4. Low alpha content ratio (e.g. only emojis or punctuation)
        alpha_count = sum(c.isalpha() for c in stripped)
        if len(stripped) > 0 and (alpha_count / len(stripped)) < 0.30:
            return self._record_spam("low_alpha_content")

        # 5. Generic one-word or uninformative short reviews (e.g. 'worst app ever', 'great app for sip')
        words = stripped.split()
        substantive_clues = (
            "cancel", "pause", "stop", "deduct", "mandate", "nav", "unit", "kyc",
            "charge", "fee", "penalty", "fail", "delay", "return", "loss", "bank",
            "error", "stuck", "folio", "amc", "elss", "redeem", "tax", "bounced",
            "autopay", "withdraw", "deposit", "crash", "glitch", "invest"
        )
        if len(words) <= 4 and not any(k in stripped.lower() for k in substantive_clues):
            return self._record_spam("uninformative_generic_short")

        self.stats["passed"] += 1
        return False, None

    def _record_spam(self, reason: str) -> tuple[bool, str]:
        self.stats["spam_detected"] += 1
        self.stats["by_reason"][reason] = self.stats["by_reason"].get(reason, 0) + 1
        return True, reason

    def process_items(
        self, items: list[RawItem]
    ) -> tuple[list[RawItem], list[dict[str, Any]]]:
        """
        Filter a batch of RawItems, retaining non-spam. Normalizes HTML/entities on retained items.

        Returns:
            (retained_items, rejected_records)
        """
        retained: list[RawItem] = []
        rejected: list[dict[str, Any]] = []

        for item in items:
            is_spam, reason = self.check_spam(item.text)
            if is_spam:
                rejected.append({
                    "raw_id": item.raw_id,
                    "reason": f"spam_{reason}",
                    "source": item.source.value,
                    "preview": item.text[:60],
                })
            else:
                # Normalize HTML entities and residual markup
                clean_text = html.unescape(item.text)
                clean_text = re.sub(r"<[^>]+>", " ", clean_text)
                clean_text = re.sub(r"[ \t]+", " ", clean_text).strip()
                item.text = clean_text
                retained.append(item)

        return retained, rejected

