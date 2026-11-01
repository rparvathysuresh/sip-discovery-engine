"""
src/extraction/confidence_scorer.py — Parses, scores, and audits extraction confidence ratings.

Performs:
- Extraction confidence scoring across all 11 fields
- Calculation of aggregate confidence scores (0.0 to 1.0)
- Low-confidence tagging (records with < 3 high-confidence fields flagged for audit)
"""

from __future__ import annotations

from typing import Any

from src.models.schemas import ConfidenceLevel, FieldConfidence, StructuredRecord
from src.utils.logging import get_logger

logger = get_logger(__name__)

# Numerical weights for confidence levels
CONFIDENCE_WEIGHTS = {
    ConfidenceLevel.HIGH: 1.0,
    ConfidenceLevel.MEDIUM: 0.6,
    ConfidenceLevel.LOW: 0.2,
    ConfidenceLevel.UNKNOWN: 0.0,
}

# Threshold: records with fewer than this many high-confidence fields are flagged for review
MIN_HIGH_CONFIDENCE_FIELDS = 3


class ConfidenceScorer:
    """
    Evaluates extraction confidence across structured records.
    """

    def __init__(self, min_high_fields: int = MIN_HIGH_CONFIDENCE_FIELDS):
        self.min_high_fields = min_high_fields

    def score_confidence(self, confidence: FieldConfidence) -> dict[str, Any]:
        """
        Compute aggregate confidence statistics from a FieldConfidence object.

        Returns:
            Dictionary containing:
            - high_count: int
            - medium_count: int
            - low_count: int
            - unknown_count: int
            - overall_score: float (0.0 to 1.0)
            - is_low_confidence: bool
        """
        field_values = [
            confidence.lifecycle_stage,
            confidence.behavior,
            confidence.driver_to_start,
            confidence.expectation,
            confidence.barrier_or_trigger_to_stop,
            confidence.confusion_or_worry_in_app,
            confidence.checking_behavior,
            confidence.outside_app_behavior,
            confidence.emotion,
            confidence.segment,
            confidence.outcome,
        ]

        total_fields = len(field_values)
        high_count = sum(1 for v in field_values if v == ConfidenceLevel.HIGH)
        medium_count = sum(1 for v in field_values if v == ConfidenceLevel.MEDIUM)
        low_count = sum(1 for v in field_values if v == ConfidenceLevel.LOW)
        unknown_count = sum(1 for v in field_values if v == ConfidenceLevel.UNKNOWN)

        weighted_sum = sum(CONFIDENCE_WEIGHTS.get(v, 0.0) for v in field_values)
        overall_score = round(weighted_sum / total_fields, 3) if total_fields > 0 else 0.0

        is_low_confidence = high_count < self.min_high_fields

        return {
            "high_count": high_count,
            "medium_count": medium_count,
            "low_count": low_count,
            "unknown_count": unknown_count,
            "total_fields": total_fields,
            "overall_score": overall_score,
            "is_low_confidence": is_low_confidence,
        }

    def evaluate_record(self, record: StructuredRecord) -> dict[str, Any]:
        """
        Evaluate a complete StructuredRecord, returning confidence audit metrics.
        """
        return self.score_confidence(record.confidence)

