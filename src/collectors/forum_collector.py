"""
Forum collector for qualitative investor discussions.
Collects from TradingQnA (Discourse API) and Value Research (RSS / articles),
with graceful fallback to local dump files in forum_raw/.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Optional

import requests
from bs4 import BeautifulSoup

from src.collectors.base_collector import BaseCollector, detect_platforms
from src.models.schemas import RawItem, RawItemMetadata, SourceType
from src.utils.logging import get_logger

logger = get_logger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": "sip-discovery-engine/0.1 (Research & Analytics; contact@sipdiscovery.local)"
}


class ForumCollector(BaseCollector):
    """
    Collects investor discussions, Q&As, and articles from major Indian financial forums:
    - TradingQnA (Zerodha's Discourse community)
    - Value Research (Editorial & investor Q&A RSS)
    """

    def __init__(self, config: Optional[dict[str, Any]] = None):
        super().__init__(config)

        # TradingQnA configuration
        tqna_cfg = self.config.get("tradingqna", {})
        self.tqna_base_url = tqna_cfg.get("base_url", "https://tradingqna.com").rstrip("/")
        self.tqna_queries = tqna_cfg.get("search_queries", [
            "SIP",
            "mutual fund retention",
            "SIP stop",
            "SIP pause",
            "mandate bounce",
        ])

        # Value Research configuration
        vr_cfg = self.config.get("valueresearch", {})
        self.vr_base_url = vr_cfg.get("base_url", "https://www.valueresearchonline.com").rstrip("/")
        self.vr_rss_url = vr_cfg.get("rss_url", f"{self.vr_base_url}/rss/")
        self.vr_queries = vr_cfg.get("search_queries", [
            "first time SIP",
            "SIP returns negative",
            "SIP",
        ])

        self.max_posts_per_query = self.config.get("max_posts_per_query", 25)
        self.raw_dir = Path(self.config.get("raw_dir", "forum_raw"))
        self.raw_file = Path(self.config.get("raw_file", "forum_raw/forum_raw.txt"))

    def get_source_name(self) -> str:
        return "forum"

    @property
    def source_type(self) -> SourceType:
        return SourceType.FORUM

    def collect_snapshot(self, limit: Optional[int] = None) -> list[RawItem]:
        """
        Collect forum posts and articles across configured forums.
        
        Args:
            limit: Maximum items to return.
            
        Returns:
            List of normalized RawItem records.
        """
        target_count = limit or 500
        items: list[RawItem] = []
        seen_ids: set[str] = set()

        self.logger.info("Starting Forum collection (target: %d items)", target_count)

        # 1. Collect from TradingQnA (Discourse API)
        tqna_items = self._collect_from_tradingqna(target_count - len(items))
        for item in tqna_items:
            if item.source_native_id not in seen_ids:
                seen_ids.add(item.source_native_id)
                items.append(item)
                if len(items) >= target_count:
                    break

        # 2. Collect from Value Research (RSS)
        if len(items) < target_count:
            vr_items = self._collect_from_valueresearch(target_count - len(items))
            for item in vr_items:
                if item.source_native_id not in seen_ids:
                    seen_ids.add(item.source_native_id)
                    items.append(item)
                    if len(items) >= target_count:
                        break

        # 3. Fallback to local dump if online collection yielded no items (e.g. offline/sandboxed)
        if not items:
            self.logger.info("Online forum sources yielded 0 items. Checking local forum dump.")
            items = self._collect_from_local_dump(target_count)

        self.logger.info("Forum collection complete: %d items gathered", len(items))
        return items[:target_count]

    def _collect_from_tradingqna(self, target_count: int) -> list[RawItem]:
        """
        Fetch topics and posts from TradingQnA via Discourse search.json API.
        """
        items: list[RawItem] = []
        seen_post_ids: set[int] = set()

        for query in self.tqna_queries:
            if len(items) >= target_count:
                break

            url = f"{self.tqna_base_url}/search.json"
            params = {"q": query}

            try:
                resp = requests.get(url, params=params, headers=DEFAULT_HEADERS, timeout=10)
                if resp.status_code != 200:
                    self.logger.warning("TradingQnA search '%s' returned status %d", query, resp.status_code)
                    continue

                data = resp.json()
                topics = {t["id"]: t for t in data.get("topics", []) if "id" in t}
                posts = data.get("posts", [])

                for post in posts:
                    post_id = post.get("id")
                    if not post_id or post_id in seen_post_ids:
                        continue
                    seen_post_ids.add(post_id)

                    topic_id = post.get("topic_id")
                    topic = topics.get(topic_id, {})
                    topic_title = topic.get("title", "")
                    slug = topic.get("slug", f"topic-{topic_id}")
                    post_num = post.get("post_number", 1)

                    blurb = post.get("blurb", "").strip()
                    # If blurb is empty or short, check cooked
                    text = blurb
                    if not text and "cooked" in post:
                        text = BeautifulSoup(post["cooked"], "html.parser").get_text(separator=" ").strip()

                    if not text:
                        continue

                    # If topic title adds valuable context, prepend it
                    full_text = f"{topic_title}\n\n{text}".strip() if topic_title and topic_title not in text else text

                    published_at = None
                    created_at_str = post.get("created_at")
                    if created_at_str:
                        try:
                            published_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
                        except Exception:
                            published_at = None

                    platforms = detect_platforms(full_text)
                    source_url = f"{self.tqna_base_url}/t/{slug}/{topic_id}/{post_num}"

                    raw_item = RawItem(
                        source=SourceType.FORUM,
                        source_native_id=f"tradingqna_{post_id}",
                        source_url=source_url,
                        platform_mentioned=platforms,
                        published_at=published_at,
                        text=full_text,
                        language_detected="en",
                        metadata=RawItemMetadata(
                            thread_title=topic_title or None,
                            extra={
                                "forum": "tradingqna",
                                "username": post.get("username"),
                                "topic_id": topic_id,
                                "search_query": query,
                            },
                        ),
                    )
                    items.append(raw_item)
                    if len(items) >= target_count:
                        break

                self.respect_rate_limit(0.5)

            except Exception as e:
                self.logger.warning("Error fetching TradingQnA for query '%s': %s", query, e)

        return items

    def _collect_from_valueresearch(self, target_count: int) -> list[RawItem]:
        """
        Fetch editorial posts and investor Q&As from Value Research RSS.
        """
        items: list[RawItem] = []

        try:
            resp = requests.get(self.vr_rss_url, headers=DEFAULT_HEADERS, timeout=10)
            if resp.status_code != 200:
                self.logger.warning("Value Research RSS returned status %d", resp.status_code)
                return []

            root = ET.fromstring(resp.content)
            channel = root.find("channel")
            if channel is None:
                return []

            entries = channel.findall("item")
            for idx, entry in enumerate(entries):
                title = (entry.findtext("title") or "").strip()
                link = (entry.findtext("link") or "").strip()
                description = (entry.findtext("description") or "").strip()
                pub_date_str = (entry.findtext("pubDate") or "").strip()

                # Clean HTML tags out of description if any
                if "<" in description and ">" in description:
                    description = BeautifulSoup(description, "html.parser").get_text(separator=" ").strip()

                full_text = f"{title}\n\n{description}".strip() if description else title
                if not full_text:
                    continue

                published_at = None
                if pub_date_str:
                    try:
                        published_at = parsedate_to_datetime(pub_date_str)
                    except Exception:
                        published_at = None

                platforms = detect_platforms(full_text)

                # Extract story/article ID from link if present
                guid_match = re.search(r"/stories/(\d+)/", link)
                native_id = f"valueresearch_{guid_match.group(1)}" if guid_match else f"valueresearch_{idx}"

                raw_item = RawItem(
                    source=SourceType.FORUM,
                    source_native_id=native_id,
                    source_url=link or self.vr_base_url,
                    platform_mentioned=platforms,
                    published_at=published_at,
                    text=full_text,
                    language_detected="en",
                    metadata=RawItemMetadata(
                        thread_title=title or None,
                        extra={
                            "forum": "valueresearch",
                            "link": link,
                        },
                    ),
                )
                items.append(raw_item)
                if len(items) >= target_count:
                    break

        except Exception as e:
            self.logger.warning("Error collecting from Value Research RSS: %s", e)

        return items

    def _collect_from_local_dump(self, target_count: int) -> list[RawItem]:
        """
        Read local raw forum dump files if available.
        """
        if not self.raw_file.is_file():
            return []

        try:
            content = self.raw_file.read_text(encoding="utf-8", errors="replace")
            blocks = [b.strip() for b in content.split("\n\n---\n\n") if b.strip()]
            items: list[RawItem] = []
            for idx, block in enumerate(blocks[:target_count]):
                lines = block.splitlines()
                title = lines[0].strip() if lines else "Forum Discussion"
                platforms = detect_platforms(block)
                items.append(
                    RawItem(
                        source=SourceType.FORUM,
                        source_native_id=f"forum_manual_{idx}",
                        source_url="https://tradingqna.com",
                        platform_mentioned=platforms,
                        published_at=None,
                        text=block,
                        language_detected="en",
                        metadata=RawItemMetadata(
                            thread_title=title,
                            extra={"manual_index": idx},
                        ),
                    )
                )
            return items
        except Exception as e:
            self.logger.error("Error reading local forum dump: %s", e)
            return []

