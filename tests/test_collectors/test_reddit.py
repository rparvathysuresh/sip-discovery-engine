"""
Unit tests for RedditCollector (both local raw file parsing and mocked PRAW API).
"""

from unittest.mock import MagicMock, patch
from pathlib import Path

from src.collectors.reddit_collector import RedditCollector
from src.models.schemas import SourceType


def test_reddit_collector_local_dump_success():
    collector = RedditCollector(config={"raw_file": "reddit_raw/reddit_raw.txt"})
    items = collector.collect_snapshot()

    assert len(items) == 40
    for item in items:
        assert item.source == SourceType.REDDIT
        assert item.source_native_id.startswith("reddit_manual_")
        assert len(item.text) > 10
        assert item.metadata is not None
        assert item.metadata.subreddit is not None
        assert item.metadata.thread_title is not None

    # First item verification
    first = items[0]
    assert first.source_native_id == "reddit_manual_1"
    assert "Hold this or not? Groww app SIP in loss" in first.metadata.thread_title
    assert "groww" in first.platform_mentioned
    assert "negative trend and now the loss is 4.7k" in first.text
    assert first.metadata.subreddit == "r/IndiaFinance"


def test_reddit_collector_local_dump_limit():
    collector = RedditCollector(config={"raw_file": "reddit_raw/reddit_raw.txt"})
    items = collector.collect_snapshot(limit=7)

    assert len(items) == 7
    assert items[0].source_native_id == "reddit_manual_1"
    assert items[6].source_native_id == "reddit_manual_7"


def test_reddit_collector_missing_raw_file(tmp_path):
    collector = RedditCollector(
        config={
            "raw_file": str(tmp_path / "non_existent.txt"),
            "raw_dir": str(tmp_path / "empty_dir"),
        }
    )
    items = collector.collect_snapshot()
    assert items == []


@patch("praw.Reddit")
def test_reddit_collector_api_success(mock_praw_reddit):
    # Setup mock PRAW submission
    mock_submission = MagicMock()
    mock_submission.id = "sub_12345"
    mock_submission.title = "Why did my SIP fail on Groww?"
    mock_submission.selftext = "Autopay failed and bank charged 590 rs mandate bounce fee."
    mock_submission.created_utc = 1712000000.0
    mock_submission.permalink = "/r/mutualfunds/comments/sub_12345/why_did_my_sip_fail/"
    mock_submission.score = 42
    mock_submission.num_comments = 15
    mock_submission.author = "investor_user"

    mock_sub = MagicMock()
    mock_sub.search.return_value = [mock_submission]

    mock_reddit_instance = MagicMock()
    mock_reddit_instance.subreddit.return_value = mock_sub
    mock_praw_reddit.return_value = mock_reddit_instance

    collector = RedditCollector(
        config={
            "client_id": "mock_id",
            "client_secret": "mock_secret",
            "subreddits": ["mutualfunds"],
            "search_queries": ["SIP failed"],
            "max_items_per_query": 5,
        }
    )

    items = collector.collect_snapshot(limit=10)

    assert len(items) == 1
    assert items[0].source == SourceType.REDDIT
    assert items[0].source_native_id == "sub_12345"
    assert "Autopay failed" in items[0].text
    assert items[0].metadata.thread_title == "Why did my SIP fail on Groww?"
    assert items[0].metadata.subreddit == "mutualfunds"
    assert items[0].metadata.extra["author"] == "investor_user"
    assert "groww" in items[0].platform_mentioned
    assert "https://www.reddit.com/r/mutualfunds/comments/sub_12345/" in items[0].source_url


@patch("praw.Reddit")
def test_reddit_collector_api_fallback_to_local(mock_praw_reddit):
    # Simulate API error
    mock_praw_reddit.side_effect = Exception("Reddit API 429 Too Many Requests")

    collector = RedditCollector(
        config={
            "client_id": "mock_id",
            "client_secret": "mock_secret",
            "raw_file": "reddit_raw/reddit_raw.txt",
        }
    )

    # Should fall back to local dump
    items = collector.collect_snapshot(limit=3)
    assert len(items) == 3
    assert items[0].source_native_id == "reddit_manual_1"
