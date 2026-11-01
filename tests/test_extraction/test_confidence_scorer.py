"""
tests/test_extraction/test_confidence_scorer.py — Unit tests for ConfidenceScorer.
"""

from src.extraction.confidence_scorer import ConfidenceScorer
from src.models.schemas import ConfidenceLevel, FieldConfidence, StructuredRecord


def test_confidence_scorer_high_confidence():
    scorer = ConfidenceScorer(min_high_fields=3)
    conf = FieldConfidence(
        lifecycle_stage=ConfidenceLevel.HIGH,
        behavior=ConfidenceLevel.HIGH,
        driver_to_start=ConfidenceLevel.HIGH,
        expectation=ConfidenceLevel.MEDIUM,
        barrier_or_trigger_to_stop=ConfidenceLevel.HIGH,
        confusion_or_worry_in_app=ConfidenceLevel.HIGH,
        checking_behavior=ConfidenceLevel.MEDIUM,
        outside_app_behavior=ConfidenceLevel.HIGH,
        emotion=ConfidenceLevel.HIGH,
        segment=ConfidenceLevel.MEDIUM,
        outcome=ConfidenceLevel.HIGH,
    )
    res = scorer.score_confidence(conf)
    assert res["high_count"] == 8
    assert res["medium_count"] == 3
    assert res["overall_score"] > 0.85
    assert res["is_low_confidence"] is False


def test_confidence_scorer_low_confidence_flag():
    scorer = ConfidenceScorer(min_high_fields=3)
    # Only 1 high confidence field
    conf = FieldConfidence(
        lifecycle_stage=ConfidenceLevel.HIGH,
        behavior=ConfidenceLevel.LOW,
        driver_to_start=ConfidenceLevel.UNKNOWN,
        expectation=ConfidenceLevel.UNKNOWN,
        barrier_or_trigger_to_stop=ConfidenceLevel.LOW,
        confusion_or_worry_in_app=ConfidenceLevel.UNKNOWN,
        checking_behavior=ConfidenceLevel.UNKNOWN,
        outside_app_behavior=ConfidenceLevel.UNKNOWN,
        emotion=ConfidenceLevel.UNKNOWN,
        segment=ConfidenceLevel.UNKNOWN,
        outcome=ConfidenceLevel.LOW,
    )
    res = scorer.score_confidence(conf)
    assert res["high_count"] == 1
    assert res["is_low_confidence"] is True

