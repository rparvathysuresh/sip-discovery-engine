"""
Opportunity scoring engine for the SIP Discovery Engine.

Computes frequency, severity, breadth, and composite opportunity scores
for discovered thematic areas based on config/scoring.yaml.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import yaml

from src.models.schemas import OpportunityArea, Outcome, StructuredRecord
from src.utils.logging import get_logger

logger = get_logger(__name__)

DEFAULT_SCORING_CONFIG_PATH = Path("config/scoring.yaml")


class OpportunityScorer:
    """
    Computes weighted opportunity scores across frequency, severity, and breadth,
    and assigns statistical evidence levels.
    """

    def __init__(self, config_path: Optional[Path | str] = None):
        """Initialize with scoring configuration weights and thresholds."""
        self.config_path = Path(config_path or DEFAULT_SCORING_CONFIG_PATH)
        self.weights = {"frequency": 0.4, "severity": 0.4, "breadth": 0.2}
        self.negative_outcomes = {"paused", "reduced", "stopped"}
        self.thresholds = {
            "headline_min_count": 30,
            "headline_min_sources": 2,
            "supporting_min_count": 10,
            "anecdotal_max_count": 9,
        }
        self.load_config(self.config_path)

    def load_config(self, path: Path | str) -> None:
        """Load scoring weights and thresholds from YAML."""
        p = Path(path)
        if p.is_file():
            with open(p, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            self.weights = data.get("weights", self.weights)
            self.negative_outcomes = set(
                data.get("severity_negative_outcomes", ["paused", "reduced", "stopped"])
            )
            self.thresholds = data.get("thresholds", self.thresholds)
            logger.info("Loaded scoring configuration from %s", p)
        else:
            logger.warning("Scoring config %s not found, using defaults", p)

    def score_theme(
        self,
        theme_name: str,
        theme_category: str,
        records_in_theme: list[StructuredRecord],
        total_corpus_size: int,
        all_sources: Optional[set[str]] = None,
        max_frequency_count: Optional[int] = None,
        source_mapping: Optional[dict[str, str]] = None,
    ) -> OpportunityArea:
        """
        Score a single opportunity theme based on its associated records.

        Args:
            theme_name: Sub-theme name.
            theme_category: Top-level category.
            records_in_theme: Structured records tagged with this theme.
            total_corpus_size: Total number of records across the entire analyzed corpus.
            all_sources: Set of all unique source types observed across the corpus.
            max_frequency_count: Max count observed across all themes for relative scaling.
            source_mapping: Optional dict mapping raw_id -> source name.

        Returns:
            OpportunityArea object populated with all scores and breakdowns.
        """
        n = len(records_in_theme)
        total_corpus_size = max(1, total_corpus_size)

        # 1. Frequency Score
        freq_share = n / total_corpus_size
        if max_frequency_count and max_frequency_count > 0:
            freq_score = min(1.0, n / max_frequency_count)
        else:
            freq_score = min(1.0, freq_share * 5.0)  # scale share up to [0,1]

        # 2. Severity Score: Proportion where outcome in {paused, reduced, stopped}
        negative_count = 0
        known_outcomes = 0
        for r in records_in_theme:
            val = r.outcome.value if hasattr(r.outcome, "value") else str(r.outcome)
            if val != Outcome.UNCLEAR.value and val != "unknown":
                known_outcomes += 1
                if val.lower() in self.negative_outcomes:
                    negative_count += 1

        if n > 0:
            severity_score = negative_count / n
        else:
            severity_score = 0.0

        # 3. Breadth Score: Distinct sources and distinct segments
        sources_in_theme: set[str] = set()
        segments_in_theme: set[str] = set()

        for r in records_in_theme:
            # Source resolution
            src = None
            if source_mapping and r.raw_id in source_mapping:
                src = source_mapping[r.raw_id]
            if not src:
                src = "groww_app" if r.groww_specific else "general"
            sources_in_theme.add(src)

            # Segment resolution
            seg = r.segment
            if seg:
                seg_repr = f"{seg.age_band}:{seg.income_stability}"
                if seg_repr != "unknown:unknown":
                    segments_in_theme.add(seg_repr)

        total_sources_count = max(1, len(all_sources)) if all_sources else 6
        source_ratio = min(1.0, len(sources_in_theme) / total_sources_count)
        # Segments breadth normalized assuming ~8 distinct common demographic clusters
        segment_ratio = min(1.0, len(segments_in_theme) / 4.0)
        breadth_score = round(0.5 * source_ratio + 0.5 * segment_ratio, 4)

        # 4. Composite Score
        w_freq = self.weights.get("frequency", 0.4)
        w_sev = self.weights.get("severity", 0.4)
        w_brd = self.weights.get("breadth", 0.2)

        composite_score = (
            w_freq * freq_score +
            w_sev * severity_score +
            w_brd * breadth_score
        )
        composite_score = round(min(1.0, max(0.0, composite_score)), 4)

        # 5. Evidence Threshold Determination
        min_headline_n = self.thresholds.get("headline_min_count", 30)
        min_headline_src = self.thresholds.get("headline_min_sources", 2)
        min_supp_n = self.thresholds.get("supporting_min_count", 10)

        num_sources = len(sources_in_theme)
        if n >= min_headline_n and num_sources >= min_headline_src:
            evidence_level = "sufficient"
            sufficient_evidence = True
        elif n >= min_supp_n or num_sources >= 1:
            evidence_level = "directional"
            sufficient_evidence = False
        else:
            evidence_level = "insufficient"
            sufficient_evidence = False

        if n < min_supp_n:
            evidence_level = "insufficient"
            sufficient_evidence = False

        # Build breakdowns
        lifecycle_counts: dict[str, int] = {}
        source_counts: dict[str, int] = {}
        segment_counts: dict[str, int] = {}

        for r in records_in_theme:
            # Lifecycle breakdown
            lc_val = r.lifecycle_stage.value if hasattr(r.lifecycle_stage, "value") else str(r.lifecycle_stage)
            lifecycle_counts[lc_val] = lifecycle_counts.get(lc_val, 0) + 1

            # Source breakdown
            src = None
            if source_mapping and r.raw_id in source_mapping:
                src = source_mapping[r.raw_id]
            if not src:
                src = "groww_platform" if r.groww_specific else "platform_agnostic"
            source_counts[src] = source_counts.get(src, 0) + 1

            # Segment breakdown
            if r.segment:
                age = r.segment.age_band
                inc = r.segment.income_stability
                if age != "unknown":
                    segment_counts[f"age_{age}"] = segment_counts.get(f"age_{age}", 0) + 1
                if inc != "unknown":
                    segment_counts[f"inc_{inc}"] = segment_counts.get(f"inc_{inc}", 0) + 1

        return OpportunityArea(
            theme_name=theme_name,
            theme_category=theme_category,
            frequency_count=n,
            frequency_share=round(freq_share, 4),
            severity_score=round(severity_score, 4),
            breadth_score=breadth_score,
            composite_score=composite_score,
            segment_breakdown=segment_counts,
            lifecycle_breakdown=lifecycle_counts,
            source_breakdown=source_counts,
            sufficient_evidence=sufficient_evidence,
            evidence_level=evidence_level,
        )

    def score_all_themes(
        self,
        theme_groups: dict[str, tuple[str, list[StructuredRecord]]],
        total_corpus_size: int,
        all_sources: Optional[set[str]] = None,
        source_mapping: Optional[dict[str, str]] = None,
    ) -> list[OpportunityArea]:
        """
        Score and rank all themes in the corpus.

        Args:
            theme_groups: Mapping of theme_name -> (theme_category, records_in_theme)
            total_corpus_size: Total corpus size.
            all_sources: Set of unique source names.
            source_mapping: Mapping of raw_id -> source.

        Returns:
            List of OpportunityArea instances sorted by composite_score descending.
        """
        max_n = max([len(recs) for _, recs in theme_groups.values()]) if theme_groups else 1

        areas: list[OpportunityArea] = []
        for theme_name, (theme_category, records) in theme_groups.items():
            area = self.score_theme(
                theme_name=theme_name,
                theme_category=theme_category,
                records_in_theme=records,
                total_corpus_size=total_corpus_size,
                all_sources=all_sources,
                max_frequency_count=max_n,
                source_mapping=source_mapping,
            )
            areas.append(area)

        # Sort by composite score descending, then frequency count descending
        areas.sort(key=lambda a: (a.composite_score, a.frequency_count), reverse=True)
        return areas

