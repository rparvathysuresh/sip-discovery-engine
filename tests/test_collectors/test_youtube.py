"""
Unit tests for YouTubeCollector with mocked YouTube Data API v3 responses.
"""

from unittest.mock import MagicMock, patch

from src.collectors.youtube_collector import YouTubeCollector
from src.models.schemas import SourceType


@patch("src.collectors.youtube_collector.requests.get")
def test_youtube_collector_success(mock_get):
    # Mock video search response
    search_resp = MagicMock()
    search_resp.status_code = 200
    search_resp.json.return_value = {
        "items": [
            {
                "id": {"videoId": "vid_abc123"},
                "snippet": {"title": "Groww SIP Complete Guide for Beginners"},
            }
        ]
    }

    # Mock comments response
    comments_resp = MagicMock()
    comments_resp.status_code = 200
    comments_resp.json.return_value = {
        "items": [
            {
                "id": "comment_999",
                "snippet": {
                    "topLevelComment": {
                        "snippet": {
                            "textDisplay": "My SIP bounced on Groww and bank charged 500 Rs penalty! How do I pause it?",
                            "authorDisplayName": "Rohan Sharma",
                            "likeCount": 12,
                            "publishedAt": "2024-05-10T14:30:00Z",
                        }
                    }
                },
            }
        ]
    }

    mock_get.side_effect = [search_resp, comments_resp]

    collector = YouTubeCollector(
        config={
            "api_key": "dummy_test_key",
            "search_queries": ["Groww SIP review"],
            "max_videos_per_query": 1,
            "max_comments_per_video": 10,
        }
    )

    items = collector.collect_snapshot(limit=5)

    assert len(items) == 1
    item = items[0]
    assert item.source == SourceType.YOUTUBE
    assert item.source_native_id == "comment_999"
    assert "https://www.youtube.com/watch?v=vid_abc123&lc=comment_999" in item.source_url
    assert "SIP bounced on Groww" in item.text
    assert "groww" in item.platform_mentioned
    assert item.metadata.video_id == "vid_abc123"
    assert item.metadata.thread_title == "Groww SIP Complete Guide for Beginners"
    assert item.metadata.extra["author"] == "Rohan Sharma"
    assert item.metadata.extra["like_count"] == 12
    assert item.metadata.extra["search_query"] == "Groww SIP review"
    assert item.published_at is not None


@patch("src.collectors.youtube_collector.requests.get")
def test_youtube_collector_comments_disabled(mock_get):
    search_resp = MagicMock()
    search_resp.status_code = 200
    search_resp.json.return_value = {
        "items": [
            {
                "id": {"videoId": "vid_disabled"},
                "snippet": {"title": "Disabled Comments Video"},
            }
        ]
    }

    error_resp = MagicMock()
    error_resp.status_code = 403
    error_resp.json.return_value = {
        "error": {
            "errors": [{"reason": "commentsDisabled"}],
            "message": "The video has disabled comments.",
        }
    }

    mock_get.side_effect = [search_resp, error_resp]

    collector = YouTubeCollector(
        config={
            "api_key": "dummy_test_key",
            "search_queries": ["SIP"],
            "max_videos_per_query": 1,
        }
    )

    items = collector.collect_snapshot(limit=5)
    assert items == []


@patch("src.collectors.youtube_collector.requests.get")
def test_youtube_collector_quota_exceeded(mock_get):
    quota_resp = MagicMock()
    quota_resp.status_code = 403
    quota_resp.json.return_value = {
        "error": {
            "errors": [{"reason": "quotaExceeded"}],
            "message": "The request cannot be completed because you have exceeded your quota.",
        }
    }

    mock_get.return_value = quota_resp

    collector = YouTubeCollector(
        config={
            "api_key": "dummy_test_key",
            "search_queries": ["SIP"],
        }
    )

    items = collector.collect_snapshot(limit=5)
    assert items == []


def test_youtube_collector_missing_api_key(tmp_path):
    collector = YouTubeCollector(
        config={
            "api_key": "",
            "raw_file": str(tmp_path / "nonexistent.txt"),
        }
    )
    items = collector.collect_snapshot()
    assert items == []


def test_youtube_collector_local_dump(tmp_path):
    dump_file = tmp_path / "youtube_raw.txt"
    dump_file.write_text(
        "I started SIP in Nippon small cap on Groww, now market is down 5% should I stop?\n\n"
        "Can we change the bank account for active SIP without paying bounce charge?",
        encoding="utf-8",
    )

    collector = YouTubeCollector(
        config={
            "api_key": "",
            "raw_file": str(dump_file),
        }
    )

    items = collector.collect_snapshot(limit=10)
    assert len(items) == 2
    assert items[0].source == SourceType.YOUTUBE
    assert items[0].source_native_id == "yt_manual_0"
    assert "groww" in items[0].platform_mentioned
    assert "Nippon small cap" in items[0].text
    assert items[1].source_native_id == "yt_manual_1"

