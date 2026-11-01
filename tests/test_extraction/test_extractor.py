"""
tests/test_extraction/test_extractor.py — Unit tests for StructuredExtractor and retry loop.
"""

import json
from unittest.mock import MagicMock

from src.extraction.extractor import StructuredExtractor
from src.models.schemas import (
    ConfidenceLevel,
    Emotion,
    ExtractionStatus,
    LifecycleStage,
    Outcome,
    RawItem,
    RawItemMetadata,
    SourceType,
)


def _make_dummy_item(text: str) -> RawItem:
    return RawItem(
        raw_id="test_raw_001",
        source=SourceType.REDDIT,
        source_native_id="native_001",
        platform_mentioned=["groww"],
        text=text,
        metadata=RawItemMetadata(),
    )


def test_extractor_success_first_attempt():
    mock_client = MagicMock()
    valid_payload = {
        "groww_specific": True,
        "lifecycle_stage": "month 0 to 1",
        "behavior": ["checked NAV after 1 week"],
        "driver_to_start": "salary investment",
        "expectation": "safe wealth creation",
        "barrier_or_trigger_to_stop": "unknown",
        "confusion_or_worry_in_app": "folio number not generated",
        "checking_behavior": "daily check",
        "outside_app_behavior": "unknown",
        "emotion": "anxiety",
        "segment": {
            "income_stability": "stable",
            "age_band": "22-28",
            "source_of_money": "salary",
            "influencer": "self",
        },
        "outcome": "continued",
        "evidence_span": "folio number not generated yet",
        "confidence": {
            "lifecycle_stage": "high",
            "behavior": "high",
            "driver_to_start": "medium",
            "expectation": "medium",
            "barrier_or_trigger_to_stop": "unknown",
            "confusion_or_worry_in_app": "high",
            "checking_behavior": "high",
            "outside_app_behavior": "unknown",
            "emotion": "high",
            "segment": "medium",
            "outcome": "high",
        },
    }

    mock_client.chat_completion.return_value = {
        "content": json.dumps(valid_payload),
        "prompt_tokens": 120,
        "completion_tokens": 80,
    }

    extractor = StructuredExtractor(groq_client=mock_client)
    item = _make_dummy_item("Started my SIP yesterday. My folio number not generated yet, feeling worried.")

    record, meta = extractor.extract_single(item)

    assert record.extraction_status == ExtractionStatus.SUCCESS
    assert record.lifecycle_stage == LifecycleStage.MONTH_0_1
    assert record.emotion == Emotion.ANXIETY
    assert record.outcome == Outcome.CONTINUED
    assert meta["status"] == "success"
    assert meta["attempts"] == 1
    assert not meta["repaired"]
    assert mock_client.chat_completion.call_count == 1


def test_extractor_repair_loop_success():
    mock_client = MagicMock()

    # Attempt 1 returns invalid enum for lifecycle_stage
    bad_payload = {
        "groww_specific": True,
        "lifecycle_stage": "INVALID_STAGE",
        "behavior": ["stopped SIP"],
        "driver_to_start": "unknown",
        "expectation": "unknown",
        "barrier_or_trigger_to_stop": "market drop",
        "confusion_or_worry_in_app": "unknown",
        "checking_behavior": "unknown",
        "outside_app_behavior": "unknown",
        "emotion": "panic",  # invalid enum
        "segment": {},
        "outcome": "stopped",
        "evidence_span": "I stopped my SIP",
        "confidence": {},
    }

    # Attempt 2 returns corrected payload
    good_payload = {
        "groww_specific": True,
        "lifecycle_stage": "months 2 to 3",
        "behavior": ["stopped SIP"],
        "driver_to_start": "unknown",
        "expectation": "unknown",
        "barrier_or_trigger_to_stop": "market drop",
        "confusion_or_worry_in_app": "unknown",
        "checking_behavior": "unknown",
        "outside_app_behavior": "unknown",
        "emotion": "anxiety",
        "segment": {
            "income_stability": "unknown",
            "age_band": "unknown",
            "source_of_money": "unknown",
            "influencer": "unknown",
        },
        "outcome": "stopped",
        "evidence_span": "I stopped my SIP",
        "confidence": {
            "lifecycle_stage": "high",
            "behavior": "high",
            "driver_to_start": "unknown",
            "expectation": "unknown",
            "barrier_or_trigger_to_stop": "high",
            "confusion_or_worry_in_app": "unknown",
            "checking_behavior": "unknown",
            "outside_app_behavior": "unknown",
            "emotion": "high",
            "segment": "unknown",
            "outcome": "high",
        },
    }

    mock_client.chat_completion.side_effect = [
        {"content": json.dumps(bad_payload), "prompt_tokens": 100, "completion_tokens": 50},
        {"content": json.dumps(good_payload), "prompt_tokens": 120, "completion_tokens": 60},
    ]

    extractor = StructuredExtractor(groq_client=mock_client)
    item = _make_dummy_item("After 2 months of returns dropping I stopped my SIP.")

    record, meta = extractor.extract_single(item)

    assert record.extraction_status == ExtractionStatus.SUCCESS
    assert record.lifecycle_stage == LifecycleStage.MONTHS_2_3
    assert record.emotion == Emotion.ANXIETY
    assert meta["status"] == "success"
    assert meta["repaired"] is True
    assert meta["attempts"] == 2
    assert mock_client.chat_completion.call_count == 2


def test_extractor_fallback_on_unrecoverable_error():
    mock_client = MagicMock()
    mock_client.chat_completion.side_effect = Exception("API rate limit exceeded repeatedly")

    extractor = StructuredExtractor(groq_client=mock_client)
    item = _make_dummy_item("Sample review text that fails.")

    record, meta = extractor.extract_single(item, max_repairs=1)

    assert record.extraction_status == ExtractionStatus.FAILED
    assert meta["status"] == "failed"
    assert meta["is_low_confidence"] is True

