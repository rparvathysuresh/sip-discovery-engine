"""
Tests for SQLite database operations in src/db/connection.py.
"""

from datetime import datetime
import pytest

from src.db.connection import (
    check_db_integrity,
    count_raw_items,
    count_structured_records,
    get_corpus_stats,
    get_table_names,
    init_db,
    insert_evidence_log_entry,
    insert_opportunity_area,
    insert_raw_item,
    insert_structured_record,
    raw_item_exists,
    structured_record_exists,
)
from src.models.schemas import (
    Emotion,
    EvidenceLogEntry,
    LifecycleStage,
    OpportunityArea,
    Outcome,
    RawItem,
    RawItemMetadata,
    SourceType,
    StructuredRecord,
)


def test_init_db_creates_expected_tables(test_db):
    assert check_db_integrity(test_db) is True
    tables = get_table_names(test_db)
    for expected in ["raw_items", "structured_records", "opportunity_areas", "evidence_log"]:
        assert expected in tables


def test_insert_and_count_raw_item(test_db):
    item = RawItem(
        source=SourceType.REDDIT,
        source_native_id="reddit_abc123",
        source_url="https://reddit.com/r/mutualfunds/abc123",
        platform_mentioned=["groww"],
        text="Sample post about stopping SIP due to emergency expenses.",
        metadata=RawItemMetadata(subreddit="mutualfunds"),
    )

    inserted = insert_raw_item(test_db, item)
    assert inserted is True
    assert count_raw_items(test_db) == 1
    assert raw_item_exists(test_db, SourceType.REDDIT.value, "reddit_abc123") is True
    assert raw_item_exists(test_db, SourceType.REDDIT.value, "non_existent") is False

    # Inserting the exact same (source, source_native_id) should be ignored
    inserted_dup = insert_raw_item(test_db, item)
    assert inserted_dup is False
    assert count_raw_items(test_db) == 1


def test_insert_and_count_structured_record(test_db):
    raw_item = RawItem(
        source=SourceType.PLAYSTORE,
        source_native_id="play_rev_456",
        text="App is good but XIRR confuses me so I paused my monthly SIP.",
        platform_mentioned=["groww"],
    )
    insert_raw_item(test_db, raw_item)

    record = StructuredRecord(
        raw_id=raw_item.raw_id,
        groww_specific=True,
        lifecycle_stage=LifecycleStage.MONTHS_2_3,
        behavior=["pauses SIP"],
        confusion_or_worry_in_app="XIRR calculation",
        emotion=Emotion.DISAPPOINTMENT,
        outcome=Outcome.PAUSED,
        evidence_span="XIRR confuses me so I paused my monthly SIP",
    )
    insert_structured_record(test_db, record)

    assert count_structured_records(test_db) == 1
    assert structured_record_exists(test_db, raw_item.raw_id) is True
    assert structured_record_exists(test_db, "non_existent_raw_id") is False


def test_insert_opportunity_area(test_db):
    area = OpportunityArea(
        theme_name="XIRR Misunderstanding",
        theme_category="Comprehension",
        frequency_count=35,
        frequency_share=0.035,
        severity_score=0.70,
        breadth_score=0.80,
        composite_score=0.67,
        sufficient_evidence=True,
        evidence_level="sufficient",
    )
    insert_opportunity_area(test_db, area)

    row = test_db.execute("SELECT * FROM opportunity_areas WHERE theme_name = ?", ("XIRR Misunderstanding",)).fetchone()
    assert row is not None
    assert row["frequency_count"] == 35
    assert row["sufficient_evidence"] == 1


def test_insert_evidence_log(test_db):
    entry = EvidenceLogEntry(
        pipeline_stage="collection",
        event_type="playstore_run_complete",
        details={"total_fetched": 1500, "valid_retained": 1420},
    )
    insert_evidence_log_entry(test_db, entry)

    row = test_db.execute("SELECT * FROM evidence_log WHERE event_type = ?", ("playstore_run_complete",)).fetchone()
    assert row is not None
    assert row["pipeline_stage"] == "collection"


def test_get_corpus_stats(test_db):
    # Empty DB stats
    stats_empty = get_corpus_stats(test_db)
    assert stats_empty["total_items"] == 0
    assert stats_empty["groww_specific_count"] == 0

    # Insert items
    raw_item1 = RawItem(
        source=SourceType.REDDIT,
        source_native_id="r1",
        published_at=datetime(2025, 1, 15, 10, 0, 0),
        text="Groww SIP stopped",
    )
    raw_item2 = RawItem(
        source=SourceType.PLAYSTORE,
        source_native_id="p1",
        published_at=datetime(2025, 2, 20, 10, 0, 0),
        text="Agnostic SIP dropped",
    )
    insert_raw_item(test_db, raw_item1)
    insert_raw_item(test_db, raw_item2)

    rec1 = StructuredRecord(raw_id=raw_item1.raw_id, groww_specific=True)
    rec2 = StructuredRecord(raw_id=raw_item2.raw_id, groww_specific=False)
    insert_structured_record(test_db, rec1)
    insert_structured_record(test_db, rec2)

    stats = get_corpus_stats(test_db)
    assert stats["total_items"] == 2
    assert stats["groww_specific_count"] == 1
    assert stats["platform_agnostic_count"] == 1
    assert "reddit" in stats["sources"]
    assert "playstore" in stats["sources"]

