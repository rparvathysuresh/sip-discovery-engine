"""
src/extraction/schema_validator.py — Schema validator for LLM-extracted structured records.

Performs:
- Pydantic schema validation
- Controlled vocabulary / enum enforcement
- Evidence span fidelity verification against the original text
- Word count bounds checking on evidence spans
"""

from __future__ import annotations

import re
import string
from typing import Any, Optional

from src.models.schemas import (
    ConfidenceLevel,
    Emotion,
    ExtractionStatus,
    FieldConfidence,
    LifecycleStage,
    Outcome,
    Segment,
    StructuredRecord,
)
from src.utils.logging import get_logger

logger = get_logger(__name__)

# Valid enum value sets
VALID_LIFECYCLE_STAGES = {e.value for e in LifecycleStage}
VALID_EMOTIONS = {e.value for e in Emotion}
VALID_OUTCOMES = {e.value for e in Outcome}
VALID_CONFIDENCE_LEVELS = {e.value for e in ConfidenceLevel}

DEFAULT_MAX_EVIDENCE_WORDS = 35


def _normalize_for_matching(text: str) -> str:
    """Normalize text by lowering case, removing punctuation and collapsing whitespace."""
    if not text:
        return ""
    # Replace punctuation with space
    table = str.maketrans(string.punctuation, " " * len(string.punctuation))
    cleaned = text.translate(table).lower()
    return re.sub(r"\s+", " ", cleaned).strip()


class SchemaValidationError(Exception):
    """Raised when structured extraction output fails validation."""
    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


