"""
tests/test_extraction/test_schema_validator.py — Unit tests for SchemaValidator.
"""

import pytest

from src.extraction.schema_validator import SchemaValidationError, SchemaValidator
from src.models.schemas import ConfidenceLevel, Emotion, LifecycleStage, Outcome


def _sample_valid_dict():
    return {
        "groww_specific": True,
        "lifecycle_stage": "months 2 to 3",
        "behavior": ["stopped monthly SIP", "researched on Reddit"],
        "driver_to_start": "peer recommendation",
        "expectation": "12% annual returns",
        "barrier_or_trigger_to_stop": "negative returns in first 3 months",
        "confusion_or_worry_in_app": "XIRR vs absolute return display",
        "checking_behavior": "daily NAV checking",
        "outside_app_behavior": "asked on r/mutualfunds",
        "emotion": "anxiety",
        "segment": {
            "income_stability": "stable",
            "age_band": "22-28",
            "source_of_money": "salary",
            "influencer": "friend",
        },
        "outcome": "stopped",
        "evidence_span": "I stopped my monthly SIP because returns were negative after 3 months",
        "confidence": {
            "lifecycle_stage": "high",
            "behavior": "high",
            "driver_to_start": "medium",
            "expectation": "medium",
            "barrier_or_trigger_to_stop": "high",
            "confusion_or_worry_in_app": "high",
            "checking_behavior": "high",
            "outside_app_behavior": "high",
            "emotion": "high",
            "segment": "medium",
            "outcome": "high",
        },
    }


def test_schema_validator_valid():
    validator = SchemaValidator()
    orig = "I started investing last quarter. I stopped my monthly SIP because returns were negative after 3 months and I was scared."
    is_valid, errors = validator.validate_raw_dict(_sample_valid_dict(), orig)
    assert is_valid
    assert errors == []

    record = validator.to_structured_record(_sample_valid_dict(), raw_id="raw_123", original_text=orig)
    assert record.raw_id == "raw_123"
    assert record.lifecycle_stage == LifecycleStage.MONTHS_2_3
    assert record.emotion == Emotion.ANXIETY
    assert record.outcome == Outcome.STOPPED
    assert record.confidence.lifecycle_stage == ConfidenceLevel.HIGH


def test_schema_validator_invalid_enums():
    validator = SchemaValidator()
    data = _sample_valid_dict()
    data["lifecycle_stage"] = "year 5"  # invalid enum
    data["emotion"] = "hysterical"       # invalid enum
    data["outcome"] = "abandoned"        # invalid enum

    orig = "I stopped my monthly SIP because returns were negative after 3 months"
    is_valid, errors = validator.validate_raw_dict(data, orig)
    assert not is_valid
    assert any("lifecycle_stage" in e for e in errors)
    assert any("emotion" in e for e in errors)
    assert any("outcome" in e for e in errors)


def test_schema_validator_evidence_span_too_long():
    validator = SchemaValidator(max_evidence_words=10)
    data = _sample_valid_dict()
    data["evidence_span"] = "word " * 15  # 15 words > 10 max
    orig = "word " * 20
    is_valid, errors = validator.validate_raw_dict(data, orig)
    assert not is_valid
    assert any("exceeds word limit" in e for e in errors)


def test_schema_validator_ungrounded_evidence_span():
    validator = SchemaValidator()
    data = _sample_valid_dict()
    data["evidence_span"] = "Crypto bitcoin wallet transfer got completely blocked"
    orig = "I stopped my monthly SIP because returns were negative after 3 months"
    is_valid, errors = validator.validate_raw_dict(data, orig)
    assert not is_valid
    assert any("not grounded" in e or "not a substring" in e for e in errors)

