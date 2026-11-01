"""
Unit tests for src/analysis/continuer_dropper_comparator.py.
"""

import pytest

from src.analysis.continuer_dropper_comparator import ContinuerDropperComparator, _chi2_contingency_2x2
from src.models.schemas import Emotion, Outcome, Segment, StructuredRecord


@pytest.fixture
def comparator():
    return ContinuerDropperComparator()


def test_chi2_contingency_math():
    """Verify Chi-square, Yates correction, and odds ratio math."""
    # Table:
    #             Feature+   Feature-
    # Droppers:     30         10    (40)
    # Continuers:   10         30    (40)
    chi2, p_val, odds_ratio = _chi2_contingency_2x2(30, 10, 10, 30)

    # OR should be approx (30.5*30.5)/(10.5*10.5) = 930.25 / 110.25 ~ 8.4
    assert odds_ratio > 5.0
    assert chi2 > 15.0
    assert p_val < 0.001


def test_compare_dimension(comparator):
    """Verify comparator groups and statistical output."""
    continuers = [
        StructuredRecord(
            record_id=f"c_{i}",
            raw_id=f"raw_c_{i}",
            groww_specific=True,
            lifecycle_stage="month 0 to 1",
            behavior=["test"],
            barrier_or_trigger_to_stop="none",
            confusion_or_worry_in_app="none",
            expectation="none",
            checking_behavior="monthly",
            outside_app_behavior="none",
            emotion=Emotion.CONFIDENCE,
            segment=Segment(),
            outcome=Outcome.CONTINUED,
            evidence_span="evidence",
        )
        for i in range(10)
    ]

    droppers = [
        StructuredRecord(
            record_id=f"d_{i}",
            raw_id=f"raw_d_{i}",
            groww_specific=True,
            lifecycle_stage="month 0 to 1",
            behavior=["test"],
            barrier_or_trigger_to_stop="market dip",
            confusion_or_worry_in_app="none",
            expectation="none",
            checking_behavior="daily",
            outside_app_behavior="none",
            emotion=Emotion.ANXIETY,
            segment=Segment(),
            outcome=Outcome.STOPPED,
            evidence_span="evidence",
        )
        for i in range(10)
    ]

    records = continuers + droppers
    results = comparator.run_full_comparison(records)

    assert results["summary"]["continuers_count"] == 10
    assert results["summary"]["droppers_count"] == 10

    # Emotion dimension should show anxiety vs confidence
    emotions = {e["value"]: e for e in results["emotions"]}
    assert "anxiety" in emotions
    assert emotions["anxiety"]["dropper_count"] == 10
    assert emotions["anxiety"]["continuer_count"] == 0
    assert emotions["anxiety"]["diff_pct"] == 100.0
    assert emotions["anxiety"]["odds_ratio"] > 10.0
