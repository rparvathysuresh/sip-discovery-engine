"""
Unit tests for src/analysis/theme_clusterer.py.
"""

from pathlib import Path
import pytest

from src.analysis.theme_clusterer import ThemeClusterer
from src.models.schemas import (
    Emotion,
    Outcome,
    Segment,
    StructuredRecord,
)


@pytest.fixture
def clusterer():
    return ThemeClusterer()


def test_theme_clusterer_initialization(clusterer):
    """Verify codebook categories and sub-themes load properly."""
    categories = clusterer.get_all_categories()
    themes = clusterer.get_all_themes()

    assert len(categories) == 6
    assert len(themes) == 20
    assert "returns_disappointment" in clusterer.category_by_id
    assert "onboarding_kyc_friction" in clusterer.themes_by_id


def test_match_record_direct_keyword(clusterer):
    """Test matching record with explicit keyword."""
    rec = StructuredRecord(
        record_id="rec_test_1",
        raw_id="raw_1",
        groww_specific=True,
        lifecycle_stage="month 0 to 1",
        behavior=["complaining about returns"],
        barrier_or_trigger_to_stop="Promising 30% monthly return but got loss",
        confusion_or_worry_in_app="unknown",
        expectation="guaranteed returns",
        checking_behavior="unknown",
        outside_app_behavior="unknown",
        emotion=Emotion.DISAPPOINTMENT,
        segment=Segment(),
        outcome=Outcome.STOPPED,
        evidence_span="Promising 30% monthly return but got loss",
    )

    match = clusterer.match_record(rec)
    assert match["classified"] is True
    assert match["primary_theme_id"] == "unrealistic_return_expectations"
    assert match["category_id"] == "returns_disappointment"
    assert match["match_score"] > 0


def test_match_record_currency_normalization(clusterer):
    """Test matching with rupee symbol and increment rule."""
    rec = StructuredRecord(
        record_id="rec_test_2",
        raw_id="raw_2",
        groww_specific=True,
        lifecycle_stage="months 2 to 3",
        behavior=["trying to step up"],
        barrier_or_trigger_to_stop="error saying must be in multiples of ₹500",
        confusion_or_worry_in_app="why ₹500 multiples when amc allows ₹100",
        expectation="increase sip by 100",
        checking_behavior="unknown",
        outside_app_behavior="unknown",
        emotion=Emotion.ANGER,
        segment=Segment(),
        outcome=Outcome.CONTINUED,
        evidence_span="error saying must be in multiples of ₹500",
    )

    match = clusterer.match_record(rec)
    assert match["classified"] is True
    assert match["primary_theme_id"] == "step_up_and_increment_rules"
    assert match["category_id"] == "lifecycle_friction"


def test_compute_coverage(clusterer):
    """Test coverage calculation across multiple records."""
    recs = [
        StructuredRecord(
            record_id=f"rec_{i}",
            raw_id=f"raw_{i}",
            groww_specific=True,
            lifecycle_stage="pre-start",
            behavior=["test"],
            barrier_or_trigger_to_stop="autopay failed and bank penalty charged",
            confusion_or_worry_in_app="unknown",
            expectation="unknown",
            checking_behavior="unknown",
            outside_app_behavior="unknown",
            emotion=Emotion.ANGER,
            segment=Segment(),
            outcome=Outcome.PAUSED,
            evidence_span="autopay failed",
        )
        for i in range(5)
    ]

    cov = clusterer.compute_coverage(recs)
    assert cov["total_records"] == 5
    assert cov["classified_records"] == 5
    assert cov["coverage_pct"] == 100.0
    assert "Autopay & Mandate Failure" in cov["theme_counts"]
