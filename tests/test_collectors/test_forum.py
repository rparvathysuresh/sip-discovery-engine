"""
Unit tests for ForumCollector (TradingQnA Discourse API and Value Research RSS).
"""

from unittest.mock import MagicMock, patch

from src.collectors.forum_collector import ForumCollector
from src.models.schemas import SourceType


@patch("src.collectors.forum_collector.requests.get")
def test_forum_collector_tradingqna_success(mock_get):
    tqna_resp = MagicMock()
    tqna_resp.status_code = 200
    tqna_resp.json.return_value = {
        "posts": [
            {
                "id": 136312,
                "topic_id": 47128,
                "post_number": 1,
                "blurb": "Should I just cancel the bank mandate or will doing so involve penalties on Groww?",
                "username": "ron94",
                "created_at": "2024-03-01T10:00:00Z",
            }
        ],
        "topics": [
            {
                "id": 47128,
                "title": "Whats the easiest way to stop sip in regular fund?",
                "slug": "whats-the-easiest-way-to-stop-sip",
            }
        ],
    }

    vr_resp = MagicMock()
    vr_resp.status_code = 200
    vr_resp.content = b'<?xml version="1.0"?><rss><channel></channel></rss>'

    mock_get.side_effect = [tqna_resp, vr_resp]

    collector = ForumCollector(
        config={
            "tradingqna": {"search_queries": ["SIP stop"]},
            "valueresearch": {"search_queries": []},
        }
    )

    items = collector.collect_snapshot(limit=5)

    assert len(items) == 1
    item = items[0]
    assert item.source == SourceType.FORUM
    assert item.source_native_id == "tradingqna_136312"
    assert "https://tradingqna.com/t/whats-the-easiest-way-to-stop-sip/47128/1" in item.source_url
    assert "Whats the easiest way to stop sip in regular fund?" in item.text
    assert "penalties on Groww" in item.text
    assert "groww" in item.platform_mentioned
    assert item.metadata.thread_title == "Whats the easiest way to stop sip in regular fund?"
    assert item.metadata.extra["forum"] == "tradingqna"
    assert item.metadata.extra["username"] == "ron94"


@patch("src.collectors.forum_collector.requests.get")
def test_forum_collector_valueresearch_rss(mock_get):
    # TradingQnA returns empty
    tqna_resp = MagicMock()
    tqna_resp.status_code = 200
    tqna_resp.json.return_value = {"posts": [], "topics": []}

    # Value Research returns valid RSS XML
    vr_resp = MagicMock()
    vr_resp.status_code = 200
    vr_resp.content = b"""<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0">
      <channel>
        <item>
          <title>10 Years of SIP investing</title>
          <link>https://www.valueresearchonline.com/stories/230017/10-years-of-sip/</link>
          <description>Groww and other platforms have popularized SIPs among youth.</description>
          <pubDate>Fri, 30 Oct 2026 16:00:00 +0530</pubDate>
        </item>
      </channel>
    </rss>
    """

    mock_get.side_effect = [tqna_resp, vr_resp]

    collector = ForumCollector(
        config={
            "tradingqna": {"search_queries": ["SIP"]},
            "valueresearch": {"search_queries": ["SIP"]},
        }
    )

    items = collector.collect_snapshot(limit=5)

    assert len(items) == 1
    item = items[0]
    assert item.source == SourceType.FORUM
    assert item.source_native_id == "valueresearch_230017"
    assert "10 Years of SIP investing" in item.metadata.thread_title
    assert "Groww and other platforms" in item.text
    assert "groww" in item.platform_mentioned
    assert item.metadata.extra["forum"] == "valueresearch"
    assert item.published_at is not None


@patch("src.collectors.forum_collector.requests.get")
def test_forum_collector_fallback_to_local_dump(mock_get, tmp_path):
    mock_get.side_effect = Exception("Network unreachable")

    dump_file = tmp_path / "forum_raw.txt"
    dump_file.write_text(
        "Stopping SIP vs Pausing SIP on Zerodha Coin and Groww\n"
        "If you pause your SIP for more than 3 months, will the AMC cancel the folio?\n\n---\n\n"
        "How to avoid NACH mandate bounce charges\n"
        "Always maintain minimum balance on SIP debit date.",
        encoding="utf-8",
    )

    collector = ForumCollector(
        config={
            "raw_file": str(dump_file),
        }
    )

    items = collector.collect_snapshot(limit=10)

    assert len(items) == 2
    assert items[0].source == SourceType.FORUM
    assert items[0].source_native_id == "forum_manual_0"
    assert "Stopping SIP vs Pausing SIP" in items[0].text
    assert items[1].source_native_id == "forum_manual_1"


@patch("src.collectors.forum_collector.requests.get")
def test_forum_collector_empty_result(mock_get, tmp_path):
    mock_get.side_effect = Exception("Connection refused")

    collector = ForumCollector(
        config={
            "raw_file": str(tmp_path / "nonexistent.txt"),
        }
    )

    items = collector.collect_snapshot()
    assert items == []

