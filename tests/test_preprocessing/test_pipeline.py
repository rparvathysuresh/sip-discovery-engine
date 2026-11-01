"""
Unit tests for scripts/run_preprocessing.py end-to-end pipeline.
"""

import sqlite3
from pathlib import Path

from scripts.run_preprocessing import run_preprocessing_pipeline
from src.db.connection import init_db, insert_raw_item
from src.models.schemas import RawItem, RawItemMetadata, SourceType


def test_preprocessing_pipeline_end_to_end(tmp_path):
    db_file = tmp_path / "test_pipeline.db"
    out_file = tmp_path / "filtered.json"

    # Populate raw_items in the test database
    conn = init_db(str(db_file))

    raw_samples = [
        # 1. Legitimate Groww SIP item with PII
        RawItem(
            raw_id="raw_1",
            source=SourceType.REDDIT,
            source_native_id="r1",
            text="Started monthly SIP on Groww app for 5k. My email is user@example.com and PAN is ABCDE1234F.",
            metadata=RawItemMetadata(),
        ),
        # 2. Duplicate of item 1
        RawItem(
            raw_id="raw_2",
            source=SourceType.REDDIT,
            source_native_id="r2",
            text="Started monthly SIP on Groww app for 5k. My email is user@example.com and PAN is ABCDE1234F.",
            metadata=RawItemMetadata(),
        ),
        # 3. Spam item
        RawItem(
            raw_id="raw_3",
            source=SourceType.PLAYSTORE,
            source_native_id="r3",
            text="Join telegram channel for 100% daily profit jackpot calls!",
            metadata=RawItemMetadata(),
        ),
        # 4. Irrelevant crypto item
        RawItem(
            raw_id="raw_4",
            source=SourceType.REDDIT,
            source_native_id="r4",
            text="How to trade crypto trading futures and call options bot on Binance",
            metadata=RawItemMetadata(),
        ),
        # 5. Competitor-only item (mentions SIP, but purely about competitor app crash)
        RawItem(
            raw_id="raw_5",
            source=SourceType.FORUM,
            source_native_id="r5",
            text="Zerodha support not responding to my coin portal and kite app error for my active SIP",
            metadata=RawItemMetadata(),
        ),
        # 6. Platform agnostic SIP item
        RawItem(
            raw_id="raw_6",
            source=SourceType.FORUM,
            source_native_id="r6",
            text="How do I pause my mutual fund SIP for two months without cancellation penalty?",
            metadata=RawItemMetadata(),
        ),
    ]

    for it in raw_samples:
        insert_raw_item(conn, it)
    conn.close()

    metrics = run_preprocessing_pipeline(
        db_path=str(db_file),
        output_file=str(out_file),
        use_llm=False,
        dry_run=False,
    )

    assert metrics["total_collected"] == 6
    assert metrics["duplicates_removed"] == 1
    assert metrics["spam_removed"] == 1
    assert metrics["pii_redacted_items"] == 1
    assert metrics["irrelevant_removed"] == 1
    assert metrics["competitor_removed"] == 1
    assert metrics["corpus_retained"] == 2
    assert metrics["groww_specific_count"] == 1
    assert metrics["platform_agnostic_count"] == 1

    # Verify database persistence
    conn = sqlite3.connect(str(db_file))
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM filtered_items")
    assert cursor.fetchone()[0] == 2

    # Verify PII is redacted in filtered database output
    cursor.execute("SELECT text_content FROM filtered_items WHERE raw_id = 'raw_1'")
    text_content = cursor.fetchone()[0]
    assert "[EMAIL]" in text_content
    assert "[PAN]" in text_content
    assert "user@example.com" not in text_content
    assert "ABCDE1234F" not in text_content

    # Verify evidence log recorded
    cursor.execute("SELECT COUNT(*) FROM evidence_log WHERE pipeline_stage = 'preprocessing'")
    assert cursor.fetchone()[0] == 1
    conn.close()

    # Verify JSON export
    assert out_file.exists()
