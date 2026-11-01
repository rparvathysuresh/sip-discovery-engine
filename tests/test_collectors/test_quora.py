"""
Unit tests for QuoraCollector (online HTML/JSON-LD scraping and local dump parsing).
"""

from unittest.mock import MagicMock, patch
from pathlib import Path

from src.collectors.quora_collector import QuoraCollector
from src.models.schemas import SourceType


def test_quora_collector_local_dump_success():
    collector = QuoraCollector(config={"raw_file": "quora_raw/quora_raw.txt"})
    items = collector.collect_snapshot()

    assert len(items) == 5
    for item in items:
        assert item.source == SourceType.QUORA
        assert item.source_native_id.startswith("quora_manual_")
        assert len(item.text) > 30
        assert item.metadata.thread_title is not None
        assert "quora.com" in item.source_url

    # Check first item details
    first = items[0]
    assert first.source_native_id == "quora_manual_1"
    assert "What happens if I stop my SIP in Groww app?" in first.metadata.thread_title
    assert "groww" in first.platform_mentioned
    assert "existing units remain invested" in first.text


def test_quora_collector_local_dump_limit():
    collector = QuoraCollector(config={"raw_file": "quora_raw/quora_raw.txt"})
    items = collector.collect_snapshot(limit=2)
    assert len(items) == 2
    assert items[0].source_native_id == "quora_manual_1"
    assert items[1].source_native_id == "quora_manual_2"


@patch("src.collectors.quora_collector.requests.get")
def test_quora_collector_online_json_ld(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = """
    <html>
      <head>
        <script type="application/ld+json">
        {
          "@context": "https://schema.org",
          "@type": "Question",
          "name": "Why did my Groww SIP fail on the 5th?",
          "acceptedAnswer": {
            "@type": "Answer",
            "text": "<p>Groww requires the bank account to maintain sufficient balance on debit date.</p>"
          }
        }
        </script>
      </head>
      <body></body>
    </html>
    """
    mock_get.return_value = mock_resp

    collector = QuoraCollector(
        config={
            "search_queries": ["Why did my Groww SIP fail"],
            "raw_file": "nonexistent.txt",
        }
    )

    items = collector.collect_snapshot(limit=5)
    assert len(items) == 1
    assert items[0].source == SourceType.QUORA
    assert items[0].metadata.thread_title == "Why did my Groww SIP fail on the 5th?"
    assert "groww" in items[0].platform_mentioned
    assert "Groww requires the bank account" in items[0].text
    assert items[0].metadata.extra["format"] == "json_ld"


@patch("src.collectors.quora_collector.requests.get")
def test_quora_collector_online_html_fallback(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = """
    <html>
      <head>
        <title>Is Groww safe for first time SIP investing? - Quora</title>
      </head>
      <body>
        <div class="q-content">
          <p>Groww is a registered stock broker and AMFI registered mutual fund distributor.</p>
          <p>Your mutual fund folios are held directly with the respective AMC.</p>
        </div>
      </body>
    </html>
    """
    mock_get.return_value = mock_resp

    collector = QuoraCollector(
        config={
            "search_queries": ["Is Groww safe for first time SIP"],
            "raw_file": "nonexistent.txt",
        }
    )

    items = collector.collect_snapshot(limit=5)
    assert len(items) == 1
    assert items[0].source == SourceType.QUORA
    assert items[0].metadata.thread_title == "Is Groww safe for first time SIP investing?"
    assert "groww" in items[0].platform_mentioned
    assert "AMFI registered mutual fund distributor" in items[0].text


@patch("src.collectors.quora_collector.requests.get")
def test_quora_collector_error_fallback(mock_get, tmp_path):
    mock_get.side_effect = Exception("HTTP 403 Forbidden")

    dump_file = tmp_path / "quora_raw.txt"
    dump_file.write_text(
        "1. Can I pause SIP for 6 months on Groww?\n"
        "You can skip up to 2 installments before the AMC cancels the mandate.",
        encoding="utf-8",
    )

    collector = QuoraCollector(
        config={
            "search_queries": ["SIP"],
            "raw_file": str(dump_file),
        }
    )

    items = collector.collect_snapshot(limit=5)
    assert len(items) == 1
    assert items[0].source == SourceType.QUORA
    assert items[0].source_native_id == "quora_manual_1"


def test_quora_collector_empty_result(tmp_path):
    collector = QuoraCollector(
        config={
            "raw_file": str(tmp_path / "nonexistent.txt"),
            "raw_dir": str(tmp_path / "empty_dir"),
        }
    )
    items = collector.collect_snapshot()
    assert items == []

