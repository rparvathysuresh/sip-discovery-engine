#!/usr/bin/env python3
"""
scripts/run_analysis.py
Orchestrates Phase 4: Theme Clustering, Opportunity Scoring, Segment Aggregation,
and Continuer vs. Dropper Statistical Comparison.

Usage:
    python scripts/run_analysis.py [--db-path DB] [--output-dir DIR] [--dry-run]
"""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.analysis.continuer_dropper_comparator import ContinuerDropperComparator
from src.analysis.opportunity_scorer import OpportunityScorer
from src.analysis.segment_aggregator import SegmentAggregator
from src.analysis.theme_clusterer import ThemeClusterer
from src.db.connection import get_connection, init_db, insert_evidence_log_entry, insert_opportunity_area
from src.models.schemas import (
    Emotion,
    EvidenceLogEntry,
    FieldConfidence,
    OpportunityArea,
    Outcome,
    Segment,
    StructuredRecord,
)
from src.utils.logging import get_logger

logger = get_logger("run_analysis")


def load_structured_records(conn: sqlite3.Connection) -> list[StructuredRecord]:
    """Load all records from structured_records table."""
    cursor = conn.execute("SELECT * FROM structured_records ORDER BY extracted_at DESC")
    rows = cursor.fetchall()
    records: list[StructuredRecord] = []

    for r in rows:
        behavior_list = json.loads(r["behavior"]) if r["behavior"] else []
        seg_dict = json.loads(r["segment"]) if r["segment"] else {}
        conf_dict = json.loads(r["confidence"]) if r["confidence"] else {}

        # Safely parse Enums
        try:
            emotion_val = Emotion(r["emotion"])
        except ValueError:
            emotion_val = Emotion.UNKNOWN

        try:
            outcome_val = Outcome(r["outcome"])
        except ValueError:
            outcome_val = Outcome.UNCLEAR

        rec = StructuredRecord(
            record_id=r["record_id"],
            raw_id=r["raw_id"],
            groww_specific=bool(r["groww_specific"]),
            lifecycle_stage=r["lifecycle_stage"],
            behavior=behavior_list,
            driver_to_start=r["driver_to_start"] or "unknown",
            expectation=r["expectation"] or "unknown",
            barrier_or_trigger_to_stop=r["barrier_or_trigger_to_stop"] or "unknown",
            confusion_or_worry_in_app=r["confusion_or_worry_in_app"] or "unknown",
            checking_behavior=r["checking_behavior"] or "unknown",
            outside_app_behavior=r["outside_app_behavior"] or "unknown",
            emotion=emotion_val,
            segment=Segment(**seg_dict),
            outcome=outcome_val,
            evidence_span=r["evidence_span"] or "",
            confidence=FieldConfidence(**conf_dict),
            extracted_at=datetime.fromisoformat(r["extracted_at"]),
            extraction_status=r["extraction_status"],
            model_version=r["model_version"] or "unknown",
            prompt_version=r["prompt_version"] or "v1.0",
        )
        records.append(rec)

    return records


def load_source_mapping(conn: sqlite3.Connection) -> dict[str, str]:
    """Map raw_id -> source string from raw_items table."""
    cursor = conn.execute("SELECT raw_id, source FROM raw_items")
    mapping = {}
    for r in cursor.fetchall():
        mapping[r["raw_id"]] = r["source"]
    return mapping


