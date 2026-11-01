"""
Unit tests for src/query/vector_search.py using in-memory ChromaDB client.
"""

import pytest

from src.models.schemas import Emotion, Outcome, Segment, StructuredRecord
from src.query.vector_search import VectorSearch


@pytest.fixture
def vector_search():
    return VectorSearch(in_memory=True)


def test_vector_search_index_and_retrieve(vector_search):
    """Test indexing evidence spans and retrieving semantically similar items."""
    recs = [
        StructuredRecord(
            record_id="rec_v1",
            raw_id="raw_v1",
            groww_specific=True,
            lifecycle_stage="month 0 to 1",
            behavior=["test"],
            barrier_or_trigger_to_stop="Autopay mandate failed at bank",
            confusion_or_worry_in_app="why was penalty charged",
            expectation="seamless autopay",
            checking_behavior="unknown",
            outside_app_behavior="unknown",
            emotion=Emotion.ANGER,
            segment=Segment(),
            outcome=Outcome.STOPPED,
            evidence_span="My bank autopay bounced and they deducted ₹500 penalty charges",
        ),
        StructuredRecord(
            record_id="rec_v2",
            raw_id="raw_v2",
            groww_specific=False,
            lifecycle_stage="months 2 to 3",
            behavior=["test"],
            barrier_or_trigger_to_stop="Negative returns in first quarter",
            confusion_or_worry_in_app="portfolio in red",
            expectation="positive returns",
            checking_behavior="unknown",
            outside_app_behavior="unknown",
            emotion=Emotion.DISAPPOINTMENT,
            segment=Segment(),
            outcome=Outcome.PAUSED,
            evidence_span="After 3 months of monthly SIP, my total returns were minus 4 percent so I paused",
        ),
    ]

    count = vector_search.index_evidence_spans(recs)
    assert count == 2
    assert vector_search.count() == 2

    # Query autopay
    results = vector_search.search("autopay bounce bank penalty", top_k=1)
    assert len(results) == 1
    assert results[0]["record_id"] == "rec_v1"
    assert "penalty" in results[0]["evidence_span"].lower()

    # Query returns
    results2 = vector_search.search("negative returns after 3 months", top_k=1)
    assert len(results2) == 1
    assert results2[0]["record_id"] == "rec_v2"
    assert "minus 4" in results2[0]["evidence_span"].lower()

