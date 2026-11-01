"""
App Store collector for Groww iOS app reviews using the Apple iTunes Customer Reviews JSON API.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

import requests

from src.collectors.base_collector import BaseCollector, detect_platforms
from src.models.schemas import RawItem, RawItemMetadata, SourceType
from src.utils.logging import get_logger

logger = get_logger(__name__)

DEFAULT_APP_ID = 1404871703  # Groww iOS app ID
DEFAULT_COUNTRY = "in"


class AppStoreCollector(BaseCollector):
    """
    Collects and normalizes public user reviews from the Apple App Store for Groww.
    """

    def __init__(self, config: Optional[dict[str, Any]] = None):
        super().__init__(config)
        self.app_id = self.config.get("app_id", DEFAULT_APP_ID)
        self.country = self.config.get("country", DEFAULT_COUNTRY)
        self.max_reviews = self.config.get("max_reviews", 500)

    def get_source_name(self) -> str:
        return "appstore"

    @property
    def source_type(self) -> SourceType:
        return SourceType.APPSTORE

    def collect_snapshot(self, limit: Optional[int] = None) -> list[RawItem]:
        """
        Fetch reviews from the Apple iTunes Customer Reviews RSS feed.
        
        Args:
            limit: Maximum reviews to fetch (defaults to config max_reviews, max 500).
            
        Returns:
            List of normalized RawItem objects.
        """
        target_count = limit or self.max_reviews
        items: list[RawItem] = []

        self.logger.info(
            "Starting App Store collection for app_id=%s (country=%s, target=%d)",
            self.app_id, self.country, target_count
        )

        # Apple iTunes RSS pagination: max 10 pages supported by Apple
        page = 1
        max_pages = 10

        while page <= max_pages and len(items) < target_count:
            url = f"https://itunes.apple.com/{self.country}/rss/customerreviews/page={page}/id={self.app_id}/sortBy=mostRecent/json"
            try:
                resp = requests.get(url, timeout=10)
                if resp.status_code != 200:
                    self.logger.warning(
                        "App Store RSS returned status %d on page %d", resp.status_code, page
                    )
                    break

                data = resp.json()
                feed = data.get("feed", {})
                entries = feed.get("entry", [])

                if not entries:
                    self.logger.info("No more reviews found on App Store page %d", page)
                    break

                for entry in entries:
                    # The first entry in the feed is often metadata for the app itself, not a review
                    if "im:rating" not in entry:
                        continue

                    review_id = str(entry.get("id", {}).get("label", ""))
                    title = entry.get("title", {}).get("label", "").strip()
                    content = entry.get("content", {}).get("label", "").strip()

                    text = f"{title}. {content}".strip() if title else content
                    if not text:
                        continue

                    rating_str = entry.get("im:rating", {}).get("label", "0")
                    rating = int(rating_str) if rating_str.isdigit() else None
                    version = entry.get("im:version", {}).get("label")

                    updated_str = entry.get("updated", {}).get("label")
                    published_at = None
                    if updated_str:
                        try:
                            published_at = datetime.fromisoformat(updated_str.replace("Z", "+00:00"))
                        except Exception:
                            published_at = None

                    platforms = detect_platforms(text)
                    if "groww" not in platforms:
                        # Reviews on Groww's App Store page inherently discuss Groww context
                        platforms.append("groww")

                    item = RawItem(
                        source=SourceType.APPSTORE,
                        source_native_id=review_id,
                        source_url=f"https://apps.apple.com/{self.country}/app/groww/id{self.app_id}",
                        platform_mentioned=platforms,
                        published_at=published_at,
                        text=text,
                        language_detected="en",
                        metadata=RawItemMetadata(
                            rating=rating,
                            thread_title=title,
                            extra={"app_version": version},
                        ),
                    )
                    items.append(item)
                    if len(items) >= target_count:
                        break

                self.logger.info("Fetched page %d (total items collected: %d)", page, len(items))
                page += 1
                self.respect_rate_limit(0.5)

            except Exception as e:
                self.logger.warning("Error fetching App Store page %d: %s", page, e)
                break

        self.logger.info("App Store collection completed: %d items collected", len(items))
        return items
