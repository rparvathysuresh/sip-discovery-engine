#!/usr/bin/env python3
"""
scripts/run_preprocessing.py — Orchestrates the Phase 2 Preprocessing & Filtering Pipeline.

Chains:
  1. Deduplication (exact + SimHash)
  2. Spam & quality filtering
  3. Privacy & PII redaction (PAN, phone, email, bank account, usernames)
  4. Relevance classification (SIP/MF domain focus)
  5. Platform & Groww tagging (competitor-only removal)

Persists retained corpus to SQLite `filtered_items` table and logs funnel metrics to `evidence_log`.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
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
    insert_filtered_item,
)
from src.models.schemas import EvidenceLogEntry, RawItem, RawItemMetadata, SourceType
from src.preprocessing.deduplicator import Deduplicator
from src.preprocessing.groww_tagger import GrowwTagger
from src.preprocessing.pii_redactor import PIIRedactor
from src.preprocessing.relevance_classifier import RelevanceClassifier
from src.preprocessing.spam_detector import SpamDetector
from src.utils.logging import get_logger

logger = get_logger("run_preprocessing")


def load_raw_items_from_db(conn: sqlite3.Connection) -> list[RawItem]:
    """Fetch all rows from raw_items table and construct RawItem objects."""
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT raw_id, source, source_native_id, source_url, platform_mentioned,
               collected_at, published_at, text_content, language_detected, metadata
        FROM raw_items
        ORDER BY 
            CASE source
                WHEN 'reddit' THEN 1
                WHEN 'quora' THEN 2
                WHEN 'twitter' THEN 3
                WHEN 'youtube' THEN 4
                WHEN 'forum' THEN 5
                WHEN 'appstore' THEN 6
                WHEN 'playstore' THEN 7
                ELSE 8
            END,
            collected_at DESC
        """
    )
    rows = cursor.fetchall()
    items: list[RawItem] = []

    for row in rows:
        platforms = json.loads(row["platform_mentioned"]) if row["platform_mentioned"] else []
        meta_dict = json.loads(row["metadata"]) if row["metadata"] else {}

        collected_at = datetime.fromisoformat(row["collected_at"])
        published_at = datetime.fromisoformat(row["published_at"]) if row["published_at"] else None

        item = RawItem(
            raw_id=row["raw_id"],
            source=SourceType(row["source"]),
            source_native_id=row["source_native_id"],
            source_url=row["source_url"],
            platform_mentioned=platforms,
            collected_at=collected_at,
            published_at=published_at,
            text=row["text_content"],
            language_detected=row["language_detected"],
            metadata=RawItemMetadata(**meta_dict),
        )
        items.append(item)

    return items


