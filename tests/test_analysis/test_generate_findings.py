"""
Unit tests for scripts/generate_findings.py findings generator.
"""

import tempfile
from pathlib import Path
import pytest

from scripts.generate_findings import generate_findings_report, query_data_scope
from src.db.connection import get_connection, init_db, insert_opportunity_area, insert_structured_record
from src.models.schemas import Emotion, OpportunityArea, Outcome, Segment, StructuredRecord


@pytest.fixture
def sample_findings_db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    conn = init_db(db_path)

    # Insert raw_items first to satisfy foreign key constraint
    conn.execute(
        """
        INSERT INTO raw_items (raw_id, source, source_native_id, text_content, collected_at)
        VALUES ('raw_1', 'reddit', 'sub_1', 'SIP returns negative after 3 months', '2026-10-01T00:00:00'),
               ('raw_2', 'playstore', 'ps_1', 'Autopay failed and bank penalty charged', '2026-10-02T00:00:00'),
               ('raw_3', 'quora', 'q_1', 'General query on mutual funds', '2026-10-03T00:00:00')
        """
    )
    # Insert sample filtered items
    conn.execute(
        """
        INSERT INTO filtered_items (raw_id, source, source_native_id, text_content, groww_specific, processed_at)
        VALUES ('raw_1', 'reddit', 'sub_1', 'SIP returns negative after 3 months', 1, '2026-10-01T00:00:00'),
               ('raw_2', 'playstore', 'ps_1', 'Autopay failed and bank penalty charged', 1, '2026-10-02T00:00:00'),
               ('raw_3', 'quora', 'q_1', 'General query on mutual funds', 0, '2026-10-03T00:00:00')
        """
    )
    conn.commit()

    # Insert structured records
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
        outcome=Outcome.CONTINUED,
        evidence_span="Autopay failed and bank penalty charged",
    )
    insert_structured_record(conn, rec1)
    insert_structured_record(conn, rec2)

    # Insert opportunity area
    area = OpportunityArea(
        theme_name="Autopay Failure",
        theme_category="Lifecycle Friction",
        frequency_count=2,
        frequency_share=1.0,
        severity_score=0.5,
        breadth_score=0.4,
        composite_score=0.68,
        sufficient_evidence=False,
        evidence_level="insufficient",
    )
    insert_opportunity_area(conn, area)
    conn.close()

    yield db_path

    try:
        Path(db_path).unlink(missing_ok=True)
    except Exception:
        pass


def test_query_data_scope(sample_findings_db):
    conn = get_connection(sample_findings_db)
    scope = query_data_scope(conn)
    conn.close()

    assert scope["filtered_count"] == 3
    assert scope["raw_count"] == 3
    assert scope["structured_count"] == 2
    assert scope["groww_count"] == 2
    assert scope["agnostic_count"] == 1


def test_generate_findings_report(sample_findings_db, tmp_path):
    out_file = tmp_path / "research-findings-summary.md"
    res = generate_findings_report(db_path=sample_findings_db, output_path=str(out_file))

    assert res["placeholders_remaining"] is False
    assert out_file.is_file()

    content = out_file.read_text(encoding="utf-8")
    assert "# Research Findings Summary" in content
    assert "## Data Scope" in content
    assert "## Ranked Opportunity Areas" in content
    assert "## Continuer vs. Dropper Comparison" in content
    assert "## Groww-Specific vs. Platform-Agnostic Split" in content
    assert "## Source Mix Analysis" in content
    assert "_(auto-populated)_" not in content
