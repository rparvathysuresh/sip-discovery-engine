"""
Unit tests for src/query/query_engine.py.
"""

import tempfile
from pathlib import Path
import pytest

from src.db.connection import init_db, insert_structured_record
from src.models.schemas import Emotion, Outcome, Segment, StructuredRecord
from src.query.query_engine import QueryEngine
from src.query.vector_search import VectorSearch


@pytest.fixture
def query_engine_setup():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    conn = init_db(db_path)

    for i in range(4):
        conn.execute(
            """
            INSERT INTO raw_items (raw_id, source, source_native_id, text_content, collected_at)
            VALUES (?, 'playstore', ?, 'Sample text', '2026-10-01T00:00:00')
            """,
            (f"raw_{i}", f"ps_{i}"),
        )
    conn.commit()

    recs = [
        StructuredRecord(
            record_id=f"rec_{i}",
            raw_id=f"raw_{i}",
            groww_specific=True,
            lifecycle_stage="month 0 to 1",
            behavior=["test"],
            barrier_or_trigger_to_stop="Autopay failed",
            confusion_or_worry_in_app="why was penalty charged",
            expectation="seamless autopay",
            checking_behavior="monthly",
            outside_app_behavior="unknown",
            emotion=Emotion.ANGER,
            segment=Segment(),
            outcome=Outcome.STOPPED if i < 2 else Outcome.CONTINUED,
            evidence_span=f"Bank autopay failed and deducted charges {i}",
        )
        for i in range(4)
    ]

    for r in recs:
        insert_structured_record(conn, r)
    conn.close()

    v_search = VectorSearch(in_memory=True)
    engine = QueryEngine(db_path=db_path, vector_search=v_search, groq_client=False)
    engine.index_evidence()

    yield engine

    engine.close()
    try:
        Path(db_path).unlink(missing_ok=True)
    except Exception:
        pass


def test_query_engine_refusal(query_engine_setup):
    """Test guardrail refusal through query engine."""
    res = query_engine_setup.query("Which mutual fund should I invest in for high returns?")
    assert res.intent == "refusal"
    assert "not to recommend specific funds" in res.answer.lower()
    assert res.total_matching == 0


def test_query_engine_count(query_engine_setup):
    """Test count query through query engine."""
    res = query_engine_setup.query("How many investors mentioned autopay failure?")
    assert res.intent == "count_query"
    assert "Research Findings Analysis" in res.answer
    assert res.total_matching >= 1
    assert res.latency_seconds >= 0.0


def test_query_engine_drill_down(query_engine_setup):
    """Test drill-down query returning evidence spans."""
    res = query_engine_setup.query("Show me evidence for autopay")
    assert res.intent == "drill_down"
    assert len(res.citations) >= 1
    assert "autopay" in res.citations[0]["evidence_span"].lower()

