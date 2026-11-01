"""
Continuer vs. Dropper statistical comparison engine for the SIP Discovery Engine.

Compares investors who persist with their SIP (outcome = continued) against
investors who churn or lapse (outcome in {paused, reduced, stopped}) across
emotions, checking behaviors, drivers, barriers, and themes.
"""

from __future__ import annotations

import math
from typing import Any, Optional

from src.models.schemas import Outcome, StructuredRecord
from src.utils.logging import get_logger

logger = get_logger(__name__)

DROPPER_OUTCOMES = {"paused", "reduced", "stopped"}


def _chi2_contingency_2x2(a: int, b: int, c: int, d: int) -> tuple[float, float, float]:
    """
    Compute 2x2 contingency table Chi-squared test with Yates' continuity correction.

    Table layout:
               Feature Present    Feature Absent    Total
    Droppers        a                   b           a+b (R1)
    Continuers      c                   d           c+d (R2)
    Total          a+c (C1)            b+d (C2)       N

    Returns:
        (chi2_stat, p_value, odds_ratio)
    """
    n = a + b + c + d
    if n == 0 or (a + b) == 0 or (c + d) == 0 or (a + c) == 0 or (b + d) == 0:
        return 0.0, 1.0, 1.0

    # Odds ratio with Haldane-Anscombe correction (+0.5) to avoid div-by-zero
    or_num = (a + 0.5) * (d + 0.5)
    or_den = (b + 0.5) * (c + 0.5)
    odds_ratio = round(or_num / or_den, 3)

    # Yates' continuity corrected Chi-square
    numerator = n * (max(0.0, abs(a * d - b * c) - (n / 2.0)) ** 2)
    denominator = (a + b) * (c + d) * (a + c) * (b + d)

    if denominator == 0:
        return 0.0, 1.0, odds_ratio

    chi2 = numerator / denominator
    # For df = 1, p-value = erfc(sqrt(chi2) / sqrt(2))
    p_value = math.erfc(math.sqrt(max(0.0, chi2)) / math.sqrt(2.0))
    p_value = min(1.0, max(0.0, p_value))

    return round(chi2, 4), round(p_value, 5), odds_ratio


