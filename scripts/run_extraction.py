#!/usr/bin/env python3
"""
scripts/run_extraction.py — CLI runner for Stage 3 LLM Structured Extraction.

Loads filtered items from the database, executes batch extraction via Groq,
validates schema compliance, audits confidence, writes results to the
structured_records table, and logs token usage to the AI Evidence Log.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.db.connection import (
    get_connection,
    init_db,
    insert_evidence_log_entry,
    insert_structured_record,
)
from src.extraction.extractor import StructuredExtractor
from src.models.schemas import (
    EvidenceLogEntry,
    ExtractionStatus,
    RawItem,
    RawItemMetadata,
    SourceType,
    StructuredRecord,
)
from src.utils.config import get_extraction_config
from src.utils.logging import get_logger

logger = get_logger("run_extraction")


def load_filtered_items_from_db(
    conn, limit: Optional[int] = None, skip_already_extracted: bool = False
) -> list[RawItem]:
    """Load items from filtered_items table into RawItem records."""
    cursor = conn.cursor()

    query = """
        SELECT f.raw_id, f.source, f.source_native_id, f.source_url, f.platform_mentioned,
               f.published_at, f.text_content, f.groww_specific, f.metadata
        FROM filtered_items f
    """
    if skip_already_extracted:
        query += " WHERE f.raw_id NOT IN (SELECT raw_id FROM structured_records)"

    query += """
        ORDER BY 
            CASE f.source
                WHEN 'reddit' THEN 1
                WHEN 'quora' THEN 2
                WHEN 'twitter' THEN 3
                WHEN 'youtube' THEN 4
                WHEN 'forum' THEN 5
                WHEN 'appstore' THEN 6
                WHEN 'playstore' THEN 7
                ELSE 8
            END,
            f.rowid ASC
    """
    if limit and limit > 0:
        query += f" LIMIT {limit}"

    cursor.execute(query)
    rows = cursor.fetchall()
    items: list[RawItem] = []

    for row in rows:
        platforms = json.loads(row["platform_mentioned"]) if row["platform_mentioned"] else []
        meta_dict = json.loads(row["metadata"]) if row["metadata"] else {}
        published_at = datetime.fromisoformat(row["published_at"]) if row["published_at"] else None

        item = RawItem(
            raw_id=row["raw_id"],
            source=SourceType(row["source"]),
            source_native_id=row["source_native_id"],
            source_url=row["source_url"],
            platform_mentioned=platforms,
            published_at=published_at,
            text=row["text_content"],
            metadata=RawItemMetadata(**meta_dict),
        )
        items.append(item)

    return items


def run_extraction_pipeline(
    db_path: Optional[str] = None,
    limit: Optional[int] = None,
    workers: int = 5,
    skip_already_extracted: bool = False,
    output_json: str = "data/structured_corpus.json",
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Orchestrate Stage 3 extraction across filtered items.
    """
    logger.info("Initializing database connection (db_path=%s)...", db_path or "default")
    conn = init_db(db_path)

    items = load_filtered_items_from_db(conn, limit=limit, skip_already_extracted=skip_already_extracted)
    total_items = len(items)
    logger.info("Loaded %d items for structured extraction.", total_items)

    if total_items == 0:
        print("\nNo items to extract. Either filtered_items table is empty or all items were already extracted.")
        conn.close()
        return {"total": 0, "extracted": 0}

    extractor = StructuredExtractor()
    t_start = time.perf_counter()

    # Progress tracker
    def on_progress(done: int, total: int, rec: StructuredRecord):
        pct = (done / total) * 100
        sys.stdout.write(f"\r[Extraction Progress] {done}/{total} ({pct:.1f}%) | Record ID: {rec.record_id[:8]}...")
        sys.stdout.flush()

    records, summary = extractor.extract_batch(items, max_workers=workers, on_progress=on_progress)
    print()  # newline after progress carriage return

    elapsed_time = round(time.perf_counter() - t_start, 2)
    successful_records = [r for r in records if r.extraction_status == ExtractionStatus.SUCCESS]
    success_rate = (len(successful_records) / total_items * 100) if total_items > 0 else 0.0

    metrics = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_items": total_items,
        "records_extracted": len(records),
        "successful_records": len(successful_records),
        "failed_records": total_items - len(successful_records),
        "success_rate_pct": round(success_rate, 2),
        "stats": extractor.stats,
        "elapsed_seconds": elapsed_time,
        "model_version": extractor.model_version,
        "prompt_version": extractor.prompt_version,
    }

    if not dry_run:
        logger.info("Writing %d structured records to database...", len(records))
        for r in records:
            conn.execute("DELETE FROM structured_records WHERE raw_id = ?", (r.raw_id,))
            insert_structured_record(conn, r)

        # Log to evidence log
        evidence_entry = EvidenceLogEntry(
            pipeline_stage="extraction",
            event_type="stage_completed",
            details=metrics,
        )
        insert_evidence_log_entry(conn, evidence_entry)

        # Export cumulative structured corpus JSON from database
        cur = conn.execute("SELECT * FROM structured_records ORDER BY extracted_at DESC")
        db_rows = cur.fetchall()
        all_json = []
        for row in db_rows:
            all_json.append({
                "record_id": row["record_id"],
                "raw_id": row["raw_id"],
                "groww_specific": bool(row["groww_specific"]),
                "lifecycle_stage": row["lifecycle_stage"],
                "behavior": json.loads(row["behavior"]) if row["behavior"] else [],
                "driver_to_start": row["driver_to_start"],
                "expectation": row["expectation"],
                "barrier_or_trigger_to_stop": row["barrier_or_trigger_to_stop"],
                "confusion_or_worry_in_app": row["confusion_or_worry_in_app"],
                "checking_behavior": row["checking_behavior"],
                "outside_app_behavior": row["outside_app_behavior"],
                "emotion": row["emotion"],
                "segment": json.loads(row["segment"]) if row["segment"] else {},
                "outcome": row["outcome"],
                "evidence_span": row["evidence_span"],
                "confidence": json.loads(row["confidence"]) if row["confidence"] else {},
                "extracted_at": row["extracted_at"],
                "extraction_status": row["extraction_status"],
                "model_version": row["model_version"],
                "prompt_version": row["prompt_version"],
            })

        out_path = Path(output_json)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(all_json, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.info("Saved structured JSON corpus (%d records) to %s", len(all_json), out_path)

        # Export cumulative structured CSV
        csv_path = Path("data/structured_records.csv")
        with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow([
                "record_id",
                "raw_id",
                "groww_specific",
                "lifecycle_stage",
                "emotion",
                "outcome",
                "barrier_or_trigger_to_stop",
                "confusion_or_worry_in_app",
                "checking_behavior",
                "outside_app_behavior",
                "driver_to_start",
                "expectation",
                "behaviors_json",
                "segment_json",
                "evidence_span",
                "extraction_status",
            ])
            for row in db_rows:
                writer.writerow([
                    row["record_id"],
                    row["raw_id"],
                    "Yes" if row["groww_specific"] else "No",
                    row["lifecycle_stage"],
                    row["emotion"],
                    row["outcome"],
                    row["barrier_or_trigger_to_stop"],
                    row["confusion_or_worry_in_app"],
                    row["checking_behavior"],
                    row["outside_app_behavior"],
                    row["driver_to_start"],
                    row["expectation"],
                    row["behavior"],
                    row["segment"],
                    row["evidence_span"],
                    row["extraction_status"],
                ])
        logger.info("Saved structured CSV (%d records) to %s", len(db_rows), csv_path)

    conn.close()
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Stage 3 LLM Structured Extraction.")
    parser.add_argument("--db-path", type=str, default=None, help="Path to SQLite database.")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of items to extract (e.g. for testing).")
    parser.add_argument("--workers", type=int, default=5, help="Concurrent worker threads (default 5).")
    parser.add_argument("--skip-extracted", action="store_true", help="Skip items already in structured_records.")
    parser.add_argument("--output-json", type=str, default="data/structured_corpus.json", help="Path to output JSON.")
    parser.add_argument("--dry-run", action="store_true", help="Run extraction without committing to database.")

    args = parser.parse_args()

    print("\n" + "=" * 60)
    print("SIP Discovery Engine — LLM Structured Extraction (Phase 3)")
    print("=" * 60)
    print(f"Limit: {args.limit or 'All items'}")
    print(f"Workers: {args.workers}")
    print(f"Skip already extracted: {args.skip_extracted}")
    print(f"Output JSON: {args.output_json}")
    print(f"Dry run: {args.dry_run}")
    print("-" * 60 + "\n")

    try:
        metrics = run_extraction_pipeline(
            db_path=args.db_path,
            limit=args.limit,
            workers=args.workers,
            skip_already_extracted=args.skip_extracted,
            output_json=args.output_json,
            dry_run=args.dry_run,
        )

        print("\n" + "=" * 60)
        print("Extraction Run Summary:")
        print(f"  Total items processed:     {metrics.get('total_items', 0)}")
        print(f"  Records extracted:         {metrics.get('records_extracted', 0)}")
        print(f"  Success on first attempt:  {metrics.get('stats', {}).get('success_first_attempt', 0)}")
        print(f"  Success after repair:      {metrics.get('stats', {}).get('success_after_repair', 0)}")
        print(f"  Validation failures:       {metrics.get('stats', {}).get('failed_validation', 0)}")
        print(f"  Overall success rate:      {metrics.get('success_rate_pct', 0.0)}%")
        print(f"  Low-confidence items:      {metrics.get('stats', {}).get('low_confidence_count', 0)}")
        print(f"  Total prompt tokens:       {metrics.get('stats', {}).get('total_prompt_tokens', 0):,}")
        print(f"  Total completion tokens:   {metrics.get('stats', {}).get('total_completion_tokens', 0):,}")
        print(f"  Elapsed time:              {metrics.get('elapsed_seconds', 0.0)}s")
        print("=" * 60 + "\n")

    except Exception as e:
        logger.exception("Extraction failed: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()

