"""
Quora collector for SIP and mutual fund investor questions and answers.
Supports live web scraping of public search topics and questions, with fallback
to local raw dumps in quora_raw/quora_raw.txt.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import requests
from bs4 import BeautifulSoup

from src.collectors.base_collector import BaseCollector, detect_platforms
from src.models.schemas import RawItem, RawItemMetadata, SourceType
from src.utils.logging import get_logger

logger = get_logger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

DEFAULT_QUORA_QUERIES = [
    "Groww SIP review",
    "SIP stopped Groww",
    "first time mutual fund SIP India",
    "why stop SIP mutual fund",
    "is Groww safe for SIP",
    "Groww mandate charges",
]


class QuoraCollector(BaseCollector):
    """
    Collects qualitative discussions, questions, and answers from Quora.
    Handles online HTML scraping with anti-bot resilience, and seamlessly falls
    back to local dump files in quora_raw/.
    """

    def __init__(self, config: Optional[dict[str, Any]] = None):
        super().__init__(config)
        self.base_url = self.config.get("base_url", "https://www.quora.com").rstrip("/")
        self.search_queries = self.config.get("search_queries", DEFAULT_QUORA_QUERIES)
        self.max_items_per_query = self.config.get("max_items_per_query", 15)
        self.raw_dir = Path(self.config.get("raw_dir", "quora_raw"))
        self.raw_file = Path(self.config.get("raw_file", "quora_raw/quora_raw.txt"))

    def get_source_name(self) -> str:
        return "quora"

    @property
    def source_type(self) -> SourceType:
        return SourceType.QUORA

    def collect_snapshot(self, limit: Optional[int] = None) -> list[RawItem]:
        """
        Collect Quora questions and answers matching SIP search queries.

        Args:
            limit: Maximum items to collect.

        Returns:
            List of normalized RawItem records.
        """
        target_count = limit or 200
        items: list[RawItem] = []
        seen_ids: set[str] = set()

        self.logger.info("Starting Quora collection (target: %d items)", target_count)

        # 1. Attempt online query collection
        online_items = self._collect_online(target_count)
        for item in online_items:
            if item.source_native_id not in seen_ids:
                seen_ids.add(item.source_native_id)
                items.append(item)
                if len(items) >= target_count:
                    break

        # 2. If online collection returned zero items (e.g. offline, blocked, or sandboxed), use local dump
        if not items:
            self.logger.info("Online Quora search yielded 0 items. Checking local quora_raw dump.")
            local_items = self._collect_from_local_dump(target_count)
            for item in local_items:
                if item.source_native_id not in seen_ids:
                    seen_ids.add(item.source_native_id)
                    items.append(item)
                    if len(items) >= target_count:
                        break

        self.logger.info("Quora collection completed: %d items collected", len(items))
        return items[:target_count]

    def _collect_online(self, target_count: int) -> list[RawItem]:
        """
        Query public Quora pages for discussions matching search queries.
        """
        items: list[RawItem] = []

        for query in self.search_queries:
            if len(items) >= target_count:
                break

            encoded_query = query.replace(" ", "-")
            url = f"{self.base_url}/{encoded_query}"

            try:
                resp = requests.get(url, headers=DEFAULT_HEADERS, timeout=10)
                if resp.status_code != 200:
                    self.logger.debug("Quora search for '%s' returned status %d", query, resp.status_code)
                    continue

                parsed = self._parse_quora_html(resp.text, query, url)
                for item in parsed:
                    items.append(item)
                    if len(items) >= target_count:
                        break

                self.respect_rate_limit(0.5)

            except Exception as e:
                self.logger.debug("Error requesting Quora page for '%s': %s", query, e)

        return items

    def _parse_quora_html(self, html: str, query: str, page_url: str) -> list[RawItem]:
        """
        Extract questions, structured JSON-LD, or post content from Quora HTML.
        """
        items: list[RawItem] = []
        soup = BeautifulSoup(html, "html.parser")

        # 1. Check for schema.org / JSON-LD Question data
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "")
                if isinstance(data, dict) and data.get("@type") in ("Question", "QAPage"):
                    title = data.get("name") or data.get("headline") or query
                    main_entity = data.get("mainEntity", {})
                    accepted = main_entity.get("acceptedAnswer", {}) or data.get("acceptedAnswer", {})
                    answer_text = accepted.get("text", "")

                    if title and answer_text:
                        clean_answer = BeautifulSoup(answer_text, "html.parser").get_text(separator=" ").strip()
                        full_text = f"{title}\n\n{clean_answer}"
                        native_id = hashlib.sha256(full_text.encode("utf-8")).hexdigest()[:12]

                        items.append(
                            RawItem(
                                source=SourceType.QUORA,
                                source_native_id=f"quora_{native_id}",
                                source_url=page_url,
                                platform_mentioned=detect_platforms(full_text),
                                text=full_text,
                                language_detected="en",
                                metadata=RawItemMetadata(
                                    thread_title=title,
                                    extra={"search_query": query, "format": "json_ld"},
                                ),
                            )
                        )
            except Exception:
                continue

        # 2. Check standard question and answer containers
        if not items:
            title_tag = soup.find("title")
            title = title_tag.get_text().replace(" - Quora", "").strip() if title_tag else query

            # Collect text blocks from paragraph or answer containers
            paragraphs = [p.get_text().strip() for p in soup.find_all("p") if len(p.get_text().strip()) > 30]
            if paragraphs:
                body_text = "\n\n".join(paragraphs[:5])
                full_text = f"{title}\n\n{body_text}"
                native_id = hashlib.sha256(full_text.encode("utf-8")).hexdigest()[:12]

                items.append(
                    RawItem(
                        source=SourceType.QUORA,
                        source_native_id=f"quora_{native_id}",
                        source_url=page_url,
                        platform_mentioned=detect_platforms(full_text),
                        text=full_text,
                        language_detected="en",
                        metadata=RawItemMetadata(
                            thread_title=title,
                            extra={"search_query": query, "format": "html_scrape"},
                        ),
                    )
                )

        return items

    def _collect_from_local_dump(self, target_count: int) -> list[RawItem]:
        """
        Parse human-collected or exported Quora questions and answers from quora_raw/.
        """
        items: list[RawItem] = []

        candidate_files: list[Path] = []
        if self.raw_file.is_file():
            candidate_files.append(self.raw_file)
        elif self.raw_dir.is_dir():
            candidate_files.extend(sorted(self.raw_dir.glob("*.txt")))

        if not candidate_files:
            self.logger.info("No local Quora dump files found at %s or in %s", self.raw_file, self.raw_dir)
            return []

        for fpath in candidate_files:
            if len(items) >= target_count:
                break
            try:
                content = fpath.read_text(encoding="utf-8", errors="replace")
                parsed = self._parse_raw_text_dump(content, fpath.name)
                for item in parsed:
                    items.append(item)
                    if len(items) >= target_count:
                        break
            except Exception as e:
                self.logger.error("Error reading Quora raw dump %s: %s", fpath, e)

        return items

    def _parse_raw_text_dump(self, content: str, filename: str) -> list[RawItem]:
        """
        Parse numbered or question-separated blocks from raw text file.
        Format pattern:
          1. <Question>
          <Answer / Content>
          or
          Q: <Question>
          A: <Answer>
        """
        # Split on numbered item headings or Q: delimiters
        matches = list(re.finditer(r"(?:^|\n)\s*(?:(\d+)\.|\bQ:)\s*(.*?)(?=\n)", content))
        if not matches:
            blocks = [b.strip() for b in content.split("\n\n---\n\n") if b.strip()]
            return [
                RawItem(
                    source=SourceType.QUORA,
                    source_native_id=f"quora_manual_{filename}_{idx}",
                    source_url="https://www.quora.com",
                    platform_mentioned=detect_platforms(block),
                    published_at=None,
                    text=block,
                    metadata=RawItemMetadata(
                        thread_title=block.splitlines()[0][:60] if block else "Quora Q&A",
                        extra={"filename": filename, "block_index": idx},
                    ),
                )
                for idx, block in enumerate(blocks)
            ]

        results: list[RawItem] = []
        for i, m in enumerate(matches):
            start = m.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
            raw_block = content[start:end].strip()
            num = m.group(1) or str(i + 1)
            first_line_rest = m.group(2).strip()

            lines = [line.strip() for line in raw_block.splitlines() if line.strip()]
            if not lines:
                continue

            # Title is typically the first line
            title = first_line_rest if first_line_rest else re.sub(r"^\d+\.\s*|^Q:\s*", "", lines[0]).strip()
            # Clean full text
            clean_text = "\n".join(lines).strip()
            clean_text = re.sub(r"^\d+\.\s*", "", clean_text).strip()

            platforms = detect_platforms(clean_text)

            item = RawItem(
                source=SourceType.QUORA,
                source_native_id=f"quora_manual_{num}",
                source_url=f"https://www.quora.com/{re.sub(r'[^a-zA-Z0-9]+', '-', title).strip('-')}",
                platform_mentioned=platforms,
                published_at=None,
                text=clean_text,
                language_detected="en",
                metadata=RawItemMetadata(
                    thread_title=title or None,
                    extra={
                        "manual_index": int(num) if num.isdigit() else i + 1,
                        "source_file": filename,
                    },
                ),
            )
            results.append(item)

        return results

