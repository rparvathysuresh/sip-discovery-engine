"""
Play Store collector for Groww app reviews using google-play-scraper.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

try:
    from google_play_scraper import Sort, reviews
except ImportError:
    reviews = None
    Sort = None

from src.collectors.base_collector import BaseCollector, detect_platforms
from src.models.schemas import RawItem, RawItemMetadata, SourceType
from src.utils.logging import get_logger

logger = get_logger(__name__)

DEFAULT_APP_ID = "com.nextbillion.groww"


class PlayStoreCollector(BaseCollector):
    """
    Collects and normalizes public user reviews from the Google Play Store for Groww.
    """

    def __init__(self, config: Optional[dict[str, Any]] = None):
        super().__init__(config)
        self.app_id = self.config.get("app_id", DEFAULT_APP_ID)
        self.lang = self.config.get("lang", "en")
        self.country = self.config.get("country", "in")
        self.max_reviews = self.config.get("max_reviews", 2000)
        self.filter_ratings = self.config.get("filter_ratings", [1, 2, 3, 4, 5])

    def get_source_name(self) -> str:
        return "playstore"

    @property
    def source_type(self) -> SourceType:
        return SourceType.PLAYSTORE

    def collect_snapshot(self, limit: Optional[int] = None) -> list[RawItem]:
        """
        Fetch reviews from Google Play Store for Groww and normalize to RawItem records.
        
        Args:
            limit: Maximum reviews to fetch (defaults to config max_reviews).
            
        Returns:
            List of normalized RawItem objects.
        """
        target_count = limit or self.max_reviews
        items: list[RawItem] = []
        seen_review_ids: set[str] = set()

        if reviews is None:
            self.logger.error("google-play-scraper is not installed in the environment.")
            return items

        self.logger.info(
            "Starting Play Store collection for app=%s (lang=%s, country=%s, target=%d)",
            self.app_id, self.lang, self.country, target_count
        )

        # Multi-rating strategy for large target counts: sample balanced across star ratings
        if target_count > 100 and self.filter_ratings:
            per_rating_target = max(50, target_count // len(self.filter_ratings))
            for score in self.filter_ratings:
                if len(items) >= target_count:
                    break
                rating_items = 0
                continuation_token = None
                while rating_items < per_rating_target and len(items) < target_count:
                    fetch_count = min(200, per_rating_target - rating_items)
                    try:
                        result, continuation_token = reviews(
                            self.app_id,
                            lang=self.lang,
                            country=self.country,
                            sort=Sort.MOST_RELEVANT if Sort else 1,
                            filter_score_with=score,
                            count=fetch_count,
                            continuation_token=continuation_token,
                        )
                    except Exception as e:
                        self.logger.warning("Error fetching score=%d reviews: %s", score, e)
                        break

                    if not result:
                        break

                    for rev in result:
                        text = (rev.get("content") or "").strip()
                        if not text:
                            continue
                        rev_id = str(rev.get("reviewId", ""))
                        if rev_id in seen_review_ids:
                            continue
                        seen_review_ids.add(rev_id)

                        item = self._normalize_review(rev, text)
                        items.append(item)
                        rating_items += 1
                        if len(items) >= target_count:
                            break

                    if not continuation_token:
                        break
                    self.respect_rate_limit(0.3)

            self.logger.info(
                "Play Store multi-rating collection complete: %d items gathered across scores %s",
                len(items), self.filter_ratings
            )

        # Fallback or top-up using standard newest pagination
        if len(items) < target_count:
            batch_size = min(200, target_count - len(items))
            continuation_token = None
            while len(items) < target_count:
                fetch_count = min(batch_size, target_count - len(items))
                try:
                    result, continuation_token = reviews(
                        self.app_id,
                        lang=self.lang,
                        country=self.country,
                        sort=Sort.NEWEST if Sort else 2,
                        count=fetch_count,
                        continuation_token=continuation_token,
                    )
                except Exception as e:
                    self.logger.warning("Error in Play Store top-up pagination: %s", e)
                    break

                if not result:
                    break

                for rev in result:
                    text = (rev.get("content") or "").strip()
                    if not text:
                        continue
                    rev_id = str(rev.get("reviewId", ""))
                    if rev_id in seen_review_ids:
                        continue
                    seen_review_ids.add(rev_id)

                    item = self._normalize_review(rev, text)
                    items.append(item)
                    if len(items) >= target_count:
                        break

                if not continuation_token:
                    break
                self.respect_rate_limit(0.3)

        self.logger.info("Play Store collection completed: %d items collected", len(items))
        return items

    def _normalize_review(self, rev: dict[str, Any], text: str) -> RawItem:
        review_id = str(rev.get("reviewId", ""))
        published_at = rev.get("at")
        if isinstance(published_at, datetime) and published_at.tzinfo is None:
            published_at = published_at.replace(tzinfo=timezone.utc)

        rating = rev.get("score")
        platforms = detect_platforms(text)
        if "groww" not in platforms:
            platforms.append("groww")

        return RawItem(
            source=SourceType.PLAYSTORE,
            source_native_id=review_id,
            source_url=f"https://play.google.com/store/apps/details?id={self.app_id}&reviewId={review_id}",
            platform_mentioned=platforms,
            published_at=published_at,
            text=text,
            language_detected=self.lang,
            metadata=RawItemMetadata(
                rating=rating,
                extra={
                    "thumbs_up": rev.get("thumbsUpCount", 0),
                    "app_version": rev.get("reviewCreatedVersion"),
                    "reply_content": rev.get("replyContent"),
                },
            ),
        )

