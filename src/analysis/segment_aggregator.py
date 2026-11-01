"""
Segment and multi-dimensional aggregation module for the SIP Discovery Engine.

Computes slices of extracted records across lifecycle stages, demographic segments,
platform affinity (Groww-specific vs agnostic), and data sources.
"""

from __future__ import annotations

from typing import Any, Optional

from src.models.schemas import Outcome, StructuredRecord
from src.utils.logging import get_logger

logger = get_logger(__name__)

NEGATIVE_OUTCOMES = {"paused", "reduced", "stopped"}


class SegmentAggregator:
    """
    Aggregates structured investor feedback records across multiple dimensions.
    """

    def __init__(self, negative_outcomes: Optional[set[str]] = None):
        self.negative_outcomes = negative_outcomes or NEGATIVE_OUTCOMES

    def aggregate_by_lifecycle(
        self,
        records: list[StructuredRecord],
        tagged_records: Optional[list[dict[str, Any]]] = None,
    ) -> dict[str, Any]:
        """
        Aggregate records by lifecycle stage.
        Computes count, share, drop-off rate, top emotions, and top themes.
        """
        total = max(1, len(records))
        by_stage: dict[str, list[StructuredRecord]] = {}
        tag_by_rec = {t["record_id"]: t for t in (tagged_records or [])}

        for r in records:
            stage = r.lifecycle_stage.value if hasattr(r.lifecycle_stage, "value") else str(r.lifecycle_stage)
            by_stage.setdefault(stage, []).append(r)

        result: dict[str, Any] = {}
        for stage, recs in sorted(by_stage.items(), key=lambda x: len(x[1]), reverse=True):
            n = len(recs)
            drop_count = sum(1 for r in recs if r.outcome.value.lower() in self.negative_outcomes)
            drop_rate = round(drop_count / n, 4) if n > 0 else 0.0

            # Emotions
            emotions: dict[str, int] = {}
            for r in recs:
                emo = r.emotion.value if hasattr(r.emotion, "value") else str(r.emotion)
                if emo != "unknown":
                    emotions[emo] = emotions.get(emo, 0) + 1

            # Top themes
            theme_counts: dict[str, int] = {}
            for r in recs:
                t_info = tag_by_rec.get(r.record_id)
                if t_info and t_info.get("primary_theme_name"):
                    th = t_info["primary_theme_name"]
                    theme_counts[th] = theme_counts.get(th, 0) + 1

            result[stage] = {
                "count": n,
                "share": round(n / total, 4),
                "drop_off_count": drop_count,
                "drop_off_rate": drop_rate,
                "top_emotions": dict(sorted(emotions.items(), key=lambda x: x[1], reverse=True)[:3]),
                "top_themes": dict(sorted(theme_counts.items(), key=lambda x: x[1], reverse=True)[:3]),
            }

        return result

    def aggregate_by_segment_dimensions(
        self,
        records: list[StructuredRecord],
    ) -> dict[str, dict[str, Any]]:
        """
        Aggregate records across demographic and psychographic segment dimensions:
        income_stability, age_band, source_of_money, and influencer.
        """
        total = max(1, len(records))
        dimensions = ["income_stability", "age_band", "source_of_money", "influencer"]
        result: dict[str, dict[str, Any]] = {}

        for dim in dimensions:
            dim_groups: dict[str, list[StructuredRecord]] = {}
            for r in records:
                seg = r.segment
                val = getattr(seg, dim, "unknown") if seg else "unknown"
                dim_groups.setdefault(val, []).append(r)

            dim_stats: dict[str, Any] = {}
            for val, recs in sorted(dim_groups.items(), key=lambda x: len(x[1]), reverse=True):
                n = len(recs)
                drop_count = sum(1 for r in recs if r.outcome.value.lower() in self.negative_outcomes)
                dim_stats[val] = {
                    "count": n,
                    "share": round(n / total, 4),
                    "drop_off_count": drop_count,
                    "drop_off_rate": round(drop_count / n, 4) if n > 0 else 0.0,
                }
            result[dim] = dim_stats

        return result

    def aggregate_by_platform_context(
        self,
        records: list[StructuredRecord],
        tagged_records: Optional[list[dict[str, Any]]] = None,
    ) -> dict[str, Any]:
        """
        Compare Groww-specific records vs platform-agnostic records.
        """
        groww_recs = [r for r in records if r.groww_specific]
        agnostic_recs = [r for r in records if not r.groww_specific]
        tag_by_rec = {t["record_id"]: t for t in (tagged_records or [])}

        def _stats(recs: list[StructuredRecord]) -> dict[str, Any]:
            n = len(recs)
            if n == 0:
                return {"count": 0, "share": 0.0, "drop_off_rate": 0.0, "top_themes": {}}
            drop_count = sum(1 for r in recs if r.outcome.value.lower() in self.negative_outcomes)
            themes: dict[str, int] = {}
            for r in recs:
                t = tag_by_rec.get(r.record_id)
                if t and t.get("primary_theme_name"):
                    th = t["primary_theme_name"]
                    themes[th] = themes.get(th, 0) + 1

            return {
                "count": n,
                "share": round(n / max(1, len(records)), 4),
                "drop_off_count": drop_count,
                "drop_off_rate": round(drop_count / n, 4),
                "top_themes": dict(sorted(themes.items(), key=lambda x: x[1], reverse=True)[:5]),
            }

        return {
            "groww_specific": _stats(groww_recs),
            "platform_agnostic": _stats(agnostic_recs),
        }

    def aggregate_by_source(
        self,
        records: list[StructuredRecord],
        source_mapping: dict[str, str],
        tagged_records: Optional[list[dict[str, Any]]] = None,
    ) -> dict[str, Any]:
        """
        Aggregate records by original source platform (Reddit, Quora, Play Store, etc.).
        """
        by_src: dict[str, list[StructuredRecord]] = {}
        tag_by_rec = {t["record_id"]: t for t in (tagged_records or [])}

        for r in records:
            src = source_mapping.get(r.raw_id, "unknown")
            by_src.setdefault(src, []).append(r)

        result: dict[str, Any] = {}
        total = max(1, len(records))

        for src, recs in sorted(by_src.items(), key=lambda x: len(x[1]), reverse=True):
            n = len(recs)
            drop_count = sum(1 for r in recs if r.outcome.value.lower() in self.negative_outcomes)
            themes: dict[str, int] = {}
            for r in recs:
                t = tag_by_rec.get(r.record_id)
                if t and t.get("primary_theme_name"):
                    th = t["primary_theme_name"]
                    themes[th] = themes.get(th, 0) + 1

            result[src] = {
                "count": n,
                "share": round(n / total, 4),
                "drop_off_count": drop_count,
                "drop_off_rate": round(drop_count / n, 4) if n > 0 else 0.0,
                "top_themes": dict(sorted(themes.items(), key=lambda x: x[1], reverse=True)[:3]),
            }

        return result

    def compute_all_aggregations(
        self,
        records: list[StructuredRecord],
        tagged_records: Optional[list[dict[str, Any]]] = None,
        source_mapping: Optional[dict[str, str]] = None,
    ) -> dict[str, Any]:
        """Run all aggregation slices and return unified dictionary."""
        source_mapping = source_mapping or {}
        return {
            "total_records": len(records),
            "lifecycle_breakdown": self.aggregate_by_lifecycle(records, tagged_records),
            "segment_breakdown": self.aggregate_by_segment_dimensions(records),
            "platform_breakdown": self.aggregate_by_platform_context(records, tagged_records),
            "source_breakdown": self.aggregate_by_source(records, source_mapping, tagged_records),
        }

