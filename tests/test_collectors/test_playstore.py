"""
Tests for PlayStoreCollector with mocked google-play-scraper.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from src.collectors.playstore_collector import PlayStoreCollector
from src.models.schemas import SourceType


@patch("src.collectors.playstore_collector.reviews")
def test_playstore_collector_success(mock_reviews):
    mock_reviews.return_value = (
        [
            {
                "reviewId": "gp_101",
                "content": "Groww SIP deduction was delayed by 3 days. Very confusing.",
                "score": 2,
                "thumbsUpCount": 5,
                "reviewCreatedVersion": "12.4.1",
                "replyContent": "We are looking into this.",
                "at": datetime(2025, 3, 10, 12, 0, 0, tzinfo=timezone.utc),
            },
            {
                "reviewId": "gp_102",
                "content": "Best app for beginners, continued SIP for 1 year without issues.",
                "score": 5,
                "thumbsUpCount": 1,
                "reviewCreatedVersion": "12.4.0",
                "replyContent": None,
                "at": datetime(2025, 3, 11, 14, 0, 0, tzinfo=timezone.utc),
            },
        ],
        None,  # No continuation token (single page)
    )

    collector = PlayStoreCollector(config={"app_id": "com.nextbillion.groww", "max_reviews": 10})
    items = collector.collect_snapshot(limit=2)

    assert len(items) == 2
    assert items[0].source == SourceType.PLAYSTORE
    assert items[0].source_native_id == "gp_101"
    assert "groww" in items[0].platform_mentioned
    assert items[0].metadata.rating == 2
    assert items[0].metadata.extra["thumbs_up"] == 5
    assert items[0].metadata.extra["app_version"] == "12.4.1"
    assert "https://play.google.com/store/apps/details" in items[0].source_url

    assert items[1].source_native_id == "gp_102"
    assert items[1].metadata.rating == 5


@patch("src.collectors.playstore_collector.reviews")
def test_playstore_collector_pagination(mock_reviews):
    # First batch returns continuation token 'token_123', second batch returns None
    page1 = [
        {
            "reviewId": f"gp_{i}",
            "content": f"Review {i} about mutual funds.",
            "score": 4,
            "thumbsUpCount": 0,
            "reviewCreatedVersion": "12.0",
            "at": datetime(2025, 1, 1, tzinfo=timezone.utc),
        }
        for i in range(2)
    ]
    page2 = [
        {
            "reviewId": f"gp_{i}",
            "content": f"Review {i} about mutual funds.",
            "score": 3,
            "thumbsUpCount": 0,
            "reviewCreatedVersion": "12.0",
            "at": datetime(2025, 1, 2, tzinfo=timezone.utc),
        }
        for i in range(2, 4)
    ]

    mock_reviews.side_effect = [
        (page1, "token_123"),
        (page2, None),
    ]

    collector = PlayStoreCollector(config={"max_reviews": 4})
    items = collector.collect_snapshot(limit=4)

    assert len(items) == 4
    assert mock_reviews.call_count == 2
    assert items[3].source_native_id == "gp_3"


@patch("src.collectors.playstore_collector.reviews")
def test_playstore_collector_handles_empty_and_network_error(mock_reviews):
    # Test network exception is caught gracefully
    mock_reviews.side_effect = Exception("Network connection timeout")

    collector = PlayStoreCollector()
    items = collector.collect_snapshot(limit=10)

    assert items == []

