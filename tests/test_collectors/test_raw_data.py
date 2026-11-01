"""
tests/test_collectors/test_raw_data.py — Unit tests for RawDataCollector.
"""

from pathlib import Path
from src.collectors.raw_data_collector import RawDataCollector, parse_raw_data_file
from src.models.schemas import SourceType


def test_parse_raw_data_file_full_dataset():
    """Verify all 300 items from raw_data/raw_data.txt parse cleanly."""
    file_path = Path("raw_data/raw_data.txt")
    assert file_path.is_file()

    items = parse_raw_data_file(file_path)
    assert len(items) == 300

    # Ensure native IDs are formatted properly from 001 to 300
    assert items[0].source_native_id == "manual_raw_001"
    assert items[-1].source_native_id == "manual_raw_300"

    # Verify source distributions
    sources = [item.source for item in items]
    assert SourceType.REDDIT in sources
    assert SourceType.PLAYSTORE in sources
    assert SourceType.QUORA in sources
    assert SourceType.YOUTUBE in sources
    assert SourceType.TWITTER in sources
    assert SourceType.APPSTORE in sources

    # Check that each item has substantial text and platform tagging
    for item in items:
        assert len(item.text) >= 20
        assert "groww" in item.platform_mentioned
        assert item.source_url is not None
        assert item.metadata is not None
        assert item.metadata.extra.get("manual_collection") is True


def test_raw_data_collector_limit():
    collector = RawDataCollector(config={"raw_file": "raw_data/raw_data.txt"})
    items = collector.collect_snapshot(limit=10)
    assert len(items) == 10
    assert items[0].source_native_id == "manual_raw_001"
    assert items[9].source_native_id == "manual_raw_010"


def test_parse_raw_data_file_missing(tmp_path):
    missing_file = tmp_path / "non_existent.txt"
    items = parse_raw_data_file(missing_file)
    assert items == []


def test_parse_raw_data_synthetic_content(tmp_path):
    sample_file = tmp_path / "sample.txt"
    sample_file.write_text(
        """#001
Reddit (r/mutualfunds)
"How do I cancel my SIP on Groww without losing my past returns?"
Groww SIP User Feedback (Raw Dataset)
Page 1 of 1
#002
Quora
"Is it safe to invest in SIP via Groww?"
""",
        encoding="utf-8",
    )
    items = parse_raw_data_file(sample_file)
    assert len(items) == 2
    assert items[0].source == SourceType.REDDIT
    assert items[0].metadata.subreddit == "r/mutualfunds"
    assert "How do I cancel my SIP" in items[0].text
    assert "Groww SIP User Feedback" not in items[0].text
    assert items[1].source == SourceType.QUORA
    assert "Is it safe to invest in SIP" in items[1].text

