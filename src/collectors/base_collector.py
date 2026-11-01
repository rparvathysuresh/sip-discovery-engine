"""
Base collector interface and common utilities for all data source collectors.
"""

from __future__ import annotations

import abc
import re
import time
from typing import Any, Optional

from src.models.schemas import RawItem, SourceType
from src.utils.logging import get_logger

logger = get_logger(__name__)

# Known mutual fund and discount broker platforms for platform tagging
KNOWN_PLATFORMS = {
    "groww": ["groww"],
    "zerodha": ["zerodha", "coin"],
    "kuvera": ["kuvera"],
    "etmoney": ["etmoney", "et money"],
    "paytm_money": ["paytm money", "paytmmoney"],
    "indmoney": ["indmoney", "ind money"],
    "angelone": ["angelone", "angel one", "angel broking"],
    "upstox": ["upstox"],
}


def detect_platforms(text: str) -> list[str]:
    """
    Detect financial platforms mentioned in the given text.
    
    Args:
        text: Input review or post text.
        
    Returns:
        List of platform keys detected (e.g. ['groww', 'zerodha']).
    """
    text_lower = text.lower()
    mentioned: list[str] = []
    for platform_key, variations in KNOWN_PLATFORMS.items():
        for var in variations:
            # Word boundary matching to avoid partial substring false positives
            if re.search(r"\b" + re.escape(var) + r"\b", text_lower):
                if platform_key not in mentioned:
                    mentioned.append(platform_key)
                break
    return mentioned


class BaseCollector(abc.ABC):
    """
    Abstract base class for all one-time snapshot collectors.
    
    All source-specific collectors (Play Store, App Store, Reddit, etc.)
    must inherit from this class and implement the abstract methods.
    """

    def __init__(self, config: Optional[dict[str, Any]] = None):
        """
        Initialize the collector with an optional source configuration dictionary.
        
        Args:
            config: Source-specific configuration dict from sources.yaml
        """
        self.config = config or {}
        self.logger = get_logger(f"{__name__}.{self.get_source_name()}")

    @abc.abstractmethod
    def get_source_name(self) -> str:
        """Return the string identifier for this source (e.g. 'playstore', 'reddit')."""
        pass

    @property
    @abc.abstractmethod
    def source_type(self) -> SourceType:
        """Return the SourceType enum for this collector."""
        pass

    @abc.abstractmethod
    def collect_snapshot(self, limit: Optional[int] = None) -> list[RawItem]:
        """
        Execute a one-time snapshot collection of public conversations.
        
        Args:
            limit: Optional maximum number of items to collect.
            
        Returns:
            List of normalized RawItem objects.
        """
        pass

    def respect_rate_limit(self, delay_seconds: float = 1.0) -> None:
        """
        Sleep for the specified delay to adhere to source rate limits.
        
        Args:
            delay_seconds: Seconds to sleep (default 1.0s).
        """
        if delay_seconds > 0:
            time.sleep(delay_seconds)

