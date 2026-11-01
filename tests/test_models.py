"""
Tests for Pydantic models and schemas in src/models/schemas.py.
"""

from datetime import datetime
import pytest
from pydantic import ValidationError

from src.models.schemas import (
    ConfidenceLevel,
    Emotion,
    EvidenceLogEntry,
    ExtractionStatus,
    LifecycleStage,
    OpportunityArea,
    Outcome,
    RawItem,
    RawItemMetadata,
    Segment,
    SourceType,
    StructuredRecord,
)


class TestRawItem:
    def test_valid_raw_item(self):
        item = RawItem(
            source=SourceType.REDDIT,
            source_native_id="post_12345",
            source_url="https://reddit.com/r/mutualfunds/comments/12345",
            platform_mentioned=["groww"],
            text="Started SIP in Groww 3 months ago but thinking of pausing due to negative returns.",
            language_detected="en",
            metadata=RawItemMetadata(subreddit="mutualfunds"),
        )
        assert item.source == SourceType.REDDIT
        assert item.source_native_id == "post_12345"
        assert len(item.platform_mentioned) == 1
        assert "groww" in item.platform_mentioned
        assert item.raw_id is not None
        assert isinstance(item.collected_at, datetime)

    def test_raw_item_empty_text_raises_validation_error(self):
        with pytest.raises(ValidationError):
            RawItem(
                source=SourceType.PLAYSTORE,
                source_native_id="rev_1",
                text="   ",
            )

    def test_invalid_source_type_raises(self):
        with pytest.raises(ValidationError):
            RawItem(
                source="invalid_source",  # type: ignore
                source_native_id="123",
                text="Some text",
            )


class TestStructuredRecord:
    def test_valid_structured_record_defaults(self):
        rec = StructuredRecord(
            raw_id="raw-uuid-1",
            groww_specific=True,
        )
        assert rec.raw_id == "raw-uuid-1"
        assert rec.groww_specific is True
        assert rec.lifecycle_stage == LifecycleStage.UNKNOWN
        assert rec.emotion == Emotion.UNKNOWN
        assert rec.outcome == Outcome.UNCLEAR
        assert rec.extraction_status == ExtractionStatus.SUCCESS
        assert isinstance(rec.segment, Segment)
        assert rec.segment.income_stability == "unknown"

    def test_structured_record_populated(self):
        rec = StructuredRecord(
            raw_id="raw-uuid-2",
            groww_specific=False,
            lifecycle_stage=LifecycleStage.MONTHS_2_3,
            behavior=["checks returns frequently", "pauses SIP"],
            driver_to_start="peer/influencer",
            expectation="15% annual returns in 1 year",
            barrier_or_trigger_to_stop="low or negative returns",
            confusion_or_worry_in_app="XIRR",
            checking_behavior="daily NAV check",
            outside_app_behavior="YouTube, Reddit",
            emotion=Emotion.ANXIETY,
            outcome=Outcome.PAUSED,
            evidence_span="returns were -2% after 3 months so I paused",
        )
        assert rec.lifecycle_stage == LifecycleStage.MONTHS_2_3
        assert rec.emotion == Emotion.ANXIETY
        assert rec.outcome == Outcome.PAUSED
        assert len(rec.behavior) == 2


class TestOpportunityArea:
    def test_valid_opportunity_area(self):
        area = OpportunityArea(
            theme_name="XIRR Confusion During Market Dips",
            theme_category="Understanding Returns",
            frequency_count=45,
            frequency_share=0.045,
            severity_score=0.62,
            breadth_score=0.75,
            composite_score=0.574,
            sufficient_evidence=True,
            evidence_level="sufficient",
        )
        assert area.frequency_count == 45
        assert area.sufficient_evidence is True
        assert area.severity_score == 0.62

    def test_opportunity_area_score_bounds(self):
        with pytest.raises(ValidationError):
            OpportunityArea(
                theme_name="Test",
                theme_category="Test",
                frequency_count=10,
                frequency_share=1.5,  # > 1.0
                breadth_score=0.5,
                composite_score=0.5,
                sufficient_evidence=False,
            )


class TestEvidenceLogEntry:
    def test_valid_log_entry(self):
        entry = EvidenceLogEntry(
            pipeline_stage="extraction",
            event_type="batch_complete",
            details={"processed": 50, "failed": 0, "model": "llama-3.3-70b-versatile"},
        )
        assert entry.pipeline_stage == "extraction"
        assert entry.event_type == "batch_complete"
        assert entry.details["processed"] == 50
        assert entry.log_id is not None

