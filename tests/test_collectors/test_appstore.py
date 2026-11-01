"""
Tests for AppStoreCollector with mocked Apple iTunes Customer Reviews JSON API.
"""

from unittest.mock import MagicMock, patch

from src.collectors.appstore_collector import AppStoreCollector
from src.models.schemas import SourceType


@patch("src.collectors.appstore_collector.requests.get")
def test_appstore_collector_success(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "feed": {
            "entry": [
                {
                    # First entry: app metadata, no im:rating
                    "id": {"label": "app_info_metadata"},
                    "title": {"label": "Groww App Info"},
                },
                {
                    # Second entry: actual user review
                    "id": {"label": "ios_rev_9001"},
                    "title": {"label": "Confusing mandate charges"},
                    "content": {"label": "Bank charged 500 rs after SIP bounce, no alert given beforehand."},
                    "im:rating": {"label": "2"},
                    "im:version": {"label": "14.2.0"},
                    "updated": {"label": "2025-04-01T10:15:00Z"},
                },
                {
                    # Third entry: positive continuer review
                    "id": {"label": "ios_rev_9002"},
                    "title": {"label": "Great UI for SIP"},
                    "content": {"label": "Continuing my SIPs for over a year seamlessly on Groww."},
                    "im:rating": {"label": "5"},
                    "im:version": {"label": "14.1.0"},
                    "updated": {"label": "2025-04-02T12:00:00Z"},
                },
            ]
        }
    }
    mock_get.return_value = mock_resp

    collector = AppStoreCollector(config={"app_id": 1404871703, "country": "in", "max_reviews": 10})
    items = collector.collect_snapshot(limit=2)

    assert len(items) == 2
    assert items[0].source == SourceType.APPSTORE
    assert items[0].source_native_id == "ios_rev_9001"
    assert "Confusing mandate charges" in items[0].text
    assert items[0].metadata.rating == 2
    assert items[0].metadata.thread_title == "Confusing mandate charges"
    assert items[0].metadata.extra["app_version"] == "14.2.0"
    assert "groww" in items[0].platform_mentioned
    assert "https://apps.apple.com/in/app/groww/id1404871703" in items[0].source_url

    assert items[1].source_native_id == "ios_rev_9002"
    assert items[1].metadata.rating == 5


@patch("src.collectors.appstore_collector.requests.get")
def test_appstore_collector_pagination(mock_get):
    page1_resp = MagicMock()
    page1_resp.status_code = 200
    page1_resp.json.return_value = {
        "feed": {
            "entry": [
                {
                    "id": {"label": "rev_p1"},
                    "title": {"label": "Page 1 review"},
                    "content": {"label": "Content page 1"},
                    "im:rating": {"label": "4"},
                }
            ]
        }
    }

    page2_resp = MagicMock()
    page2_resp.status_code = 200
    page2_resp.json.return_value = {
        "feed": {
            "entry": [
                {
                    "id": {"label": "rev_p2"},
                    "title": {"label": "Page 2 review"},
                    "content": {"label": "Content page 2"},
                    "im:rating": {"label": "3"},
                }
            ]
        }
    }

    mock_get.side_effect = [page1_resp, page2_resp]

    collector = AppStoreCollector(config={"max_reviews": 2})
    items = collector.collect_snapshot(limit=2)

    assert len(items) == 2
    assert mock_get.call_count == 2
    assert items[0].source_native_id == "rev_p1"
    assert items[1].source_native_id == "rev_p2"


@patch("src.collectors.appstore_collector.requests.get")
def test_appstore_collector_http_error(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 403
    mock_get.return_value = mock_resp

    collector = AppStoreCollector()
    items = collector.collect_snapshot(limit=5)
    assert items == []


@patch("src.collectors.appstore_collector.requests.get")
def test_appstore_collector_network_exception(mock_get):
    mock_get.side_effect = Exception("Connection refused")

    collector = AppStoreCollector()
    items = collector.collect_snapshot(limit=5)
    assert items == []

