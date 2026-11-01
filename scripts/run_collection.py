#!/usr/bin/env python3
"""
scripts/run_collection.py — Orchestrates data collectors across all sources.

Runs the active source collectors (Play Store, App Store, Reddit, YouTube, Forum),
inserts records into the raw_items database table, deduplicates by (source, source_native_id),
and logs execution metrics to the evidence_log table.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# Add project root to sys.path if invoked directly
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.collectors.appstore_collector import AppStoreCollector
from src.collectors.base_collector import BaseCollector
from src.collectors.forum_collector import ForumCollector
from src.collectors.playstore_collector import PlayStoreCollector
from src.collectors.reddit_collector import RedditCollector
from src.collectors.youtube_collector import YouTubeCollector
from src.collectors.quora_collector import QuoraCollector
from src.collectors.raw_data_collector import RawDataCollector
from src.db.connection import (
    count_raw_items,
    get_connection,
    init_db,
    insert_evidence_log_entry,
    insert_raw_item,
)
from src.models.schemas import EvidenceLogEntry, RawItem
from src.utils.config import get_source_config
from src.utils.logging import get_logger

logger = get_logger("run_collection")

# Registry of supported source collectors
COLLECTOR_REGISTRY: dict[str, type[BaseCollector]] = {
    "playstore": PlayStoreCollector,
    "appstore": AppStoreCollector,
    "reddit": RedditCollector,
    "youtube": YouTubeCollector,
    "forum": ForumCollector,
    "quora": QuoraCollector,
    "raw_data": RawDataCollector,
}


def run_collection(
    sources: Optional[list[str]] = None,
    limit_per_source: Optional[int] = None,
    db_path: Optional[str] = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Run data collection for specified sources and write results to the database.

    Args:
        sources: List of source names to collect ('playstore', 'appstore', 'reddit', 'youtube', 'forum').
                 Defaults to all registered sources.
        limit_per_source: Optional maximum items to collect per source.
        db_path: Optional override for SQLite database path.
        dry_run: If True, executes collection without committing to database.

    Returns:
        Dictionary containing summary statistics.
    """
    active_sources = sources or list(COLLECTOR_REGISTRY.keys())
    # Validate requested sources
    for src in active_sources:
        if src not in COLLECTOR_REGISTRY:
            raise ValueError(f"Unknown source '{src}'. Available: {list(COLLECTOR_REGISTRY.keys())}")

    logger.info("Initializing database (db_path=%s)...", db_path or "default")
    conn = init_db(db_path)

    stats: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_collected": 0,
        "total_inserted": 0,
        "total_duplicates_skipped": 0,
        "by_source": {},
        "dry_run": dry_run,
    }

    for source_name in active_sources:
        collector_cls = COLLECTOR_REGISTRY[source_name]
        source_cfg = get_source_config(source_name)
        collector = collector_cls(source_cfg)

        logger.info("Starting collection for source: %s", source_name)
        source_stat = {
            "collected": 0,
            "inserted": 0,
            "duplicates": 0,
            "error": None,
        }

        try:
            items: list[RawItem] = collector.collect_snapshot(limit=limit_per_source)
            source_stat["collected"] = len(items)

            if not dry_run:
                for item in items:
                    inserted = insert_raw_item(conn, item)
                    if inserted:
                        source_stat["inserted"] += 1
                    else:
                        source_stat["duplicates"] += 1
            else:
                source_stat["inserted"] = len(items)

            logger.info(
                "Source '%s' finished: collected=%d, inserted=%d, duplicates=%d",
                source_name,
                source_stat["collected"],
                source_stat["inserted"],
                source_stat["duplicates"],
            )

        except Exception as e:
            logger.error("Error during collection for source '%s': %s", source_name, e)
            source_stat["error"] = str(e)

        stats["total_collected"] += source_stat["collected"]
        stats["total_inserted"] += source_stat["inserted"]
        stats["total_duplicates_skipped"] += source_stat["duplicates"]
        stats["by_source"][source_name] = source_stat

    # Record stage completion in AI Evidence Log
    if not dry_run:
        evidence_entry = EvidenceLogEntry(
            pipeline_stage="collection",
            event_type="stage_completed",
            details={
                "total_collected": stats["total_collected"],
                "total_inserted": stats["total_inserted"],
                "total_duplicates_skipped": stats["total_duplicates_skipped"],
                "sources_run": active_sources,
                "by_source": stats["by_source"],
            },
        )
        insert_evidence_log_entry(conn, evidence_entry)
        stats["db_total_raw_items"] = count_raw_items(conn)
    else:
        stats["db_total_raw_items"] = None

    conn.close()
    return stats


def main() -> None:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(
        description="Run data collection across public channels for SIP Discovery Engine."
    )
    parser.add_argument(
        "--sources",
        type=str,
        default=None,
        help="Comma-separated sources to run (playstore,appstore,reddit,youtube,forum,quora,raw_data). Defaults to all.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of items to collect per source.",
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default=None,
        help="Custom path to SQLite database file.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run collection without saving items to the database.",
    )

    args = parser.parse_args()
    selected_sources = [s.strip() for s in args.sources.split(",")] if args.sources else None

    print("\n" + "=" * 60)
    print("SIP Discovery Engine — Data Collection Runner (Phase 1.8)")
    print("=" * 60)
    print(f"Sources: {selected_sources or list(COLLECTOR_REGISTRY.keys())}")
    print(f"Limit per source: {args.limit or 'Default configs'}")
    print(f"Dry run: {args.dry_run}")
    print("-" * 60)

    try:
        results = run_collection(
            sources=selected_sources,
            limit_per_source=args.limit,
            db_path=args.db_path,
            dry_run=args.dry_run,
        )

        print("\nCollection Summary:")
        print(f"  Total items collected: {results['total_collected']}")
        print(f"  Total items inserted:  {results['total_inserted']}")
        print(f"  Duplicates skipped:    {results['total_duplicates_skipped']}")
        if results.get("db_total_raw_items") is not None:
            print(f"  Total items in DB:     {results['db_total_raw_items']}")
        print("\nBreakdown by source:")
        for src, data in results["by_source"].items():
            err_str = f" [ERROR: {data['error']}]" if data["error"] else ""
            print(
                f"  - {src:<12}: collected={data['collected']:<4} inserted={data['inserted']:<4} duplicates={data['duplicates']:<4}{err_str}"
            )
        print("=" * 60 + "\n")

    except Exception as e:
        logger.exception("Fatal error running data collection: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()

