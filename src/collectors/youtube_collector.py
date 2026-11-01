"""
YouTube collector for SIP and mutual fund video comments.
Uses YouTube Data API v3 (REST endpoints) to fetch video comments on SIP explainer and review videos.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import requests

from src.collectors.base_collector import BaseCollector, detect_platforms
from src.models.schemas import RawItem, RawItemMetadata, SourceType
from src.utils.logging import get_logger

logger = get_logger(__name__)

YOUTUBE_API_BASE_URL = "https://www.googleapis.com/youtube/v3"

DEFAULT_QUERIES = [
    "SIP returns India",
    "SIP not working",
    "first mutual fund SIP",
    "Groww SIP review",
    "why stop SIP",
    "mutual fund beginner mistakes",
]


class YouTubeCollector(BaseCollector):
    """
    Collects qualitative comments and investor questions from YouTube videos
    addressing mutual funds and SIPs in India.
    """

    def __init__(self, config: Optional[dict[str, Any]] = None):
        super().__init__(config)
        self.api_key = self.config.get("api_key") or ""
        self.search_queries = self.config.get("search_queries", DEFAULT_QUERIES)
        self.max_videos_per_query = self.config.get("max_videos_per_query", 5)
        self.max_comments_per_video = self.config.get("max_comments_per_video", 50)
        self.raw_dir = Path(self.config.get("raw_dir", "youtube_raw"))
        self.raw_file = Path(self.config.get("raw_file", "youtube_raw/youtube_raw.txt"))

    def get_source_name(self) -> str:
        return "youtube"

    @property
    def source_type(self) -> SourceType:
        return SourceType.YOUTUBE

    def collect_snapshot(self, limit: Optional[int] = None) -> list[RawItem]:
        """
        Collect comments from YouTube videos matching SIP search queries.
        
        Args:
            limit: Maximum number of RawItem comments to collect.
            
        Returns:
            List of normalized RawItem records.
        """
        target_count = limit or 500

        if not self.api_key:
            self.logger.warning(
                "YouTube API key not found in configuration or environment. Checking local dump."
            )
            return self._collect_from_local_dump(target_count)

        return self._collect_from_api(target_count)

    def _collect_from_api(self, target_count: int) -> list[RawItem]:
        """
        Fetch comments via YouTube Data API v3 REST endpoints.
        """
        items: list[RawItem] = []
        seen_comment_ids: set[str] = set()

        self.logger.info(
            "Starting YouTube collection across %d queries (target: %d comments)",
            len(self.search_queries),
            target_count,
        )

        for query in self.search_queries:
            if len(items) >= target_count:
                break

            self.logger.info("Searching YouTube videos for query: '%s'", query)
            video_list = self._search_videos(query, max_results=self.max_videos_per_query)

            for video in video_list:
                if len(items) >= target_count:
                    break

                video_id = video["video_id"]
                video_title = video["title"]

                comments = self._fetch_video_comments(
                    video_id=video_id,
                    video_title=video_title,
                    query=query,
                    max_comments=self.max_comments_per_video,
                )

                for comment in comments:
                    if comment.source_native_id in seen_comment_ids:
                        continue
                    seen_comment_ids.add(comment.source_native_id)
                    items.append(comment)
                    if len(items) >= target_count:
                        break

                self.respect_rate_limit(0.2)

        self.logger.info("YouTube collection finished: collected %d comments", len(items))
        return items

    def _search_videos(self, query: str, max_results: int = 5) -> list[dict[str, str]]:
        """
        Query YouTube Data API v3 search endpoint to discover relevant video IDs.
        """
        url = f"{YOUTUBE_API_BASE_URL}/search"
        params = {
            "part": "snippet",
            "q": query,
            "type": "video",
            "maxResults": min(max_results, 50),
            "key": self.api_key,
        }

        try:
            resp = requests.get(url, params=params, timeout=10)
            if resp.status_code != 200:
                self._handle_api_error(resp, context=f"search: '{query}'")
                return []

            data = resp.json()
            results: list[dict[str, str]] = []
            for item in data.get("items", []):
                vid = item.get("id", {}).get("videoId")
                title = item.get("snippet", {}).get("title", "")
                if vid:
                    results.append({"video_id": vid, "title": title})
            return results

        except Exception as e:
            self.logger.warning("Error searching YouTube for '%s': %s", query, e)
            return []

    def _fetch_video_comments(
        self, video_id: str, video_title: str, query: str, max_comments: int = 50
    ) -> list[RawItem]:
        """
        Fetch top-level comments for a video using the commentThreads endpoint.
        """
        url = f"{YOUTUBE_API_BASE_URL}/commentThreads"
        params = {
            "part": "snippet",
            "videoId": video_id,
            "maxResults": min(max_comments, 100),
            "textFormat": "plainText",
            "order": "relevance",
            "key": self.api_key,
        }

        try:
            resp = requests.get(url, params=params, timeout=10)
            if resp.status_code != 200:
                self._handle_api_error(resp, context=f"commentThreads: video {video_id}")
                return []

            data = resp.json()
            comments: list[RawItem] = []

            for item in data.get("items", []):
                comment_id = item.get("id", "")
                top_comment = item.get("snippet", {}).get("topLevelComment", {})
                snippet = top_comment.get("snippet", {})

                text = snippet.get("textDisplay") or snippet.get("textOriginal") or ""
                text = text.strip()
                if not text:
                    continue

                author = snippet.get("authorDisplayName")
                like_count = snippet.get("likeCount", 0)
                published_str = snippet.get("publishedAt")

                published_at = None
                if published_str:
                    try:
                        published_at = datetime.fromisoformat(
                            published_str.replace("Z", "+00:00")
                        )
                    except Exception:
                        published_at = None

                platforms = detect_platforms(text)

                raw_item = RawItem(
                    source=SourceType.YOUTUBE,
                    source_native_id=comment_id,
                    source_url=f"https://www.youtube.com/watch?v={video_id}&lc={comment_id}",
                    platform_mentioned=platforms,
                    published_at=published_at,
                    text=text,
                    language_detected="en",
                    metadata=RawItemMetadata(
                        video_id=video_id,
                        thread_title=video_title,
                        extra={
                            "author": author,
                            "like_count": like_count,
                            "search_query": query,
                        },
                    ),
                )
                comments.append(raw_item)

            return comments

        except Exception as e:
            self.logger.warning("Error fetching comments for video %s: %s", video_id, e)
            return []

    def _handle_api_error(self, resp: requests.Response, context: str) -> None:
        """
        Handle and log specific YouTube API errors (comments disabled, quota exceeded, etc.).
        """
        try:
            err_data = resp.json().get("error", {})
            errors = err_data.get("errors", [])
            reasons = [e.get("reason", "") for e in errors]
            message = err_data.get("message", resp.text[:200])

            if "commentsDisabled" in reasons:
                self.logger.info("Comments disabled on %s", context)
            elif "quotaExceeded" in reasons:
                self.logger.warning("YouTube API quota exceeded during %s: %s", context, message)
            else:
                self.logger.warning("YouTube API error (%d) on %s: %s", resp.status_code, context, message)
        except Exception:
            self.logger.warning("YouTube API HTTP %d on %s", resp.status_code, context)

    def _collect_from_local_dump(self, target_count: int) -> list[RawItem]:
        """
        Fallback parser for local files if provided.
        """
        if not self.raw_file.is_file():
            self.logger.info("No local YouTube dump found at %s", self.raw_file)
            return []

        try:
            content = self.raw_file.read_text(encoding="utf-8", errors="replace")
            blocks = [b.strip() for b in content.split("\n\n") if b.strip()]
            items: list[RawItem] = []
            for idx, block in enumerate(blocks[:target_count]):
                items.append(
                    RawItem(
                        source=SourceType.YOUTUBE,
                        source_native_id=f"yt_manual_{idx}",
                        source_url="https://www.youtube.com",
                        platform_mentioned=detect_platforms(block),
                        published_at=None,
                        text=block,
                        language_detected="en",
                        metadata=RawItemMetadata(
                            thread_title="Manual YouTube Comment",
                            extra={"manual_index": idx},
                        ),
                    )
                )
            return items
        except Exception as e:
            self.logger.error("Error reading YouTube dump %s: %s", self.raw_file, e)
            return []