class ContinuerDropperComparator:
    """
    Conducts comparative analysis between Continuers and Droppers.
    """

    def __init__(self, dropper_outcomes: Optional[set[str]] = None):
        self.dropper_outcomes = dropper_outcomes or DROPPER_OUTCOMES

    def split_groups(
        self, records: list[StructuredRecord]
    ) -> tuple[list[StructuredRecord], list[StructuredRecord], list[StructuredRecord]]:
        """
        Split records into (continuers, droppers, unclear).
        """
        continuers: list[StructuredRecord] = []
        droppers: list[StructuredRecord] = []
        unclear: list[StructuredRecord] = []

        for r in records:
            out_val = r.outcome.value.lower() if hasattr(r.outcome, "value") else str(r.outcome).lower()
            if out_val == Outcome.CONTINUED.value:
                continuers.append(r)
            elif out_val in self.dropper_outcomes:
                droppers.append(r)
            else:
                unclear.append(r)

        return continuers, droppers, unclear

    def compare_dimension(
        self,
        dimension_name: str,
        continuers: list[StructuredRecord],
        droppers: list[StructuredRecord],
        value_extractor: Any,
    ) -> list[dict[str, Any]]:
        """
        Compare distribution of categorical values for a given dimension.

        Args:
            dimension_name: Label for the dimension.
            continuers: List of continuer records.
            droppers: List of dropper records.
            value_extractor: Callable taking a StructuredRecord and returning list[str] or str.

        Returns:
            List of feature comparison dicts sorted by effect size / significance.
        """
        n_cont = len(continuers)
        n_drop = len(droppers)

        if n_cont == 0 and n_drop == 0:
            return []

        # Count frequencies
        cont_counts: dict[str, int] = {}
        drop_counts: dict[str, int] = {}
        all_values: set[str] = set()

        for r in continuers:
            extracted = value_extractor(r)
            vals = extracted if isinstance(extracted, list) else [extracted]
            for v in vals:
                if v and v.lower() != "unknown":
                    v_clean = v.strip().lower()
                    cont_counts[v_clean] = cont_counts.get(v_clean, 0) + 1
                    all_values.add(v_clean)

        for r in droppers:
            extracted = value_extractor(r)
            vals = extracted if isinstance(extracted, list) else [extracted]
            for v in vals:
                if v and v.lower() != "unknown":
                    v_clean = v.strip().lower()
                    drop_counts[v_clean] = drop_counts.get(v_clean, 0) + 1
                    all_values.add(v_clean)

        results: list[dict[str, Any]] = []

        for val in sorted(all_values):
            a = drop_counts.get(val, 0)
            b = max(0, n_drop - a)
            c = cont_counts.get(val, 0)
            d = max(0, n_cont - c)

            pct_drop = round((a / n_drop * 100), 2) if n_drop > 0 else 0.0
            pct_cont = round((c / n_cont * 100), 2) if n_cont > 0 else 0.0

            chi2, p_val, odds_ratio = _chi2_contingency_2x2(a, b, c, d)

            # Significance flag
            if p_val < 0.001:
                sig = "***"
            elif p_val < 0.01:
                sig = "**"
            elif p_val < 0.05:
                sig = "*"
            else:
                sig = "ns"

            results.append({
                "dimension": dimension_name,
                "value": val,
                "dropper_count": a,
                "dropper_pct": pct_drop,
                "continuer_count": c,
                "continuer_pct": pct_cont,
                "diff_pct": round(pct_drop - pct_cont, 2),
                "odds_ratio": odds_ratio,
                "chi2": chi2,
                "p_value": p_val,
                "significance": sig,
            })

        # Sort by absolute percentage difference descending
        results.sort(key=lambda x: abs(x["diff_pct"]), reverse=True)
        return results

    def run_full_comparison(
        self,
        records: list[StructuredRecord],
        tagged_records: Optional[list[dict[str, Any]]] = None,
    ) -> dict[str, Any]:
        """
        Run comprehensive statistical comparison between Continuers and Droppers.
        """
        continuers, droppers, unclear = self.split_groups(records)
        tag_by_rec = {t["record_id"]: t for t in (tagged_records or [])}

        summary = {
            "total_records": len(records),
            "continuers_count": len(continuers),
            "continuers_share": round(len(continuers) / max(1, len(records)), 4),
            "droppers_count": len(droppers),
            "droppers_share": round(len(droppers) / max(1, len(records)), 4),
            "unclear_count": len(unclear),
            "unclear_share": round(len(unclear) / max(1, len(records)), 4),
        }

        # Dimensions to compare
        emotions_comp = self.compare_dimension(
            "emotion", continuers, droppers,
            lambda r: r.emotion.value if hasattr(r.emotion, "value") else str(r.emotion)
        )

        lifecycle_comp = self.compare_dimension(
            "lifecycle_stage", continuers, droppers,
            lambda r: r.lifecycle_stage.value if hasattr(r.lifecycle_stage, "value") else str(r.lifecycle_stage)
        )

        checking_comp = self.compare_dimension(
            "checking_behavior", continuers, droppers,
            lambda r: r.checking_behavior
        )

        outside_comp = self.compare_dimension(
            "outside_app_behavior", continuers, droppers,
            lambda r: r.outside_app_behavior
        )

        themes_comp = self.compare_dimension(
            "primary_theme", continuers, droppers,
            lambda r: tag_by_rec.get(r.record_id, {}).get("primary_theme_name", "unknown")
        )

        # High-level summary highlights
        top_dropper_signals = [
            f"{r['value']} (Droppers: {r['dropper_pct']}%, Continuers: {r['continuer_pct']}%, OR: {r['odds_ratio']})"
            for r in themes_comp[:5] if r['diff_pct'] > 0
        ]
        top_continuer_signals = [
            f"{r['value']} (Continuers: {r['continuer_pct']}%, Droppers: {r['dropper_pct']}%, OR: {r['odds_ratio']})"
            for r in themes_comp if r['diff_pct'] < 0
        ][:5]

        return {
            "summary": summary,
            "top_dropper_signals": top_dropper_signals,
            "top_continuer_signals": top_continuer_signals,
            "emotions": emotions_comp,
            "lifecycle_stages": lifecycle_comp,
            "checking_behavior": checking_comp,
            "outside_app_behavior": outside_comp,
            "primary_themes": themes_comp,
        }

