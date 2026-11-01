"""
tests/test_extraction/test_run_extraction.py — Tests for run_extraction CLI runner.
"""

import json
from unittest.mock import MagicMock, patch

from scripts.run_extraction import load_filtered_items_from_db, run_extraction_pipeline
from src.db.connection import init_db, insert_filtered_item, insert_raw_item
from src.models.schemas import ExtractionStatus, RawItem, RawItemMetadata, SourceType


def _insert_sample_filtered_item(conn, raw_id: str, text: str, source: str = "reddit"):
    item = RawItem(
        raw_id=raw_id,
        source=SourceType(source),
        source_native_id=f"native_{raw_id}",
        source_url=f"https://example.com/{raw_id}",
        platform_mentioned=["groww"],
        text=text,
        metadata=RawItemMetadata(),
    )
    insert_raw_item(conn, item)
    insert_filtered_item(conn, item, groww_specific=True)


def test_load_filtered_items_from_db(tmp_path):
    db_file = tmp_path / "test_extract.db"
    conn = init_db(str(db_file))

    _insert_sample_filtered_item(conn, "item_1", "Text about SIP 1", "reddit")
    _insert_sample_filtered_item(conn, "item_2", "Text about SIP 2", "playstore")

    items = load_filtered_items_from_db(conn)
    assert len(items) == 2
    assert items[0].raw_id == "item_1"
    conn.close()


@patch("scripts.run_extraction.StructuredExtractor")
def test_run_extraction_pipeline(mock_extractor_cls, tmp_path):
    db_file = tmp_path / "test_pipeline.db"
    conn = init_db(str(db_file))

    _insert_sample_filtered_item(conn, "item_a", "First SIP review", "reddit")
    conn.close()

    mock_record = MagicMock()
    mock_record.record_id = "rec_001"
    mock_record.raw_id = "item_a"
    mock_record.groww_specific = True
    mock_record.lifecycle_stage.value = "months 2 to 3"
    mock_record.behavior = ["stopped SIP"]
    mock_record.driver_to_start = "peer"
    mock_record.expectation = "returns"
    mock_record.barrier_or_trigger_to_stop = "market drop"
    mock_record.confusion_or_worry_in_app = "XIRR"
    mock_record.checking_behavior = "daily"
    mock_record.outside_app_behavior = "reddit"
    mock_record.emotion.value = "anxiety"
    mock_record.segment.model_dump_json.return_value = "{}"
    mock_record.outcome.value = "stopped"
    mock_record.evidence_span = "stopped SIP"
    mock_record.confidence.model_dump_json.return_value = "{}"
    mock_record.extracted_at.isoformat.return_value = "2026-11-01T00:00:00"
    mock_record.extraction_status = ExtractionStatus.SUCCESS
    mock_record.model_version = "llama-3.3-70b-versatile"
    mock_record.prompt_version = "v1.0"
    mock_record.model_dump.return_value = {"record_id": "rec_001", "raw_id": "item_a"}

    mock_instance = MagicMock()
    mock_instance.extract_batch.return_value = ([mock_record], {"records_extracted": 1})
    mock_instance.stats = {"success_first_attempt": 1}
    mock_instance.model_version = "llama-3.3-70b-versatile"
    mock_instance.prompt_version = "v1.0"
    mock_extractor_cls.return_value = mock_instance

    metrics = run_extraction_pipeline(
        db_path=str(db_file),
        limit=5,
        workers=1,
        dry_run=False,
    )

    assert metrics["total_items"] == 1
    assert metrics["records_extracted"] == 1
    assert metrics["successful_records"] == 1
