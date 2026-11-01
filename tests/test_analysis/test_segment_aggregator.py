"""
Unit tests for src/analysis/segment_aggregator.py.
"""

import pytest

from src.analysis.segment_aggregator import SegmentAggregator
from src.models.schemas import Emotion, Outcome, Segment, StructuredRecord


@pytest.fixture
def aggregator():
    return SegmentAggregator()


def test_segment_aggregator_slices(aggregator):
    recs = [
        StructuredRecord(
            record_id="r1",
            raw_id="raw_1",
            groww_specific=True,
            lifecycle_stage="month 0 to 1",
            behavior=["test"],
            barrier_or_trigger_to_stop="stop",
            confusion_or_worry_in_app="none",
            expectation="unknown",
            checking_behavior="unknown",
            outside_app_behavior="unknown",
            emotion=Emotion.ANXIETY,
            segment=Segment(income_stability="stable_salaried", age_band="25-34"),
            outcome=Outcome.STOPPED,
            evidence_span="evidence",
        ),
        StructuredRecord(
            record_id="r2",
            raw_id="raw_2",
            groww_specific=False,
            lifecycle_stage="month 0 to 1",
            behavior=["test"],
            barrier_or_trigger_to_stop="none",
            confusion_or_worry_in_app="none",
            expectation="unknown",
            checking_behavior="unknown",
            outside_app_behavior="unknown",
            emotion=Emotion.CONFIDENCE,
            segment=Segment(income_stability="student_dependent", age_band="<25"),
            outcome=Outcome.CONTINUED,
            evidence_span="evidence",
        ),
    ]

    source_map = {"raw_1": "playstore", "raw_2": "reddit"}
    res = aggregator.compute_all_aggregations(recs, source_mapping=source_map)

    assert res["total_records"] == 2
    assert "month 0 to 1" in res["lifecycle_breakdown"]
    assert res["lifecycle_breakdown"]["month 0 to 1"]["count"] == 2
    assert res["lifecycle_breakdown"]["month 0 to 1"]["drop_off_rate"] == 0.5

    assert "income_stability" in res["segment_breakdown"]
    assert "stable_salaried" in res["segment_breakdown"]["income_stability"]
    assert res["segment_breakdown"]["income_stability"]["stable_salaried"]["drop_off_rate"] == 1.0

    assert res["platform_breakdown"]["groww_specific"]["count"] == 1
    assert res["platform_breakdown"]["platform_agnostic"]["count"] == 1

    assert "playstore" in res["source_breakdown"]
    assert "reddit" in res["source_breakdown"]
