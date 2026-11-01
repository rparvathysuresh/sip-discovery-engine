"""
src/preprocessing/groww_tagger.py — Platform tagging and competitor filtering.

Tags items as groww_specific (true/false) and detects competitor-only content
(e.g., Zerodha/Coin/Kuvera platform-specific issues without general SIP relevance).
"""

from __future__ import annotations

import re
from typing import Any

from src.collectors.base_collector import detect_platforms
from src.models.schemas import RawItem, SourceType
from src.utils.logging import get_logger

logger = get_logger(__name__)

COMPETITORS = {
    "zerodha",
    "coin",
    "kuvera",
    "etmoney",
    "paytmmoney",
    "angelone",
    "upstox",
    "dhan",
}

# Regex to detect competitor-specific technical bugs/complaints
COMPETITOR_SPECIFIC_ISSUE_REGEX = re.compile(
    r"\b(?:kite\s*app|coin\s*portal|zerodha\s*support|kuvera\s*login|etmoney\s*genius|dhan\s*account)\b",
    re.IGNORECASE,
)


class GrowwTagger:
    """
    Tags records as Groww-specific or platform-agnostic, and filters out competitor-only noise.
    """

    def __init__(self, exclude_competitor_only: bool = True):
        self.exclude_competitor_only = exclude_competitor_only
        self.stats = {
            "total_processed": 0,
            "groww_specific": 0,
            "platform_agnostic": 0,
            "competitor_only_excluded": 0,
        }

    def tag_item(self, item: RawItem) -> tuple[bool, bool, list[str]]:
        """
        Analyze item platform relevance.

        Returns:
            (groww_specific, is_competitor_only, platforms_mentioned)
        """
        self.stats["total_processed"] += 1
        text_lower = item.text.lower()
        platforms = set(detect_platforms(item.text))
        if item.platform_mentioned:
            platforms.update(item.platform_mentioned)

        # App Store and Play Store reviews are inherently Groww-specific
        if item.source in (SourceType.PLAYSTORE, SourceType.APPSTORE):
            platforms.add("groww")

        mentions_groww = "groww" in platforms or "groww" in text_lower
        competitor_mentions = {p for p in platforms if p in COMPETITORS}

        groww_specific = mentions_groww

        # Competitor-only condition: mentions competitors, doesn't mention Groww,
        # and has competitor-specific technical/operational references
        is_competitor_only = False
        if competitor_mentions and not mentions_groww:
            has_comp_issue = bool(COMPETITOR_SPECIFIC_ISSUE_REGEX.search(text_lower))
            # If purely about competitor with no general SIP mechanics, exclude
            if has_comp_issue or (len(competitor_mentions) > 0 and "sip" not in text_lower):
                is_competitor_only = True

        if is_competitor_only and self.exclude_competitor_only:
            self.stats["competitor_only_excluded"] += 1
        elif groww_specific:
            self.stats["groww_specific"] += 1
        else:
            self.stats["platform_agnostic"] += 1

        return groww_specific, is_competitor_only, sorted(platforms)

    def process_items(
        self, items: list[RawItem]
    ) -> tuple[list[RawItem], list[dict[str, Any]]]:
        """
        Tag items with groww_specific in metadata, filtering out competitor-only items.

        Returns:
            (retained_items, rejected_records)
        """
        retained: list[RawItem] = []
        rejected: list[dict[str, Any]] = []

        for item in items:
            groww_spec, comp_only, platforms = self.tag_item(item)
            if comp_only and self.exclude_competitor_only:
                rejected.append({
                    "raw_id": item.raw_id,
                    "reason": "competitor_only",
                    "platforms": platforms,
                    "source": item.source.value,
                    "preview": item.text[:60],
                })
            else:
                # Store tags in item metadata
                item_dict = item.model_dump()
                item_dict["platform_mentioned"] = platforms
                if not item_dict.get("metadata"):
                    item_dict["metadata"] = {}
                if "extra" not in item_dict["metadata"] or item_dict["metadata"]["extra"] is None:
                    item_dict["metadata"]["extra"] = {}
                item_dict["metadata"]["extra"]["groww_specific"] = groww_spec

                retained.append(RawItem(**item_dict))

        return retained, rejected

