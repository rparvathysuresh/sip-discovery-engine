"""
Unit tests for src/query/sql_builder.py.
"""

import tempfile
from pathlib import Path
import pytest

from src.db.connection import init_db, insert_structured_record
from src.models.schemas import Emotion, Outcome, Segment, StructuredRecord
from src.query.intent_classifier import IntentClassifier, IntentType, QueryIntent
from src.query.sql_builder import SQLBuilder


@pytest.fixture
def test_db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    conn = init_db(db_path)

    for i in range(5):
        conn.execute(
            """
            INSERT INTO raw_items (raw_id, source, source_native_id, text_content, collected_at)
            VALUES (?, 'reddit', ?, 'Sample text', '2026-10-01T00:00:00')
            """,
            (f"raw_{i}", f"sub_{i}"),
        )
    conn.commit()

    recs = [
        StructuredRecord(
            record_id=f"rec_{i}",
            raw_id=f"raw_{i}",
            groww_specific=True,
            lifecycle_stage="months 2 to 3" if i % 2 == 0 else "month 0 to 1",
            behavior=["test"],
            barrier_or_trigger_to_stop="Autopay failed" if i < 3 else "negative returns",
            confusion_or_worry_in_app="none",
            expectation="none",
            checking_behavior="monthly",
            outside_app_behavior="none",
            emotion=Emotion.DISAPPOINTMENT if i < 3 else Emotion.CONFIDENCE,
            segment=Segment(),
            outcome=Outcome.STOPPED if i < 3 else Outcome.CONTINUED,
            evidence_span=f"Evidence {i}",
        )
        for i in range(5)
    ]

    for r in recs:
        insert_structured_record(conn, r)

    yield conn

    conn.close()
    try:
        Path(db_path).unlink(missing_ok=True)
    except Exception:
        pass


def test_sql_builder_count(test_db):
    builder = SQLBuilder(conn=test_db)
    intent = QueryIntent(
        intent_type=IntentType.COUNT,
        raw_query="How many stopped?",
        filters={"outcome": "stopped"},
    )
    res = builder.build_and_execute(intent)
    assert res["total_matching"] == 3
    assert len(res["results"]) >= 1


def test_sql_builder_comparison(test_db):
    builder = SQLBuilder(conn=test_db)
    intent = QueryIntent(
        intent_type=IntentType.COMPARISON,
        raw_query="Compare continuers vs droppers",
    )
    res = builder.build_and_execute(intent)
    assert res["total_matching"] == 5
    assert res["group_totals"]["continuers"] == 2
    assert res["group_totals"]["droppers"] == 3


def test_sql_builder_drill_down(test_db):
    builder = SQLBuilder(conn=test_db)
    intent = QueryIntent(
        intent_type=IntentType.DRILL_DOWN,
        raw_query="Show evidence for autopay",
        theme_focus="autopay",
    )
    res = builder.build_and_execute(intent)
    assert res["total_matching"] >= 1
    assert "evidence_span" in res["results"][0]

