"""
src/extraction/extractor.py — Core structured extraction engine utilizing Groq LLMs.

Orchestrates:
- Prompt compilation (system schema prompt + user conversation item)
- Groq API invocation with JSON mode
- Schema validation via SchemaValidator
- Repair prompt retry loop (max 2 repair attempts per item)
- Confidence scoring and low-confidence flagging
- Multi-threaded batch extraction with rate-limit adherence
"""

from __future__ import annotations

import concurrent.futures
import json
import re
import threading
import time
from pathlib import Path
from typing import Any, Callable, Optional

from src.extraction.confidence_scorer import ConfidenceScorer
from src.extraction.schema_validator import SchemaValidationError, SchemaValidator
from src.models.schemas import (
    ConfidenceLevel,
    Emotion,
    ExtractionStatus,
    FieldConfidence,
    LifecycleStage,
    Outcome,
    RawItem,
    Segment,
    StructuredRecord,
)
from src.utils.config import get_extraction_config
from src.utils.groq_client import GroqClient
from src.utils.logging import get_logger

logger = get_logger(__name__)

DEFAULT_PROMPT_PATH = Path("src/extraction/prompts/extraction_v1.txt")
DEFAULT_REPAIR_PATH = Path("src/extraction/prompts/repair_prompt.txt")


def _clean_json_output(raw_text: str) -> str:
    """Strip markdown code fences and extraneous text if present."""
    text = raw_text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


