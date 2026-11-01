"""
Unit tests for src/analysis/opportunity_scorer.py.
"""

import pytest

from src.analysis.opportunity_scorer import OpportunityScorer
from src.models.schemas import Emotion, Outcome, Segment, StructuredRecord


@pytest.fixture
def scorer():
    return OpportunityScorer()


def _make_record(raw_id: str, outcome: Outcome, age: str = "unknown", inc: str = "unknown"):
    return StructuredRecord(
        record_id=f"rec_{raw_id}",
        raw_id=raw_id,
        groww_specific=True,
        lifecycle_stage="months 2 to 3",
        behavior=["test"],
        barrier_or_trigger_to_stop="market crash fear",
        confusion_or_worry_in_app="unknown",
        expectation="unknown",
        checking_behavior="unknown",
        outside_app_behavior="unknown",
        emotion=Emotion.ANXIETY,
        segment=Segment(age_band=age, income_stability=inc),
        outcome=outcome,
        evidence_span="market crash fear",
    )


def test_score_theme_math(scorer):
    """Test the exact composite score calculation."""
    # 4 droppers, 1 continuer -> n=5, severity = 4/5 = 0.8
    recs = [
        _make_record("r1", Outcome.STOPPED, age="25-34", inc="stable_salaried"),
        _make_record("r2", Outcome.PAUSED, age="25-34", inc="stable_salaried"),
        _make_record("r3", Outcome.REDUCED, age="<25", inc="student_dependent"),
        _make_record("r4", Outcome.STOPPED, age="<25", inc="variable_freelance"),
        _make_record("r5", Outcome.CONTINUED, age="35+", inc="stable_salaried"),
    ]

    source_map = {
        "r1": "reddit",
        "r2": "playstore",
        "r3": "youtube",
        "r4": "quora",
        "r5": "twitter",
    }
    all_sources = {"reddit", "playstore", "youtube", "quora", "twitter", "appstore"}

    area = scorer.score_theme(
        theme_name="Market Volatility Fear",
        theme_category="Trust & Confidence Erosion",
        records_in_theme=recs,
        total_corpus_size=10,
        all_sources=all_sources,
        max_frequency_count=5,
        source_mapping=source_map,
    )

    # freq_score: 5 / 5 = 1.0 (relative to max_frequency_count)
    # severity_score: 4 / 5 = 0.8
    # breadth: sources = 5/6 = 0.8333, segments = 4/4 = 1.0 -> breadth = 0.5*0.8333 + 0.5*1.0 = 0.9167
    # composite: 0.4 * 1.0 + 0.4 * 0.8 + 0.2 * 0.9167 = 0.4 + 0.32 + 0.1833 = 0.9033
    assert area.frequency_count == 5
    assert area.severity_score == 0.8
    assert 0.85 <= area.composite_score <= 0.95
    assert area.evidence_level == "insufficient"  # n=5 < 10


def test_evidence_thresholds(scorer):
    """Test headline vs directional vs insufficient thresholds."""
    # 35 items across 3 sources -> Headline finding ("sufficient")
    headline_recs = [_make_record(f"r_{i}", Outcome.STOPPED) for i in range(35)]
    source_map = {f"r_{i}": ("reddit" if i < 15 else ("playstore" if i < 30 else "quora")) for i in range(35)}

    area_headline = scorer.score_theme(
        theme_name="Autopay Failure",
        theme_category="Lifecycle Friction",
        records_in_theme=headline_recs,
        total_corpus_size=100,
        all_sources={"reddit", "playstore", "quora"},
        source_mapping=source_map,
    )
    assert area_headline.sufficient_evidence is True
    assert area_headline.evidence_level == "sufficient"

    # 15 items on single source -> Directional
    dir_recs = [_make_record(f"d_{i}", Outcome.STOPPED) for i in range(15)]
    single_source_map = {f"d_{i}": "reddit" for i in range(15)}

    area_dir = scorer.score_theme(
        theme_name="Autopay Failure",
        theme_category="Lifecycle Friction",
        records_in_theme=dir_recs,
        total_corpus_size=100,
        all_sources={"reddit"},
        source_mapping=single_source_map,
    )
    assert area_dir.sufficient_evidence is False
    assert area_dir.evidence_level == "directional"