def generate_analysis_markdown(
    opportunity_areas: list[OpportunityArea],
    coverage_info: dict[str, Any],
    aggregations: dict[str, Any],
    comparison: dict[str, Any],
    output_path: Path,
) -> None:
    """Generate a clean markdown report of Stage 4 analysis findings."""
    md = [
        "# SIP Discovery Engine — Phase 4 Analysis Summary",
        f"*Generated at: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}*",
        "",
        "## 1. Executive Summary & Codebook Coverage",
        f"- **Total Records Analyzed**: {coverage_info.get('total_records', 0):,}",
        f"- **Thematically Classified**: {coverage_info.get('classified_records', 0):,} ({coverage_info.get('coverage_pct', 0.0)}%)",
        f"- **Distinct Opportunity Areas Scored**: {len(opportunity_areas)}",
        "",
        "## 2. Ranked Opportunity Areas",
        "| Rank | Theme Name | Category | Count | Share | Severity | Breadth | Composite | Evidence Level |",
        "|---|---|---|---|---|---|---|---|---|",
    ]

    for i, a in enumerate(opportunity_areas, 1):
        md.append(
            f"| {i} | **{a.theme_name}** | {a.theme_category} | {a.frequency_count} | "
            f"{a.frequency_share:.1%} | {a.severity_score:.2f} | {a.breadth_score:.2f} | "
            f"**{a.composite_score:.4f}** | `{a.evidence_level}` |"
        )

    md.extend([
        "",
        "## 3. Continuer vs. Dropper Statistical Highlights",
        f"- **Continuers**: {comparison['summary']['continuers_count']} ({comparison['summary']['continuers_share']:.1%})",
        f"- **Droppers (Churn/Pause/Stop)**: {comparison['summary']['droppers_count']} ({comparison['summary']['droppers_share']:.1%})",
        "",
        "### Top Dropper Correlates (Higher Churn Risk)",
    ])
    for sig in comparison.get("top_dropper_signals", [])[:5]:
        md.append(f"- 🔴 {sig}")

    md.append("\n### Top Continuer Correlates (Retention Signals)")
    for sig in comparison.get("top_continuer_signals", [])[:5]:
        md.append(f"- 🟢 {sig}")

    md.extend([
        "",
        "## 4. Key Emotion Distributions",
        "| Emotion | Dropper % | Continuer % | Diff % | Odds Ratio | p-value | Sig |",
        "|---|---|---|---|---|---|---|",
    ])
    for emo in comparison.get("emotions", [])[:8]:
        md.append(
            f"| {emo['value'].capitalize()} | {emo['dropper_pct']}% | {emo['continuer_pct']}% | "
            f"{emo['diff_pct']:+}% | {emo['odds_ratio']} | {emo['p_value']:.4f} | {emo['significance']} |"
        )

    md.extend([
        "",
        "## 5. Platform Context (Groww vs. Platform Agnostic)",
        f"- **Groww Specific**: {aggregations['platform_breakdown']['groww_specific']['count']} items "
        f"(Drop-off Rate: {aggregations['platform_breakdown']['groww_specific']['drop_off_rate']:.1%})",
        f"- **Platform Agnostic**: {aggregations['platform_breakdown']['platform_agnostic']['count']} items "
        f"(Drop-off Rate: {aggregations['platform_breakdown']['platform_agnostic']['drop_off_rate']:.1%})",
        "",
        "---",
        "*Report compiled by SIP Discovery Engine Analysis Runner (Phase 4)*",
    ])

    output_path.write_text("\n".join(md), encoding="utf-8")
    logger.info("Saved analysis summary report to %s", output_path)