class SchemaValidator:
    """
    Validates dictionary output from LLM against StructuredRecord constraints.
    """

    def __init__(
        self,
        strict_enums: bool = True,
        max_evidence_words: int = DEFAULT_MAX_EVIDENCE_WORDS,
        require_evidence_span: bool = True,
    ):
        self.strict_enums = strict_enums
        self.max_evidence_words = max_evidence_words
        self.require_evidence_span = require_evidence_span

    def validate_raw_dict(
        self, data: dict[str, Any], original_text: str
    ) -> tuple[bool, list[str]]:
        """
        Validate dictionary extracted from LLM.

        Args:
            data: Extracted JSON data as dict.
            original_text: The source text given to the LLM.

        Returns:
            (is_valid, list_of_error_messages)
        """
        errors: list[str] = []

        if not isinstance(data, dict):
            return False, ["Root output is not a JSON object"]

        # 1. Lifecycle stage enum check
        ls = str(data.get("lifecycle_stage", "unknown")).lower()
        if self.strict_enums and ls not in VALID_LIFECYCLE_STAGES:
            errors.append(f"Invalid lifecycle_stage '{ls}'. Allowed: {sorted(VALID_LIFECYCLE_STAGES)}")

        # 2. Emotion enum check
        emo = str(data.get("emotion", "unknown")).lower()
        if self.strict_enums and emo not in VALID_EMOTIONS:
            errors.append(f"Invalid emotion '{emo}'. Allowed: {sorted(VALID_EMOTIONS)}")

        # 3. Outcome enum check
        out = str(data.get("outcome", "unclear")).lower()
        if self.strict_enums and out not in VALID_OUTCOMES:
            errors.append(f"Invalid outcome '{out}'. Allowed: {sorted(VALID_OUTCOMES)}")

        # 4. Behavior array check
        behavior = data.get("behavior")
        if behavior is not None and not isinstance(behavior, list):
            errors.append("Field 'behavior' must be a list of strings")

        # 5. Segment check
        segment = data.get("segment")
        if segment is not None and not isinstance(segment, dict):
            errors.append("Field 'segment' must be a nested JSON object")

        # 6. Confidence dict check
        conf = data.get("confidence")
        if conf is not None:
            if not isinstance(conf, dict):
                errors.append("Field 'confidence' must be an object of field confidence ratings")
            elif self.strict_enums:
                for f_name, f_val in conf.items():
                    val_str = str(f_val).lower()
                    if val_str not in VALID_CONFIDENCE_LEVELS:
                        errors.append(
                            f"Invalid confidence level '{val_str}' for field '{f_name}'. "
                            f"Allowed: {sorted(VALID_CONFIDENCE_LEVELS)}"
                        )

        # 7. Evidence span verification
        evidence_span = data.get("evidence_span", "")
        if self.require_evidence_span and not evidence_span:
            errors.append("Field 'evidence_span' is required but was empty")
        elif evidence_span:
            words = evidence_span.split()
            if len(words) > self.max_evidence_words:
                errors.append(
                    f"Evidence span exceeds word limit ({len(words)} > {self.max_evidence_words} words)"
                )

            # Check substring match against original text
            norm_span = _normalize_for_matching(evidence_span)
            norm_orig = _normalize_for_matching(original_text)

            if norm_span and norm_span not in norm_orig:
                # Allow partial match if >= 70% of words appear in order
                span_words = norm_span.split()
                if len(span_words) >= 3:
                    matched = sum(1 for w in span_words if w in norm_orig)
                    ratio = matched / len(span_words)
                    if ratio < 0.70:
                        errors.append(
                            f"Evidence span '{evidence_span[:40]}...' is not grounded in the original text (fidelity ratio={ratio:.2f})"
                        )
                else:
                    errors.append(f"Evidence span '{evidence_span}' is not a substring of original text")

        return len(errors) == 0, errors

    def to_structured_record(
        self,
        data: dict[str, Any],
        raw_id: str,
        original_text: str,
        groww_specific_default: bool = True,
        model_version: str = "llama-3.3-70b-versatile",
        prompt_version: str = "v1.0",
    ) -> StructuredRecord:
        """
        Validate and construct a StructuredRecord instance from LLM output.

        Raises:
            SchemaValidationError: If validation fails.
        """
        is_valid, errors = self.validate_raw_dict(data, original_text)
        if not is_valid:
            raise SchemaValidationError(errors)

        # Parse nested segment
        seg_data = data.get("segment") or {}
        segment = Segment(
            income_stability=str(seg_data.get("income_stability", "unknown")),
            age_band=str(seg_data.get("age_band", "unknown")),
            source_of_money=str(seg_data.get("source_of_money", "unknown")),
            influencer=str(seg_data.get("influencer", "unknown")),
        )

        # Parse field confidences
        conf_data = data.get("confidence") or {}
        confidence = FieldConfidence(
            lifecycle_stage=ConfidenceLevel(str(conf_data.get("lifecycle_stage", "unknown")).lower()),
            behavior=ConfidenceLevel(str(conf_data.get("behavior", "unknown")).lower()),
            driver_to_start=ConfidenceLevel(str(conf_data.get("driver_to_start", "unknown")).lower()),
            expectation=ConfidenceLevel(str(conf_data.get("expectation", "unknown")).lower()),
            barrier_or_trigger_to_stop=ConfidenceLevel(str(conf_data.get("barrier_or_trigger_to_stop", "unknown")).lower()),
            confusion_or_worry_in_app=ConfidenceLevel(str(conf_data.get("confusion_or_worry_in_app", "unknown")).lower()),
            checking_behavior=ConfidenceLevel(str(conf_data.get("checking_behavior", "unknown")).lower()),
            outside_app_behavior=ConfidenceLevel(str(conf_data.get("outside_app_behavior", "unknown")).lower()),
            emotion=ConfidenceLevel(str(conf_data.get("emotion", "unknown")).lower()),
            segment=ConfidenceLevel(str(conf_data.get("segment", "unknown")).lower()),
            outcome=ConfidenceLevel(str(conf_data.get("outcome", "unknown")).lower()),
        )

        # Parse behaviors
        behaviors = data.get("behavior")
        if isinstance(behaviors, list):
            behavior_list = [str(b).strip() for b in behaviors if str(b).strip()]
        elif isinstance(behaviors, str) and behaviors.strip():
            behavior_list = [behaviors.strip()]
        else:
            behavior_list = []

        groww_spec = data.get("groww_specific")
        if groww_spec is None:
            groww_spec = groww_specific_default

        return StructuredRecord(
            raw_id=raw_id,
            groww_specific=bool(groww_spec),
            lifecycle_stage=LifecycleStage(str(data.get("lifecycle_stage", "unknown")).lower()),
            behavior=behavior_list,
            driver_to_start=str(data.get("driver_to_start", "unknown")),
            expectation=str(data.get("expectation", "unknown")),
            barrier_or_trigger_to_stop=str(data.get("barrier_or_trigger_to_stop", "unknown")),
            confusion_or_worry_in_app=str(data.get("confusion_or_worry_in_app", "unknown")),
            checking_behavior=str(data.get("checking_behavior", "unknown")),
            outside_app_behavior=str(data.get("outside_app_behavior", "unknown")),
            emotion=Emotion(str(data.get("emotion", "unknown")).lower()),
            segment=segment,
            outcome=Outcome(str(data.get("outcome", "unclear")).lower()),
            evidence_span=str(data.get("evidence_span", "")).strip(),
            confidence=confidence,
            extraction_status=ExtractionStatus.SUCCESS,
            model_version=model_version,
            prompt_version=prompt_version,
        )

