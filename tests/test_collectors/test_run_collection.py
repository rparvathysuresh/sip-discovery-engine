"""
Unit tests for scripts/run_collection.py orchestration runner.
"""

import sqlite3
from unittest.mock import MagicMock, patch

import pytest

from scripts.run_collection import run_collection
from src.models.schemas import RawItem, RawItemMetadata, SourceType


def _make_dummy_item(source: SourceType, native_id: str, text: str) -> RawItem:
    return RawItem(
        source=source,
        source_native_id=native_id,
        source_url=f"https://example.com/{native_id}",
        platform_mentioned=["groww"],
        text=text,
        metadata=RawItemMetadata(thread_title=text[:20]),
    )


@patch("scripts.run_collection.COLLECTOR_REGISTRY")
def test_run_collection_orchestration(mock_registry, tmp_path):
    db_file = tmp_path / "test_collection.db"

    # Create mock collectors
    mock_playstore = MagicMock()
    mock_playstore.return_value.collect_snapshot.return_value = [
        _make_dummy_item(SourceType.PLAYSTORE, "ps_1", "Play store review on groww"),
        _make_dummy_item(SourceType.PLAYSTORE, "ps_2", "Second play store review"),
    ]

    mock_reddit = MagicMock()
    mock_reddit.return_value.collect_snapshot.return_value = [
        _make_dummy_item(SourceType.REDDIT, "rd_1", "Reddit post about SIP stop"),
    ]

    mock_registry.__getitem__.side_effect = lambda k: {
        "playstore": mock_playstore,
        "reddit": mock_reddit,
    }[k]
    mock_registry.__contains__.side_effect = lambda k: k in ["playstore", "reddit"]
    mock_registry.keys.return_value = ["playstore", "reddit"]

    stats = run_collection(
        sources=["playstore", "reddit"],
        limit_per_source=5,
        db_path=str(db_file),
        dry_run=False,
    )

    assert stats["total_collected"] == 3
    assert stats["total_inserted"] == 3
    assert stats["total_duplicates_skipped"] == 0
    assert stats["db_total_raw_items"] == 3

    # Verify database contents directly
    conn = sqlite3.connect(str(db_file))
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM raw_items")
    assert cursor.fetchone()[0] == 3

    cursor.execute("SELECT COUNT(*) FROM evidence_log WHERE pipeline_stage = 'collection'")
    assert cursor.fetchone()[0] == 1
    conn.close()


@patch("scripts.run_collection.COLLECTOR_REGISTRY")
def test_run_collection_deduplication(mock_registry, tmp_path):
    db_file = tmp_path / "test_dedup.db"

    mock_forum = MagicMock()
    # Return duplicate item
    mock_forum.return_value.collect_snapshot.return_value = [
        _make_dummy_item(SourceType.FORUM, "forum_1", "First post on SIP"),
        _make_dummy_item(SourceType.FORUM, "forum_1", "First post duplicate"),
    ]

    mock_registry.__getitem__.return_value = mock_forum
    mock_registry.__contains__.return_value = True

    stats = run_collection(
        sources=["forum"],
        db_path=str(db_file),
        dry_run=False,
    )

    assert stats["total_collected"] == 2
    assert stats["total_inserted"] == 1
    assert stats["total_duplicates_skipped"] == 1
    assert stats["db_total_raw_items"] == 1


def test_run_collection_invalid_source():
    with pytest.raises(ValueError, match="Unknown source 'invalid_source'"):
        run_collection(sources=["invalid_source"])


@patch("scripts.run_collection.COLLECTOR_REGISTRY")
def test_run_collection_dry_run(mock_registry, tmp_path):
    db_file = tmp_path / "dry_run.db"

    mock_collector = MagicMock()
    mock_collector.return_value.collect_snapshot.return_value = [
        _make_dummy_item(SourceType.APPSTORE, "as_1", "App Store review on groww"),
    ]
    mock_registry.__getitem__.return_value = mock_collector
    mock_registry.__contains__.return_value = True

    stats = run_collection(
        sources=["appstore"],
        db_path=str(db_file),
        dry_run=True,
    )

    assert stats["total_collected"] == 1
    assert stats["dry_run"] is True
    # In dry run mode, items are not written to DB
    conn = sqlite3.connect(str(db_file))
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM raw_items")
    assert cursor.fetchone()[0] == 0
    conn.close()

