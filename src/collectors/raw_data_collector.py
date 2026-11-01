"""
src/collectors/raw_data_collector.py — Collector for manually compiled raw data.

Parses manual compilations of raw user reviews and inquiries (such as raw_data/raw_data.txt)
from multiple sources (Play Store, App Store, Reddit, Quora, YouTube, Twitter/X),
normalizes them into RawItem instances, and integrates them into the collection pipeline.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from src.collectors.base_collector import BaseCollector, detect_platforms
from src.models.schemas import RawItem, RawItemMetadata, SourceType
from src.utils.logging import get_logger

logger = get_logger(__name__)

DEFAULT_RAW_FILE = Path("raw_data/raw_data.txt")

KNOWN_SOURCE_MAPPINGS = [
    (re.compile(r"reddit", re.IGNORECASE), SourceType.REDDIT),
    (re.compile(r"google\s*play", re.IGNORECASE), SourceType.PLAYSTORE),
    (re.compile(r"app\s*store", re.IGNORECASE), SourceType.APPSTORE),
    (re.compile(r"quora", re.IGNORECASE), SourceType.QUORA),
    (re.compile(r"youtube", re.IGNORECASE), SourceType.YOUTUBE),
    (re.compile(r"(?:x\s*/\s*twitter|twitter)", re.IGNORECASE), SourceType.TWITTER),
]

SUBREDDIT_REGEX = re.compile(r"r/([A-Za-z0-9_]+)", re.IGNORECASE)


def parse_raw_data_file(file_path: Path | str) -> list[RawItem]:
    """
    Parse a raw_data.txt file containing numbered feedback items (#001 to #300).

    Returns:
        List of normalized RawItem objects.
    """
    path = Path(file_path)
    if not path.is_file():
        logger.warning("Raw data file does not exist: %s", path)
        return []

    content = path.read_text(encoding="utf-8")
    chunks = re.split(r"(?:^|\n)#(\d{3})\s*\n", content)
    # chunks[0] is preamble; alternating chunks[i]=num_str, chunks[i+1]=item_content
    items: list[RawItem] = []

    for i in range(1, len(chunks), 2):
        num_str = chunks[i]
        block = chunks[i + 1].strip()

        # Clean header/footer artifacts
        lines: list[str] = []
        for line in block.split("\n"):
            line_stripped = line.strip()
            if not line_stripped:
                continue
            if "Groww SIP User Feedback" in line_stripped:
                continue
            if re.match(r"^Page \d+ of \d+$", line_stripped, re.IGNORECASE):
                continue
            lines.append(line_stripped)

        if not lines:
            continue

        # Extract source indicator line
        src_line = ""
        text_lines: list[str] = []

        def is_source_line(text_line: str) -> bool:
            return any(pattern.search(text_line) for pattern, _ in KNOWN_SOURCE_MAPPINGS)

        if lines and is_source_line(lines[0]):
            src_line = lines[0]
            text_lines = lines[1:]
        elif lines and is_source_line(lines[-1]):
            src_line = lines[-1]
            text_lines = lines[:-1]
        else:
            for idx, candidate in enumerate(lines):
                if is_source_line(candidate):
                    src_line = candidate
                    text_lines = [x for j, x in enumerate(lines) if j != idx]
                    break

        if not text_lines:
            # Fallback if no separate line found
            text_lines = lines

        # Combine text and clean surrounding quotation marks
        raw_text = " ".join(text_lines).strip()
        while (raw_text.startswith('"') and raw_text.endswith('"')) or (
            raw_text.startswith("“") and raw_text.endswith("”")
        ):
            raw_text = raw_text[1:-1].strip()

        # Determine source type
        source_type = SourceType.OTHER
        for pattern, st in KNOWN_SOURCE_MAPPINGS:
            if pattern.search(src_line):
                source_type = st
                break

        # Extract subreddit if reddit
        subreddit: Optional[str] = None
        if source_type == SourceType.REDDIT:
            sub_match = SUBREDDIT_REGEX.search(src_line)
            if sub_match:
                subreddit = f"r/{sub_match.group(1)}"

        # Determine source URL
        source_url: str
        if source_type == SourceType.REDDIT:
            source_url = f"https://www.reddit.com/{subreddit or 'r/mutualfunds'}/manual_raw_{num_str}"
        elif source_type == SourceType.PLAYSTORE:
            source_url = "https://play.google.com/store/apps/details?id=com.nextbillion.groww"
        elif source_type == SourceType.APPSTORE:
            source_url = "https://apps.apple.com/in/app/groww/id1404871703"
        elif source_type == SourceType.QUORA:
            source_url = "https://www.quora.com/topic/Groww-app"
        elif source_type == SourceType.YOUTUBE:
            source_url = "https://www.youtube.com/results?search_query=Groww+SIP"
        elif source_type == SourceType.TWITTER:
            source_url = "https://x.com/Groww_Care"
        else:
            source_url = "https://groww.in"

        # Platform tagging
        platforms = detect_platforms(raw_text)
        if "groww" not in platforms:
            platforms.append("groww")

        # Metadata
        metadata = RawItemMetadata(
            subreddit=subreddit,
            extra={
                "manual_collection": True,
                "dataset": "raw_data.txt",
                "item_number": int(num_str),
                "source_header": src_line,
            },
        )

        item = RawItem(
            source=source_type,
            source_native_id=f"manual_raw_{num_str}",
            source_url=source_url,
            platform_mentioned=platforms,
            published_at=datetime.now(timezone.utc),
            text=raw_text,
            language_detected="en",
            metadata=metadata,
        )
        items.append(item)

    logger.info("Parsed %d items from raw data file %s", len(items), path)
    return items


class RawDataCollector(BaseCollector):
    """Collector that loads manually gathered raw review datasets."""

    def __init__(self, config: Optional[dict[str, Any]] = None):
        super().__init__(config)
        self.raw_file = Path(self.config.get("raw_file", DEFAULT_RAW_FILE))

    def get_source_name(self) -> str:
        return "raw_data"

    @property
    def source_type(self) -> SourceType:
        return SourceType.OTHER

    def collect_snapshot(self, limit: Optional[int] = None) -> list[RawItem]:
        """Load and return all raw items from the configured manual raw data file."""
        items = parse_raw_data_file(self.raw_file)
        if limit and limit > 0:
            items = items[:limit]
        return items

