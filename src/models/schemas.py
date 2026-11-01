"""
Pydantic models for the SIP Discovery Engine.

Defines the core data structures used across the pipeline:
- RawItem: Collected item from any source (Stage 1)
- StructuredRecord: LLM-extracted behavioral signals (Stage 3)
- OpportunityArea: Scored and ranked theme (Stage 4)
- EvidenceLogEntry: Audit trail entry (all stages)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ──────────────────────────────────────────────
# Enums for controlled vocabularies
# ──────────────────────────────────────────────

class SourceType(str, Enum):
    """Allowed data source types."""
    REDDIT = "reddit"
    PLAYSTORE = "playstore"
    APPSTORE = "appstore"
    YOUTUBE = "youtube"
    FORUM = "forum"
    TWITTER = "twitter"
    QUORA = "quora"
    OTHER = "other"


class LifecycleStage(str, Enum):
    """SIP lifecycle stages for an investor."""
    PRE_START = "pre-start"
    MONTH_0_1 = "month 0 to 1"
    MONTHS_2_3 = "months 2 to 3"
    MONTHS_4_6 = "months 4 to 6"
    MONTHS_7_12 = "months 7 to 12"
    TWELVE_PLUS = "12+"
    LAPSED_RESTARTED = "lapsed/restarted"
    UNKNOWN = "unknown"


class Emotion(str, Enum):
    """Emotional states observed in investor feedback."""
    ANXIETY = "anxiety"
    REGRET = "regret"
    DISAPPOINTMENT = "disappointment"
    CONFIDENCE = "confidence"
    INDIFFERENCE = "indifference"
    ANGER = "anger"
    UNKNOWN = "unknown"


class Outcome(str, Enum):
    """SIP outcome after the behavior described."""
    CONTINUED = "continued"
    PAUSED = "paused"
    REDUCED = "reduced"
    STOPPED = "stopped"
    UNCLEAR = "unclear"


class ConfidenceLevel(str, Enum):
    """Extraction confidence per field."""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


class ExtractionStatus(str, Enum):
    """Status of the LLM extraction for an item."""
    SUCCESS = "success"
    FAILED = "failed"
    TOO_SHORT = "too_short"
    SKIPPED = "skipped"


# ──────────────────────────────────────────────
# Raw Item (Stage 1 — Collection)
# ──────────────────────────────────────────────

class RawItemMetadata(BaseModel):
    """Source-specific metadata attached to a raw item."""
    subreddit: Optional[str] = None
    rating: Optional[int] = None
    video_id: Optional[str] = None
    thread_title: Optional[str] = None
    extra: Optional[dict] = None


class RawItem(BaseModel):
    """
    A single collected item from any public source.
    Stored in the raw_items table as the immutable archive.
    """
    raw_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source: SourceType
    source_native_id: str = Field(
        ..., description="Original post/review ID or URL from the source platform"
    )
    source_url: Optional[str] = Field(
        None, description="Direct URL to the original post/review"
    )
    platform_mentioned: list[str] = Field(
        default_factory=list,
        description="Platforms mentioned in the text (e.g. ['groww'])"
    )
    collected_at: datetime = Field(default_factory=_utc_now)
    published_at: Optional[datetime] = Field(
        None, description="When the original post was published"
    )
    text: str = Field(..., min_length=1, description="Original text content")
    language_detected: Optional[str] = Field(
        None, description="Detected language: en, hi, hinglish, other"
    )
    metadata: RawItemMetadata = Field(default_factory=RawItemMetadata)

    @field_validator("text")
    @classmethod
    def text_must_not_be_empty(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("Text must not be empty or whitespace-only")
        return stripped


# ──────────────────────────────────────────────
# Segment (nested in StructuredRecord)
# ──────────────────────────────────────────────

class Segment(BaseModel):
    """Demographic/behavioral segment of the investor."""
    income_stability: str = Field(
        default="unknown",
        description="stable, variable, student, none, unknown"
    )
    age_band: str = Field(
        default="unknown",
        description="e.g. 18-22, 22-28, 28-35, 35+, unknown"
    )
    source_of_money: str = Field(
        default="unknown",
        description="salary, parental, freelance, bonus, unknown"
    )
    influencer: str = Field(
        default="unknown",
        description="self, friend, family, finfluencer, platform, unknown"
    )


# ──────────────────────────────────────────────
# Field Confidence Map
# ──────────────────────────────────────────────

class FieldConfidence(BaseModel):
    """Per-field extraction confidence ratings."""
    lifecycle_stage: ConfidenceLevel = ConfidenceLevel.UNKNOWN
    behavior: ConfidenceLevel = ConfidenceLevel.UNKNOWN
    driver_to_start: ConfidenceLevel = ConfidenceLevel.UNKNOWN
    expectation: ConfidenceLevel = ConfidenceLevel.UNKNOWN
    barrier_or_trigger_to_stop: ConfidenceLevel = ConfidenceLevel.UNKNOWN
    confusion_or_worry_in_app: ConfidenceLevel = ConfidenceLevel.UNKNOWN
    checking_behavior: ConfidenceLevel = ConfidenceLevel.UNKNOWN
    outside_app_behavior: ConfidenceLevel = ConfidenceLevel.UNKNOWN
    emotion: ConfidenceLevel = ConfidenceLevel.UNKNOWN
    segment: ConfidenceLevel = ConfidenceLevel.UNKNOWN
    outcome: ConfidenceLevel = ConfidenceLevel.UNKNOWN


# ──────────────────────────────────────────────
# Structured Record (Stage 3 — Extraction)
# ──────────────────────────────────────────────

class StructuredRecord(BaseModel):
    """
    LLM-extracted structured behavioral signals from a single feedback item.
    Every field the text does not support must be 'unknown', never guessed.
    """
    record_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    raw_id: str = Field(..., description="FK to the source RawItem")
    groww_specific: bool = Field(
        ..., description="True if the text mentions Groww"
    )
    lifecycle_stage: LifecycleStage = LifecycleStage.UNKNOWN
    behavior: list[str] = Field(
        default_factory=list,
        description="All behaviors mentioned (array — can be multiple)"
    )
    driver_to_start: str = Field(default="unknown")
    expectation: str = Field(default="unknown")
    barrier_or_trigger_to_stop: str = Field(default="unknown")
    confusion_or_worry_in_app: str = Field(default="unknown")
    checking_behavior: str = Field(default="unknown")
    outside_app_behavior: str = Field(default="unknown")
    emotion: Emotion = Emotion.UNKNOWN
    segment: Segment = Field(default_factory=Segment)
    outcome: Outcome = Outcome.UNCLEAR
    evidence_span: str = Field(
        default="",
        description="Short verbatim excerpt (≤30 words) supporting the tags"
    )
    confidence: FieldConfidence = Field(default_factory=FieldConfidence)
    extracted_at: datetime = Field(default_factory=_utc_now)
    extraction_status: ExtractionStatus = ExtractionStatus.SUCCESS
    model_version: str = Field(default="llama-3.3-70b-versatile")
    prompt_version: str = Field(default="v1.0")


# ──────────────────────────────────────────────
# Opportunity Area (Stage 4 — Analysis)
# ──────────────────────────────────────────────

class OpportunityArea(BaseModel):
    """
    A scored and ranked thematic opportunity area.
    Backed by frequency, severity, and breadth metrics.
    """
    opportunity_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    theme_name: str = Field(..., description="Human-readable theme name")
    theme_category: str = Field(
        ..., description="Parent category (e.g. 'Returns Disappointment')"
    )
    frequency_count: int = Field(
        ..., ge=0, description="Number of corpus items in this theme"
    )
    frequency_share: float = Field(
        ..., ge=0.0, le=1.0, description="frequency_count / total_corpus_size"
    )
    severity_score: Optional[float] = Field(
        None,
        ge=0.0, le=1.0,
        description="Proportion of items with negative outcome. None if insufficient outcome data."
    )
    breadth_score: float = Field(
        ..., ge=0.0, le=1.0,
        description="Source and segment diversity score"
    )
    composite_score: float = Field(
        ..., ge=0.0, le=1.0,
        description="Weighted combination: 0.4*freq + 0.4*severity + 0.2*breadth"
    )
    segment_breakdown: dict = Field(
        default_factory=dict,
        description="Counts by segment dimensions"
    )
    lifecycle_breakdown: dict = Field(
        default_factory=dict,
        description="Counts by lifecycle stage"
    )
    source_breakdown: dict = Field(
        default_factory=dict,
        description="Counts by source type"
    )
    sufficient_evidence: bool = Field(
        ..., description="True if n >= 30 and >= 2 sources"
    )
    evidence_level: str = Field(
        default="insufficient",
        description="'sufficient', 'directional', or 'insufficient'"
    )
    computed_at: datetime = Field(default_factory=_utc_now)


# ──────────────────────────────────────────────
# Evidence Log Entry (all stages)
# ──────────────────────────────────────────────

class EvidenceLogEntry(BaseModel):
    """
    An audit trail entry for the AI Evidence Log.
    Records collection, extraction, quality, and correction events.
    """
    log_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    pipeline_stage: str = Field(
        ...,
        description="Which stage: collection, preprocessing, extraction, analysis, synthesis"
    )
    event_type: str = Field(
        ...,
        description="Type of event: run_start, run_complete, quality_check, error, correction"
    )
    details: dict = Field(
        default_factory=dict,
        description="Structured event data (counts, metrics, errors, etc.)"
    )
    logged_at: datetime = Field(default_factory=_utc_now)