def run_preprocessing_pipeline(
    db_path: Optional[str] = None,
    output_file: Optional[str] = "data/filtered_corpus.json",
    use_llm: bool = True,
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Run the end-to-end preprocessing pipeline on raw items in SQLite.

    Returns:
        Funnel metrics dictionary.
    """
    logger.info("Initializing database...")
    conn = init_db(db_path)

    raw_items = load_raw_items_from_db(conn)
    total_collected = len(raw_items)
    logger.info("Loaded %d raw items from database for preprocessing.", total_collected)

    if total_collected == 0:
        logger.warning("No raw items found in database. Run 'python scripts/run_collection.py' first.")
        conn.close()
        return {"total_collected": 0, "corpus_retained": 0, "retention_rate_pct": 0.0}

    # Step 1: Deduplication
    logger.info("Running Step 1: Deduplication...")
    deduplicator = Deduplicator(simhash_threshold=3)
    dedup_retained, dedup_rejected = deduplicator.process_items(raw_items)
    duplicates_removed = len(dedup_rejected)
    logger.info("Step 1 complete: %d duplicates removed (%d retained)", duplicates_removed, len(dedup_retained))

    # Step 2: Spam Detection
    logger.info("Running Step 2: Spam Detection...")
    spam_detector = SpamDetector(min_text_length=30)
    spam_retained, spam_rejected = spam_detector.process_items(dedup_retained)
    spam_removed = len(spam_rejected)
    logger.info("Step 2 complete: %d spam items removed (%d retained)", spam_removed, len(spam_retained))

    # Step 3: PII Redaction
    logger.info("Running Step 3: PII Redaction...")
    pii_redactor = PIIRedactor()
    pii_redacted_items = pii_redactor.process_items(spam_retained)
    pii_redacted_count = sum(
        1
        for it in pii_redacted_items
        if it.metadata.extra and it.metadata.extra.get("pii_redacted")
    )
    logger.info("Step 3 complete: PII redacted on %d items", pii_redacted_count)

    # Step 4: Relevance Classification
    logger.info("Running Step 4: Relevance Classification (use_llm=%s)...", use_llm)
    classifier = RelevanceClassifier(use_llm=use_llm)
    rel_retained, rel_rejected = classifier.process_items(pii_redacted_items)
    irrelevant_removed = len(rel_rejected)
    logger.info("Step 4 complete: %d irrelevant items removed (%d retained)", irrelevant_removed, len(rel_retained))

    # Step 5: Groww & Platform Tagging (Competitor Filter)
    logger.info("Running Step 5: Groww & Competitor Tagging...")
    groww_tagger = GrowwTagger(exclude_competitor_only=True)
    final_retained, comp_rejected = groww_tagger.process_items(rel_retained)
    competitor_removed = len(comp_rejected)
    corpus_retained = len(final_retained)
    logger.info("Step 5 complete: %d competitor-only items removed (%d retained)", competitor_removed, corpus_retained)

    retention_rate = (corpus_retained / total_collected * 100) if total_collected > 0 else 0.0

    metrics = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_collected": total_collected,
        "duplicates_removed": duplicates_removed,
        "spam_removed": spam_removed,
        "pii_redacted_items": pii_redacted_count,
        "pii_stats": pii_redactor.stats,
        "irrelevant_removed": irrelevant_removed,
        "competitor_removed": competitor_removed,
        "corpus_retained": corpus_retained,
        "retention_rate_pct": round(retention_rate, 2),
        "groww_specific_count": sum(
            1 for it in final_retained if it.metadata.extra and it.metadata.extra.get("groww_specific")
        ),
        "platform_agnostic_count": sum(
            1 for it in final_retained if not (it.metadata.extra and it.metadata.extra.get("groww_specific"))
        ),
    }

    # Store into DB and export JSON
    if not dry_run:
        logger.info("Persisting %d retained items to filtered_items table (clearing previous filtered state)...", corpus_retained)
        conn.execute("DELETE FROM filtered_items")
        conn.commit()

        # Sort retained items by qualitative priority: Reddit, Quora, Twitter, YouTube first
        priority_map = {
            "reddit": 1,
            "quora": 2,
            "twitter": 3,
            "youtube": 4,
            "forum": 5,
            "appstore": 6,
            "playstore": 7,
        }
        sorted_retained = sorted(
            final_retained,
            key=lambda x: (
                priority_map.get(x.source.value if hasattr(x.source, "value") else str(x.source), 8),
                0 if (x.source_native_id or "").startswith("manual_raw_") else 1,
            )
        )

        for item in sorted_retained:
            groww_spec = bool(item.metadata.extra and item.metadata.extra.get("groww_specific"))
            insert_filtered_item(conn, item, groww_specific=groww_spec)

        # Record stage completion in AI Evidence Log
        evidence_entry = EvidenceLogEntry(
            pipeline_stage="preprocessing",
            event_type="stage_completed",
            details=metrics,
        )
        insert_evidence_log_entry(conn, evidence_entry)

        if output_file:
            out_path = Path(output_file)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            export_data = [item.model_dump(mode="json") for item in final_retained]
            out_path.write_text(json.dumps(export_data, indent=2, ensure_ascii=False), encoding="utf-8")
            logger.info("Saved filtered corpus to %s", out_path)

    conn.close()
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Phase 2 Preprocessing & Filtering Pipeline.")
    parser.add_argument("--db-path", type=str, default=None, help="Path to SQLite DB.")
    parser.add_argument("--output-file", type=str, default="data/filtered_corpus.json", help="Path for JSON export.")
    parser.add_argument("--no-llm", action="store_true", help="Disable LLM zero-shot and use heuristics only.")
    parser.add_argument("--dry-run", action="store_true", help="Process without saving to DB or disk.")

    args = parser.parse_args()

    print("\n" + "=" * 60)
    print("SIP Discovery Engine — Preprocessing Pipeline (Phase 2)")
    print("=" * 60)
    print(f"Output File: {args.output_file}")
    print(f"Use LLM: {not args.no_llm}")
    print(f"Dry Run: {args.dry_run}")
    print("-" * 60)

    try:
        metrics = run_preprocessing_pipeline(
            db_path=args.db_path,
            output_file=args.output_file,
            use_llm=not args.no_llm,
            dry_run=args.dry_run,
        )

        print("\nFiltering Funnel Metrics:")
        print(f"  1. Total Collected:       {metrics['total_collected']}")
        print(f"  2. Duplicates Removed:    -{metrics['duplicates_removed']}")
        print(f"  3. Spam Removed:          -{metrics['spam_removed']}")
        print(f"  4. PII Redacted Items:    {metrics['pii_redacted_items']}")
        print(f"  5. Irrelevant Removed:    -{metrics['irrelevant_removed']}")
        print(f"  6. Competitor Removed:    -{metrics['competitor_removed']}")
        print(f"  ------------------------------------")
        print(f"  Final Corpus Retained:    {metrics['corpus_retained']} ({metrics['retention_rate_pct']}%)")
        print(f"    - Groww Specific:       {metrics.get('groww_specific_count', 0)}")
        print(f"    - Platform Agnostic:    {metrics.get('platform_agnostic_count', 0)}")
        print("=" * 60 + "\n")

    except Exception as e:
        logger.exception("Fatal error during preprocessing pipeline: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()

