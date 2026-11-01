"""
Reddit collector for SIP and mutual fund discussions.
Supports both official Reddit API (PRAW OAuth2) and manual/local raw dumps (e.g. reddit_raw/reddit_raw.txt).
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

# Noise patterns commonly found in Reddit web copy-pastes
NOISE_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"^Page\s+\d+.*",
        r"^Item\s+\d+\s+of\s+\d+",
        r"^Upvote$",
        r"^Downvote$",
        r"^\d+$",
        r"^Repost$",
        r"^Share$",
        r"^Archived post.*",
        r"^Go to .*",
        r"^Sort by:?.*",
        r"^Best$",
        r"^Search Comments$",
        r"^Expand comment search$",
        r"^Comments Section$",
        r"^[•\-\*]$",
        r"^\d+[mhdwy]\s+ago$",
        r"^Open$",
        r"^View More$",
        r"^Ad$",
        r"^Thumbnail image:.*",
        r"^.*avatar$",
        r"^linkedin\.com$",
        r"^msg91\.com$",
    ]
]

TAG_FLAIRS = {
    "question",
    "discussion",
    "help",
    "reviews",
    "portfolio review",
    "other discussion",
    "educational",
    "mutual funds",
}


class RedditCollector(BaseCollector):
    """
    Collects qualitative discussions and reviews from Reddit.
    Supports official PRAW API access when credentials are configured,
    and falls back cleanly to local raw text/JSON dumps in `reddit_raw/`.
    """

    def __init__(self, config: Optional[dict[str, Any]] = None):
        super().__init__(config)
        self.client_id = self.config.get("client_id") or ""
        self.client_secret = self.config.get("client_secret") or ""
        self.user_agent = self.config.get("user_agent") or "sip-discovery-engine/0.1"
        self.subreddits = self.config.get("subreddits", [
            "IndiaInvestments",
            "personalfinanceindia",
            "IndianStreetBets",
            "mutualfunds",
            "MutualfundsIndia",
        ])
        self.search_queries = self.config.get("search_queries", [
            "SIP stopped",
            "first SIP",
            "SIP returns",
            "SIP not working",
            "Groww SIP",
            "stop SIP",
            "pause SIP",
            "SIP loss",
        ])
        self.max_items_per_query = self.config.get("max_items_per_query", 100)
        self.raw_dir = Path(self.config.get("raw_dir", "reddit_raw"))
        self.raw_file = Path(self.config.get("raw_file", "reddit_raw/reddit_raw.txt"))

    def get_source_name(self) -> str:
        return "reddit"

    @property
    def source_type(self) -> SourceType:
        return SourceType.REDDIT

    def collect_snapshot(self, limit: Optional[int] = None) -> list[RawItem]:
        """
        Collect snapshot of Reddit submissions and discussions.
        If PRAW credentials are valid, fetches via Reddit API.
        Otherwise parses local raw files from reddit_raw/.
        """
        target_count = limit or 500

        # Check if local dump exists first or if PRAW credentials are absent or placeholder
        has_credentials = bool(
            self.client_id
            and self.client_secret
            and self.client_id not in ("your_reddit_client_id", "your_reddit_client_id_here")
        )

        if not has_credentials:
            self.logger.info(
                "Reddit API credentials not configured or placeholder detected. Checking local raw dump at %s",
                self.raw_file,
            )
            return self._collect_from_local_dump(target_count)

        # Attempt API collection when valid credentials are provided
        try:
            items = self._collect_from_api(target_count)
            if not items and (self.raw_file.is_file() or self.raw_dir.is_dir()):
                self.logger.info("Reddit API returned 0 items. Falling back to local raw dump.")
                return self._collect_from_local_dump(target_count)
            return items
        except Exception as e:
            self.logger.warning("Reddit API collection failed: %s. Falling back to local raw dump.", e)
            return self._collect_from_local_dump(target_count)

    def _collect_from_api(self, target_count: int) -> list[RawItem]:
        """
        Fetch posts using PRAW OAuth2 client.
        """
        import praw  # lazy import

        reddit = praw.Reddit(
            client_id=self.client_id,
            client_secret=self.client_secret,
            user_agent=self.user_agent,
        )

        items: list[RawItem] = []
        seen_ids: set[str] = set()

        for sub_name in self.subreddits:
            if len(items) >= target_count:
                break

            self.logger.info("Searching r/%s on Reddit API...", sub_name)
            try:
                subreddit = reddit.subreddit(sub_name)
                for query in self.search_queries:
                    if len(items) >= target_count:
                        break

                    for submission in subreddit.search(query, limit=self.max_items_per_query, sort="relevance"):
                        if submission.id in seen_ids:
                            continue
                        seen_ids.add(submission.id)

                        title = submission.title or ""
                        body = submission.selftext or ""
                        full_text = f"{title}\n\n{body}".strip() if body else title
                        if not full_text:
                            continue

                        published_at = None
                        if getattr(submission, "created_utc", None):
                            published_at = datetime.fromtimestamp(submission.created_utc, timezone.utc)

                        platforms = detect_platforms(full_text)

                        raw_item = RawItem(
                            source=SourceType.REDDIT,
                            source_native_id=submission.id,
                            source_url=f"https://www.reddit.com{getattr(submission, 'permalink', '')}",
                            platform_mentioned=platforms,
                            published_at=published_at,
                            text=full_text,
                            language_detected="en",
                            metadata=RawItemMetadata(
                                subreddit=sub_name,
                                thread_title=title,
                                extra={
                                    "author": str(submission.author) if submission.author else None,
                                    "score": getattr(submission, "score", None),
                                    "num_comments": getattr(submission, "num_comments", None),
                                },
                            ),
                        )
                        items.append(raw_item)
                        if len(items) >= target_count:
                            break

                    self.respect_rate_limit(1.0)
            except Exception as e:
                self.logger.warning("Error fetching from r/%s: %s", sub_name, e)

        return items

    def _collect_from_local_dump(self, target_count: int) -> list[RawItem]:
        """
        Parse raw discussions from local file or directory dumps.
        """
        items: list[RawItem] = []

        # Find candidate dump files
        candidate_files: list[Path] = []
        if self.raw_file.is_file():
            candidate_files.append(self.raw_file)
        elif self.raw_dir.is_dir():
            candidate_files.extend(sorted(self.raw_dir.glob("*.txt")))

        if not candidate_files:
            self.logger.warning(
                "No Reddit dump files found at %s or in %s", self.raw_file, self.raw_dir
            )
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
                self.logger.error("Error reading Reddit raw file %s: %s", fpath, e)

        self.logger.info("Local Reddit collection completed: %d items normalized", len(items))
        return items

    def _parse_raw_text_dump(self, content: str, filename: str) -> list[RawItem]:
        """
        Parse human-collected or exported Reddit reviews and posts into RawItem objects.
        """
        # Split on numbered item patterns e.g. "1. ", "2. "
        matches = list(re.finditer(r"(?:^|\n)\s*(\d+)\.\s*(.*?)(?=\n)", content))
        if not matches:
            # Fallback if unnumbered: treat entire text or paragraphs as single/multiple items
            blocks = [p.strip() for p in content.split("\n\n\n") if p.strip()]
            return [
                RawItem(
                    source=SourceType.REDDIT,
                    source_native_id=f"{filename}_{idx}",
                    source_url="https://www.reddit.com/r/mutualfunds",
                    platform_mentioned=detect_platforms(block),
                    published_at=None,
                    text=block,
                    metadata=RawItemMetadata(
                        extra={"filename": filename, "block_index": idx}
                    ),
                )
                for idx, block in enumerate(blocks)
            ]

        results: list[RawItem] = []
        for i, m in enumerate(matches):
            start = m.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
            raw_block = content[start:end].strip()
            num = m.group(1)

            # Detect subreddit mentioned in the block
            sub_m = re.search(r"\b(r/[A-Za-z0-9_]+)\b", raw_block)
            subreddit = sub_m.group(1) if sub_m else "r/mutualfunds"

            # Detect author if present (e.g. u/username)
            author_m = re.search(r"\b(u/[A-Za-z0-9_-]+)\b", raw_block)
            author = author_m.group(1) if author_m else None

            # Clean noise and UI lines
            raw_lines = [line.strip() for line in raw_block.splitlines()]
            clean_lines = []
            skip_until = 0

            for idx, line in enumerate(raw_lines):
                if idx < skip_until:
                    continue
                # Strip leading number prefixes like '1. ' if present
                clean_l = re.sub(r"^\d+\.\s*", "", line).strip()
                if not clean_l:
                    continue
                if clean_l.lower() in ("ad", "promoted"):
                    skip_until = idx + 5
                    continue
                if any(rgx.match(clean_l) for rgx in NOISE_PATTERNS):
                    continue
                clean_lines.append(clean_l)

            # Determine title
            title = ""
            for l in clean_lines:
                if re.match(r"^r/[A-Za-z0-9_]+$", l) or l.startswith("u/") or l.startswith("r/"):
                    continue
                if l.lower() in TAG_FLAIRS:
                    continue
                if len(l) > 3:
                    title = l
                    break

            full_text = "\n".join(clean_lines).strip()
            if not full_text:
                continue

            platforms = detect_platforms(full_text)

            item = RawItem(
                source=SourceType.REDDIT,
                source_native_id=f"reddit_manual_{num}",
                source_url=f"https://www.reddit.com/{subreddit}",
                platform_mentioned=platforms,
                published_at=None,
                text=full_text,
                language_detected="en",
                metadata=RawItemMetadata(
                    subreddit=subreddit,
                    thread_title=title or None,
                    extra={
                        "author": author,
                        "manual_index": int(num),
                        "source_file": filename,
                    },
                ),
            )
            results.append(item)

        return results
