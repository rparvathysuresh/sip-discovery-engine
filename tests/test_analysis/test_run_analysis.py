"""
Unit tests for scripts/run_analysis.py pipeline runner.
"""

import tempfile
from pathlib import Path
import pytest

from scripts.run_analysis import run_analysis_pipeline
from src.db.connection import get_connection, init_db, insert_structured_record
from src.models.schemas import Emotion, Outcome, Segment, StructuredRecord


@pytest.fixture
def temp_db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    conn = init_db(db_path)

    # Insert sample raw items and structured records
    conn.execute(
        """
        INSERT INTO raw_items (raw_id, source, source_native_id, text_content, collected_at)
        VALUES ('raw_1', 'reddit', 'sub_1', 'SIP returns negative after 3 months', '2026-10-01T00:00:00'),
               ('raw_2', 'playstore', 'ps_1', 'Autopay failed and bank penalty charged', '2026-10-02T00:00:00')
        """
    )
    conn.commit()

    rec1 = StructuredRecord(
        record_id="rec_1",
        raw_id="raw_1",
        groww_specific=True,
        lifecycle_stage="months 2 to 3",
        behavior=["checking returns"],
        barrier_or_trigger_to_stop="SIP returns negative",
        confusion_or_worry_in_app="why portfolio negative",
        expectation="positive returns",
        checking_behavior="daily",
        outside_app_behavior="seeking advice on reddit",
        emotion=Emotion.DISAPPOINTMENT,
        segment=Segment(),
        outcome=Outcome.STOPPED,
        evidence_span="SIP returns negative after 3 months",
    )

    rec2 = StructuredRecord(
        record_id="rec_2",
        raw_id="raw_2",
        groww_specific=True,
        lifecycle_stage="month 0 to 1",
        behavior=["setup autopay"],
        barrier_or_trigger_to_stop="Autopay failed",
        confusion_or_worry_in_app="bank penalty charged",
        expectation="seamless deduction",
        checking_behavior="monthly",
        outside_app_behavior="contacted support",
        emotion=Emotion.ANGER,
        segment=Segment(),
        outcome=Outcome.PAUSED,
        evidence_span="Autopay failed and bank penalty charged",
    )

    insert_structured_record(conn, rec1)
    insert_structured_record(conn, rec2)
    conn.close()

    yield db_path

    # Cleanup
    try:
        Path(db_path).unlink(missing_ok=True)
    except Exception:
        pass


def test_run_analysis_pipeline_integration(temp_db, tmp_path):
    """Test full analysis pipeline integration with SQLite DB."""
    out_dir = tmp_path / "data_out"

    results = run_analysis_pipeline(
        db_path=temp_db,
        output_dir=str(out_dir),
        dry_run=False,
    )

    assert results["total_records"] == 2
    assert results["coverage"]["coverage_pct"] > 0
    assert len(results["opportunity_areas"]) >= 1

    # Verify output files exist
    assert (out_dir / "opportunity_areas.json").is_file()
    assert (out_dir / "opportunity_areas.csv").is_file()
    assert (out_dir / "continuer_vs_dropper.json").is_file()
    assert (out_dir / "segment_aggregations.json").is_file()
    assert (out_dir / "analysis_summary.md").is_file()

    # Verify opportunity_areas table in DB was populated
    conn = get_connection(temp_db)
    count = conn.execute("SELECT COUNT(*) FROM opportunity_areas").fetchone()[0]
    assert count >= 1

    # Verify evidence_log table
    ev_count = conn.execute("SELECT COUNT(*) FROM evidence_log WHERE pipeline_stage = 'analysis'").fetchone()[0]
    assert ev_count >= 1
    conn.close()