def run_analysis_pipeline(
    db_path: Optional[str] = None,
    codebook_path: Optional[str] = None,
    scoring_config_path: Optional[str] = None,
    output_dir: str = "data",
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Execute end-to-end Phase 4 analysis pipeline.
    """
    t_start = time.perf_counter()
    logger.info("Initializing database connection (db_path=%s)...", db_path or "default")
    conn = init_db(db_path)

    records = load_structured_records(conn)
    total_records = len(records)
    logger.info("Loaded %d structured records from database.", total_records)

    if total_records == 0:
        print("\n[WARNING] No records found in structured_records table.")
        print("Please run scripts/run_extraction.py first to extract structured records from filtered_items.\n")
        conn.close()
        return {"total_records": 0, "opportunity_areas": []}

    source_mapping = load_source_mapping(conn)
    all_sources = set(source_mapping.values()) if source_mapping else {"groww_app", "general"}

    # 1. Theme Clustering & Tagging
    logger.info("Step 4.1: Initializing ThemeClusterer...")
    clusterer = ThemeClusterer(codebook_path=codebook_path)
    tagged_records = clusterer.tag_records(records)
    coverage_info = clusterer.compute_coverage(records)
    logger.info(
        "Theme Tagging complete: %d/%d covered (%.1f%%)",
        coverage_info["classified_records"], total_records, coverage_info["coverage_pct"]
    )

    # Group records by assigned primary theme
    theme_groups: dict[str, tuple[str, list[StructuredRecord]]] = {}
    for r, tag in zip(records, tagged_records):
        th_name = tag["primary_theme_name"]
        cat_name = tag["category_name"]
        if th_name not in theme_groups:
            theme_groups[th_name] = (cat_name, [])
        theme_groups[th_name][1].append(r)

    # 2. Opportunity Scoring
    logger.info("Step 4.2: Scoring opportunity areas...")
    scorer = OpportunityScorer(config_path=scoring_config_path)
    opportunity_areas = scorer.score_all_themes(
        theme_groups=theme_groups,
        total_corpus_size=total_records,
        all_sources=all_sources,
        source_mapping=source_mapping,
    )
    logger.info("Scored and ranked %d opportunity areas.", len(opportunity_areas))

    # 3. Segment Aggregations
    logger.info("Step 4.3: Computing multi-dimensional segment breakdowns...")
    aggregator = SegmentAggregator()
    aggregations = aggregator.compute_all_aggregations(
        records=records,
        tagged_records=tagged_records,
        source_mapping=source_mapping,
    )

    # 4. Continuer vs Dropper Statistical Comparison
    logger.info("Step 4.4: Computing Continuer vs. Dropper statistical comparison...")
    comparator = ContinuerDropperComparator()
    comparison = comparator.run_full_comparison(records, tagged_records)

    elapsed_time = round(time.perf_counter() - t_start, 2)

    # 5. Persistence & Export
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not dry_run:
        logger.info("Persisting %d opportunity areas to database...", len(opportunity_areas))
        conn.execute("DELETE FROM opportunity_areas")
        for area in opportunity_areas:
            insert_opportunity_area(conn, area)

        # Log to evidence log
        analysis_metrics = {
            "total_records_analyzed": total_records,
            "classified_records": coverage_info["classified_records"],
            "coverage_pct": coverage_info["coverage_pct"],
            "opportunity_areas_count": len(opportunity_areas),
            "top_theme": opportunity_areas[0].theme_name if opportunity_areas else None,
            "top_composite_score": opportunity_areas[0].composite_score if opportunity_areas else None,
            "elapsed_seconds": elapsed_time,
        }
        evidence_entry = EvidenceLogEntry(
            pipeline_stage="analysis",
            event_type="stage_completed",
            details=analysis_metrics,
        )
        insert_evidence_log_entry(conn, evidence_entry)

    # Export JSON and CSV
    opp_json_path = out_dir / "opportunity_areas.json"
    opp_json_data = [a.model_dump(mode="json") for a in opportunity_areas]
    opp_json_path.write_text(json.dumps(opp_json_data, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Saved opportunity areas to %s", opp_json_path)

    opp_csv_path = out_dir / "opportunity_areas.csv"
    with open(opp_csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow([
            "rank",
            "opportunity_id",
            "theme_name",
            "theme_category",
            "frequency_count",
            "frequency_share",
            "severity_score",
            "breadth_score",
            "composite_score",
            "evidence_level",
            "sufficient_evidence",
        ])
        for rank, a in enumerate(opportunity_areas, 1):
            writer.writerow([
                rank,
                a.opportunity_id,
                a.theme_name,
                a.theme_category,
                a.frequency_count,
                f"{a.frequency_share:.4f}",
                f"{a.severity_score:.4f}" if a.severity_score is not None else "",
                f"{a.breadth_score:.4f}",
                f"{a.composite_score:.4f}",
                a.evidence_level,
                "Yes" if a.sufficient_evidence else "No",
            ])
    logger.info("Saved opportunity areas CSV to %s", opp_csv_path)

    # Export Continuer vs Dropper JSON
    comp_json_path = out_dir / "continuer_vs_dropper.json"
    comp_json_path.write_text(json.dumps(comparison, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Saved Continuer vs. Dropper comparison to %s", comp_json_path)

    # Export Aggregations JSON
    agg_json_path = out_dir / "segment_aggregations.json"
    agg_json_path.write_text(json.dumps(aggregations, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Saved segment aggregations to %s", agg_json_path)

    # Export Markdown Summary
    md_summary_path = out_dir / "analysis_summary.md"
    generate_analysis_markdown(opportunity_areas, coverage_info, aggregations, comparison, md_summary_path)

    conn.close()

    return {
        "total_records": total_records,
        "coverage": coverage_info,
        "opportunity_areas": opportunity_areas,
        "aggregations": aggregations,
        "comparison": comparison,
        "elapsed_seconds": elapsed_time,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Phase 4 Theme Clustering and Opportunity Scoring.")
    parser.add_argument("--db-path", type=str, default=None, help="Path to SQLite database.")
    parser.add_argument("--codebook", type=str, default="config/codebook_v1.yaml", help="Path to codebook YAML.")
    parser.add_argument("--scoring-config", type=str, default="config/scoring.yaml", help="Path to scoring YAML.")
    parser.add_argument("--output-dir", type=str, default="data", help="Directory for output files.")
    parser.add_argument("--dry-run", action="store_true", help="Run without persisting to DB.")

    args = parser.parse_args()

    print("\n" + "=" * 65)
    print("SIP Discovery Engine — Phase 4 Theme Clustering & Scoring")
    print("=" * 65)
    print(f"Database:       {args.db_path or 'default'}")
    print(f"Codebook:       {args.codebook}")
    print(f"Scoring config: {args.scoring_config}")
    print(f"Output dir:     {args.output_dir}")
    print(f"Dry run:        {args.dry_run}")
    print("-" * 65 + "\n")

    results = run_analysis_pipeline(
        db_path=args.db_path,
        codebook_path=args.codebook,
        scoring_config_path=args.scoring_config,
        output_dir=args.output_dir,
        dry_run=args.dry_run,
    )

    areas: list[OpportunityArea] = results.get("opportunity_areas", [])
    if areas:
        print("\n" + "=" * 80)
        print("TOP RANKED OPPORTUNITY AREAS")
        print("=" * 80)
        print(f"{'Rank':<5}{'Theme Name':<32}{'Category':<22}{'Count':<7}{'Score':<9}{'Level':<12}")
        print("-" * 80)
        for i, a in enumerate(areas[:10], 1):
            print(f"{i:<5}{a.theme_name[:30]:<32}{a.theme_category[:20]:<22}{a.frequency_count:<7}{a.composite_score:<9.4f}{a.evidence_level:<12}")
        print("=" * 80)

    print(f"\nPhase 4 Analysis complete in {results.get('elapsed_seconds', 0.0)}s.")


if __name__ == "__main__":
    main()