class StructuredExtractor:
    """
    LLM-based structured behavioral extractor for mutual fund SIP user feedback.
    """

    def __init__(
        self,
        groq_client: Optional[GroqClient] = None,
        validator: Optional[SchemaValidator] = None,
        confidence_scorer: Optional[ConfidenceScorer] = None,
        prompt_path: Optional[Path | str] = None,
        repair_path: Optional[Path | str] = None,
        config: Optional[dict[str, Any]] = None,
    ):
        self.config = config or get_extraction_config()
        self.groq_client = groq_client
        self.validator = validator or SchemaValidator(
            strict_enums=self.config.get("schema_validation", {}).get("strict_enums", True),
            max_evidence_words=self.config.get("schema_validation", {}).get("evidence_span_max_words", 35),
            require_evidence_span=self.config.get("schema_validation", {}).get("require_evidence_span", True),
        )
        self.confidence_scorer = confidence_scorer or ConfidenceScorer()

        # Prompt templates
        p_path = Path(prompt_path or DEFAULT_PROMPT_PATH)
        self.system_prompt = p_path.read_text(encoding="utf-8") if p_path.is_file() else ""

        r_path = Path(repair_path or DEFAULT_REPAIR_PATH)
        self.repair_template = r_path.read_text(encoding="utf-8") if r_path.is_file() else ""

        self.model_version = self.config.get("models", {}).get("primary", "openai/gpt-oss-120b")
        self.prompt_version = self.config.get("prompt_version", "v1.0")

        # Metrics
        self._stats_lock = threading.Lock()
        self.stats = {
            "total_extracted": 0,
            "success_first_attempt": 0,
            "success_after_repair": 0,
            "failed_validation": 0,
            "low_confidence_count": 0,
            "total_prompt_tokens": 0,
            "total_completion_tokens": 0,
        }

    def _get_client(self) -> GroqClient:
        """Lazy initialization of GroqClient."""
        if self.groq_client is None:
            self.groq_client = GroqClient(
                primary_model=self.model_version,
                fallback_model=self.config.get("models", {}).get("fallback", "openai/gpt-oss-20b"),
            )
        return self.groq_client

    def extract_single(
        self,
        item: RawItem,
        max_repairs: int = 2,
    ) -> tuple[StructuredRecord, dict[str, Any]]:
        """
        Extract structured behavioral signals from a single RawItem.

        Args:
            item: RawItem to process.
            max_repairs: Number of repair attempts if schema validation fails.

        Returns:
            (StructuredRecord, extraction_metrics)
        """
        client = self._get_client()
        pub_date = item.published_at.isoformat() if item.published_at else "Unknown"
        user_message = (
            f"Source: {item.source.value}\n"
            f"Published Date: {pub_date}\n"
            f"Platforms Mentioned: {', '.join(item.platform_mentioned) if item.platform_mentioned else 'none'}\n\n"
            f"Text: \"{item.text}\""
        )

        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_message},
        ]

        attempt = 1
        last_errors: list[str] = []
        parsed_data: Optional[dict[str, Any]] = None
        is_groww = "groww" in item.platform_mentioned

        while attempt <= (1 + max_repairs):
            try:
                t0 = time.perf_counter()
                resp = client.chat_completion(
                    messages=messages,
                    temperature=self.config.get("parameters", {}).get("temperature", 0.1),
                    max_tokens=self.config.get("parameters", {}).get("max_tokens", 1024),
                    response_format={"type": "json_object"},
                )
                latency = round(time.perf_counter() - t0, 3)

                usage_info = resp.get("usage", {})
                with self._stats_lock:
                    self.stats["total_prompt_tokens"] += usage_info.get("prompt_tokens", 0)
                    self.stats["total_completion_tokens"] += usage_info.get("completion_tokens", 0)

                raw_json = _clean_json_output(resp["content"])
                data = json.loads(raw_json)

                # Schema validation
                is_valid, errors = self.validator.validate_raw_dict(data, item.text)
                if is_valid:
                    parsed_data = data
                    break

                last_errors = errors
                logger.debug(
                    "Item %s attempt %d validation failed: %s", item.raw_id, attempt, errors
                )

            except Exception as e:
                last_errors = [str(e)]
                logger.warning(
                    "Extraction call error for item %s (attempt %d): %s", item.raw_id, attempt, e
                )

            # Prepare repair prompt for next attempt
            attempt += 1
            if attempt <= (1 + max_repairs):
                err_str = "; ".join(last_errors)
                repair_msg = (
                    f"You previously produced a JSON extraction that failed schema validation.\n\n"
                    f"Errors detected:\n{err_str}\n\n"
                    f"Original Text:\n\"{item.text}\"\n\n"
                    f"Please output ONLY a valid, corrected JSON object fixing all the above errors."
                )
                messages = [
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": repair_msg},
                ]

        # Final record construction
        with self._stats_lock:
            self.stats["total_extracted"] += 1

        if parsed_data:
            with self._stats_lock:
                if attempt == 1:
                    self.stats["success_first_attempt"] += 1
                else:
                    self.stats["success_after_repair"] += 1

            record = self.validator.to_structured_record(
                data=parsed_data,
                raw_id=item.raw_id,
                original_text=item.text,
                groww_specific_default=is_groww,
                model_version=self.model_version,
                prompt_version=self.prompt_version,
            )
            conf_metrics = self.confidence_scorer.evaluate_record(record)
            if conf_metrics.get("is_low_confidence"):
                with self._stats_lock:
                    self.stats["low_confidence_count"] += 1

            return record, {
                "attempts": attempt if attempt <= (1 + max_repairs) else (1 + max_repairs),
                "repaired": attempt > 1,
                "status": "success",
                "errors": [],
                "confidence_score": conf_metrics.get("overall_score", 0.0),
                "is_low_confidence": conf_metrics.get("is_low_confidence", False),
            }

        # Failed extraction fallback
        with self._stats_lock:
            self.stats["failed_validation"] += 1

        logger.error("Extraction failed for item %s after all attempts: %s", item.raw_id, last_errors)
        fallback_record = StructuredRecord(
            raw_id=item.raw_id,
            groww_specific=is_groww,
            lifecycle_stage=LifecycleStage.UNKNOWN,
            behavior=[],
            emotion=Emotion.UNKNOWN,
            segment=Segment(),
            outcome=Outcome.UNCLEAR,
            evidence_span=item.text[:60] if item.text else "",
            confidence=FieldConfidence(),
            extraction_status=ExtractionStatus.FAILED,
            model_version=self.model_version,
            prompt_version=self.prompt_version,
        )
        return fallback_record, {
            "attempts": attempt - 1,
            "repaired": False,
            "status": "failed",
            "errors": last_errors,
            "confidence_score": 0.0,
            "is_low_confidence": True,
        }

    def extract_batch(
        self,
        items: list[RawItem],
        max_workers: int = 5,
        on_progress: Optional[Callable[[int, int, StructuredRecord], None]] = None,
    ) -> tuple[list[StructuredRecord], dict[str, Any]]:
        """
        Process a batch of items with concurrency control and progress tracking.

        Args:
            items: List of RawItem objects to extract.
            max_workers: Concurrency level.
            on_progress: Optional callback invoked as each item completes: (completed, total, record).

        Returns:
            (records, summary_metrics)
        """
        records: list[StructuredRecord] = []
        total = len(items)
        completed = 0
        t_start = time.perf_counter()

        logger.info(
            "Starting batch extraction on %d items with %d workers (model=%s)",
            total, max_workers, self.model_version
        )

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_item = {executor.submit(self.extract_single, it): it for it in items}
            for future in concurrent.futures.as_completed(future_to_item):
                completed += 1
                record, meta = future.result()
                records.append(record)

                if on_progress:
                    on_progress(completed, total, record)

                if completed % 25 == 0 or completed == total:
                    pct = (completed / total) * 100
                    logger.info("Batch extraction progress: %d/%d (%.1f%%) completed", completed, total, pct)

        total_time = round(time.perf_counter() - t_start, 2)
        summary = {
            "total_items": total,
            "records_extracted": len(records),
            "success_rate_pct": round((len(records) - self.stats["failed_validation"]) / total * 100, 2) if total > 0 else 0.0,
            "stats": dict(self.stats),
            "elapsed_seconds": total_time,
        }
        return records, summary

