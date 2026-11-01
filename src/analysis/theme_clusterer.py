"""
Theme clustering and tagging engine for the SIP Discovery Engine.

Groups extracted structured records into thematic opportunity areas based on
the hierarchical codebook defined in config/codebook_v1.yaml.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional

import yaml

from src.models.schemas import StructuredRecord
from src.utils.logging import get_logger

logger = get_logger(__name__)

DEFAULT_CODEBOOK_PATH = Path("config/codebook_v1.yaml")


class ThemeClusterer:
    """
    Hierarchical theme clusterer and tagger for investor feedback records.
    Maps structured behavioral signals and evidence to codebook themes.
    """

    def __init__(self, codebook_path: Optional[Path | str] = None):
        """
        Initialize ThemeClusterer with a codebook configuration.
        """
        self.codebook_path = Path(codebook_path or DEFAULT_CODEBOOK_PATH)
        self.categories: list[dict[str, Any]] = []
        self.themes_by_id: dict[str, dict[str, Any]] = {}
        self.category_by_id: dict[str, dict[str, Any]] = {}
        self._compiled_patterns: dict[str, list[re.Pattern]] = {}

        self.load_codebook(self.codebook_path)

    def load_codebook(self, path: Path | str) -> None:
        """Load codebook YAML file and index all categories and sub-themes."""
        p = Path(path)
        if not p.is_file():
            raise FileNotFoundError(f"Codebook file not found: {p}")

        with open(p, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        self.version = data.get("version", "v1.0")
        self.categories = data.get("categories", [])
        self.themes_by_id.clear()
        self.category_by_id.clear()
        self._compiled_patterns.clear()

        for cat in self.categories:
            cat_id = cat["id"]
            self.category_by_id[cat_id] = {
                "id": cat_id,
                "name": cat["name"],
                "description": cat.get("description", ""),
            }
            for sub in cat.get("sub_themes", []):
                sub_id = sub["id"]
                theme_info = {
                    "id": sub_id,
                    "category_id": cat_id,
                    "category_name": cat["name"],
                    "name": sub["name"],
                    "description": sub.get("description", ""),
                    "keywords": sub.get("keywords", []),
                    "typical_emotions": sub.get("typical_emotions", []),
                    "typical_outcomes": sub.get("typical_outcomes", []),
                }
                self.themes_by_id[sub_id] = theme_info

                # Precompile keyword patterns
                patterns = []
                for kw in theme_info["keywords"]:
                    cleaned_kw = re.sub(r"[₹\$\€]", "", kw).strip().lower()
                    cleaned_kw = re.sub(r"\b(?:rs|inr)\.?\s*", "", cleaned_kw).strip()
                    if cleaned_kw:
                        escaped = re.escape(cleaned_kw)
                        pattern = re.compile(rf"(?:\b|_){escaped}(?:\b|_)", re.IGNORECASE)
                        patterns.append((cleaned_kw, pattern))
                self._compiled_patterns[sub_id] = patterns

        logger.info(
            "Loaded codebook %s: %d categories, %d sub-themes from %s",
            self.version, len(self.category_by_id), len(self.themes_by_id), p
        )

    def get_all_themes(self) -> list[dict[str, Any]]:
        """Return all sub-theme definitions."""
        return list(self.themes_by_id.values())

    def get_all_categories(self) -> list[dict[str, Any]]:
        """Return all top-level category definitions."""
        return list(self.category_by_id.values())

    def match_record(self, record: StructuredRecord) -> dict[str, Any]:
        """
        Classify a single StructuredRecord against the theme codebook.

        Returns a dictionary with:
            - record_id: str
            - raw_id: str
            - primary_theme_id: str
            - primary_theme_name: str
            - category_id: str
            - category_name: str
            - match_score: float
            - secondary_themes: list[str]
            - matched_keywords: list[str]
        """
        # Assemble searchable textual context from the record
        text_parts = [
            record.barrier_or_trigger_to_stop,
            record.confusion_or_worry_in_app,
            record.expectation,
            record.driver_to_start,
            record.checking_behavior,
            record.outside_app_behavior,
            record.evidence_span,
            " ".join(record.behavior) if record.behavior else "",
        ]
        # Filter out "unknown" placeholders
        meaningful_text = " ".join([p for p in text_parts if p and p.lower() != "unknown"]).lower()
        normalized_text = re.sub(r"[₹\$\€]", " ", meaningful_text)
        normalized_text = re.sub(r"\b(?:rs|inr)\.?\s*", " ", normalized_text, flags=re.IGNORECASE)

        emotion_str = record.emotion.value.lower() if record.emotion else "unknown"
        outcome_str = record.outcome.value.lower() if record.outcome else "unclear"

        theme_scores: dict[str, float] = {}
        theme_matches: dict[str, list[str]] = {}

        for theme_id, info in self.themes_by_id.items():
            score = 0.0
            matched_kw: list[str] = []

            # 1. Keyword / pattern matching
            pattern_tuples = self._compiled_patterns.get(theme_id, [])
            for raw_kw, p in pattern_tuples:
                if p.search(normalized_text) or p.search(meaningful_text):
                    score += 2.0
                    matched_kw.append(raw_kw)

            # Substring matching fallback for punctuation-adjacent terms
            for raw_kw, _ in pattern_tuples:
                if raw_kw in normalized_text and raw_kw not in matched_kw:
                    score += 1.5
                    matched_kw.append(raw_kw)

            # 2. Emotion alignment bonus
            if emotion_str != "unknown" and emotion_str in info["typical_emotions"]:
                score += 0.5

            # 3. Outcome alignment bonus
            if outcome_str != "unclear" and outcome_str in info["typical_outcomes"]:
                score += 0.5

            if score > 0:
                theme_scores[theme_id] = score
                theme_matches[theme_id] = matched_kw

        # Determine primary and secondary themes
        if theme_scores:
            sorted_themes = sorted(theme_scores.items(), key=lambda x: x[1], reverse=True)
            primary_id, top_score = sorted_themes[0]
            secondary = [t_id for t_id, s in sorted_themes[1:4] if s >= 1.0]

            theme_meta = self.themes_by_id[primary_id]
            return {
                "record_id": record.record_id,
                "raw_id": record.raw_id,
                "primary_theme_id": primary_id,
                "primary_theme_name": theme_meta["name"],
                "category_id": theme_meta["category_id"],
                "category_name": theme_meta["category_name"],
                "match_score": round(top_score, 2),
                "secondary_themes": secondary,
                "matched_keywords": theme_matches.get(primary_id, []),
                "classified": True,
            }

        # Fallback heuristic classification based on emotion + barrier presence
        fallback_theme = self._infer_fallback_theme(record)
        if fallback_theme:
            theme_meta = self.themes_by_id[fallback_theme]
            return {
                "record_id": record.record_id,
                "raw_id": record.raw_id,
                "primary_theme_id": fallback_theme,
                "primary_theme_name": theme_meta["name"],
                "category_id": theme_meta["category_id"],
                "category_name": theme_meta["category_name"],
                "match_score": 0.5,
                "secondary_themes": [],
                "matched_keywords": ["heuristic_inferred"],
                "classified": True,
            }

        # Unclassified general record
        return {
            "record_id": record.record_id,
            "raw_id": record.raw_id,
            "primary_theme_id": "general_sip_inquiry",
            "primary_theme_name": "General SIP Discussion",
            "category_id": "other",
            "category_name": "Other / General",
            "match_score": 0.0,
            "secondary_themes": [],
            "matched_keywords": [],
            "classified": False,
        }

    def _infer_fallback_theme(self, record: StructuredRecord) -> Optional[str]:
        """Apply high-level heuristics when exact keywords are missing."""
        barrier = record.barrier_or_trigger_to_stop.lower()
        confusion = record.confusion_or_worry_in_app.lower()
        emotion = record.emotion.value.lower()
        outcome = record.outcome.value.lower()

        if "mandate" in barrier or "autopay" in barrier or "deduct" in barrier:
            return "autopay_mandate_failure"
        if "kyc" in barrier or "bank" in barrier or "onboard" in barrier:
            return "onboarding_kyc_friction"
        if "return" in barrier or "loss" in barrier or "profit" in barrier:
            return "negative_short_term_returns"
        if "pause" in barrier or "cancel" in barrier:
            return "pause_vs_cancel_confusion"
        if "reddit" in record.outside_app_behavior.lower() or "youtube" in record.outside_app_behavior.lower():
            return "seeking_outside_validation"
        if emotion in {"panic", "fear"} and outcome in {"stopped", "paused"}:
            return "market_volatility_panic"
        if emotion in {"frustration", "anger"}:
            return "platform_distrust_and_glitches"
        if emotion in {"confusion"}:
            return "confusing_statements_and_taxes"

        return None

    def tag_records(self, records: list[StructuredRecord]) -> list[dict[str, Any]]:
        """Tag a list of StructuredRecords with theme assignments."""
        tagged = []
        for r in records:
            tag_info = self.match_record(r)
            tagged.append(tag_info)
        return tagged

    def compute_coverage(self, records: list[StructuredRecord]) -> dict[str, Any]:
        """
        Evaluate codebook coverage over a dataset of structured records.
        Returns coverage percentage, category counts, and unclassified count.
        """
        if not records:
            return {
                "total_records": 0,
                "classified_records": 0,
                "coverage_pct": 0.0,
                "theme_counts": {},
                "category_counts": {},
            }

        tagged = self.tag_records(records)
        classified_count = sum(1 for t in tagged if t["classified"])
        coverage_pct = round((classified_count / len(records)) * 100, 2)

        theme_counts: dict[str, int] = {}
        category_counts: dict[str, int] = {}

        for t in tagged:
            theme_name = t["primary_theme_name"]
            cat_name = t["category_name"]
            theme_counts[theme_name] = theme_counts.get(theme_name, 0) + 1
            category_counts[cat_name] = category_counts.get(cat_name, 0) + 1

        return {
            "total_records": len(records),
            "classified_records": classified_count,
            "coverage_pct": coverage_pct,
            "theme_counts": dict(sorted(theme_counts.items(), key=lambda x: x[1], reverse=True)),
            "category_counts": dict(sorted(category_counts.items(), key=lambda x: x[1], reverse=True)),
        }
