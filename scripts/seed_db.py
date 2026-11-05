#!/usr/bin/env python3
"""
scripts/seed_db.py — Seeds SQLite database from tracked JSON data files.

Ensures zero-config startup on clean environments like Render, Docker,
or fresh git clones where data/sip_discovery.db was not committed.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.db.connection import get_connection, init_db, get_db_path
from src.utils.logging import get_logger

logger = get_logger("seed_db")


def seed_database(db_path: str | Path | None = None, force: bool = False) -> dict[str, int]:
    """
    Seed database from tracked JSON files in data/.
    Populates any unseeded or empty tables (raw_items, filtered_items,
    opportunity_areas, structured_records, evidence_log).
    """
    t0 = time.perf_counter()
    target_path = Path(db_path) if db_path else Path(get_db_path())
    target_path.parent.mkdir(parents=True, exist_ok=True)

    conn = init_db(str(target_path))

    data_dir = PROJECT_ROOT / "data"
    raw_path = data_dir / "raw_items.json"
    filt_path = data_dir / "filtered_items.json"
    opp_path = data_dir / "opportunity_areas.json"
    seed_struct_path = data_dir / "structured_records_seed.json"
    log_seed_path = data_dir / "evidence_log_seed.json"

    counts = {"raw": 0, "filtered": 0, "opportunities": 0, "structured": 0, "evidence_log": 0}

    # Inspect current table counts
    existing = {"raw": 0, "filtered": 0, "opportunities": 0, "structured": 0, "evidence_log": 0}
    try:
        existing["raw"] = conn.execute("SELECT count(*) FROM raw_items").fetchone()[0]
        existing["filtered"] = conn.execute("SELECT count(*) FROM filtered_items").fetchone()[0]
        existing["opportunities"] = conn.execute("SELECT count(*) FROM opportunity_areas").fetchone()[0]
        existing["structured"] = conn.execute("SELECT count(*) FROM structured_records").fetchone()[0]
        existing["evidence_log"] = conn.execute("SELECT count(*) FROM evidence_log").fetchone()[0]
    except Exception:
        pass

    # If everything is already fully seeded and not force, skip
    if (
        not force
        and existing["raw"] > 100
        and existing["filtered"] > 100
        and existing["opportunities"] >= 8
        and existing["structured"] >= 10
        and existing["evidence_log"] > 0
    ):
        logger.info(
            "Database %s already fully populated (raw: %d, filtered: %d, opp: %d, structured: %d, logs: %d). Skipping seed.",
            target_path, existing["raw"], existing["filtered"], existing["opportunities"], existing["structured"], existing["evidence_log"]
        )
        conn.close()
        return existing

    # 1. Raw items
    if (force or existing["raw"] < 100) and raw_path.is_file():
        raw_items = json.loads(raw_path.read_text(encoding="utf-8"))
        raw_rows = [
            (
                r.get("raw_id"),
                r.get("source"),
                r.get("source_native_id", ""),
                r.get("source_url", ""),
                json.dumps(r.get("platform_mentioned", [])),
                r.get("collected_at", ""),
                r.get("published_at"),
                r.get("text_content") or r.get("text", ""),
                r.get("language_detected", "en"),
                json.dumps(r.get("metadata", {})),
            )
            for r in raw_items
        ]
        conn.executemany(
            """
            INSERT OR REPLACE INTO raw_items (
                raw_id, source, source_native_id, source_url, platform_mentioned,
                collected_at, published_at, text_content, language_detected, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            raw_rows,
        )
        counts["raw"] = len(raw_rows)

    # 2. Filtered items
    if (force or existing["filtered"] < 100) and filt_path.is_file():
        filt_items = json.loads(filt_path.read_text(encoding="utf-8"))
        filt_rows = [
            (
                f.get("raw_id"),
                f.get("source"),
                f.get("source_native_id", ""),
                f.get("source_url", ""),
                json.dumps(f.get("platform_mentioned", [])),
                f.get("published_at"),
                f.get("text_content") or f.get("text", ""),
                1 if f.get("groww_specific") else 0,
                f.get("processed_at", ""),
                json.dumps(f.get("metadata", {})),
            )
            for f in filt_items
        ]
        conn.executemany(
            """
            INSERT OR REPLACE INTO filtered_items (
                raw_id, source, source_native_id, source_url, platform_mentioned,
                published_at, text_content, groww_specific, processed_at, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            filt_rows,
        )
        counts["filtered"] = len(filt_rows)

    # 3. Opportunity areas
    if (force or existing["opportunities"] < 8) and opp_path.is_file():
        opp_items = json.loads(opp_path.read_text(encoding="utf-8"))
        opp_rows = [
            (
                o.get("opportunity_id"),
                o.get("theme_name"),
                o.get("theme_category"),
                o.get("frequency_count"),
                o.get("frequency_share"),
                o.get("severity_score"),
                o.get("breadth_score"),
                o.get("composite_score"),
                json.dumps(o.get("segment_breakdown", {})),
                json.dumps(o.get("lifecycle_breakdown", {})),
                json.dumps(o.get("source_breakdown", {})),
                1 if o.get("sufficient_evidence") else 0,
                o.get("evidence_level", "insufficient"),
                o.get("computed_at", ""),
            )
            for o in opp_items
        ]
        conn.executemany(
            """
            INSERT OR REPLACE INTO opportunity_areas (
                opportunity_id, theme_name, theme_category, frequency_count,
                frequency_share, severity_score, breadth_score, composite_score,
                segment_breakdown, lifecycle_breakdown, source_breakdown,
                sufficient_evidence, evidence_level, computed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            opp_rows,
        )
        counts["opportunities"] = len(opp_rows)

    # 4. Structured seed records
    if (force or existing["structured"] < 10) and seed_struct_path.is_file():
        seed_records = json.loads(seed_struct_path.read_text(encoding="utf-8"))
        struct_rows = [
            (
                s.get("record_id"),
                s.get("raw_id"),
                1 if s.get("groww_specific") else 0,
                s.get("lifecycle_stage", "unknown"),
                s.get("behavior", "[]") if isinstance(s.get("behavior"), str) else json.dumps(s.get("behavior", [])),
                s.get("driver_to_start", "unknown"),
                s.get("expectation", "unknown"),
                s.get("barrier_or_trigger_to_stop", "unknown"),
                s.get("confusion_or_worry_in_app", "unknown"),
                s.get("checking_behavior", "unknown"),
                s.get("outside_app_behavior", "unknown"),
                s.get("emotion", "unknown"),
                s.get("segment", "{}") if isinstance(s.get("segment"), str) else json.dumps(s.get("segment", {})),
                s.get("outcome", "unclear"),
                s.get("evidence_span", ""),
                s.get("confidence", "{}") if isinstance(s.get("confidence"), str) else json.dumps(s.get("confidence", {})),
                s.get("extracted_at", ""),
                s.get("extraction_status", "success"),
                s.get("model_version", "openai/gpt-oss-120b"),
                s.get("prompt_version", "v1.0"),
            )
            for s in seed_records
        ]
        conn.executemany(
            """
            INSERT OR REPLACE INTO structured_records (
                record_id, raw_id, groww_specific, lifecycle_stage, behavior,
                driver_to_start, expectation, barrier_or_trigger_to_stop,
                confusion_or_worry_in_app, checking_behavior, outside_app_behavior,
                emotion, segment, outcome, evidence_span, confidence,
                extracted_at, extraction_status, model_version, prompt_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            struct_rows,
        )
        counts["structured"] = len(struct_rows)

    # 5. Evidence log audit entries
    if (force or existing["evidence_log"] == 0) and log_seed_path.is_file():
        log_items = json.loads(log_seed_path.read_text(encoding="utf-8"))
        log_rows = [
            (
                entry.get("log_id"),
                entry.get("pipeline_stage"),
                entry.get("event_type"),
                json.dumps(entry.get("details", {})) if isinstance(entry.get("details"), (dict, list)) else (entry.get("details") or "{}"),
                entry.get("logged_at", ""),
            )
            for entry in log_items
        ]
        conn.executemany(
            """
            INSERT OR REPLACE INTO evidence_log (
                log_id, pipeline_stage, event_type, details, logged_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            log_rows,
        )
        counts["evidence_log"] = len(log_rows)

    conn.commit()
    conn.close()

    elapsed = round(time.perf_counter() - t0, 3)
    logger.info(
        "Successfully seeded database (%s) in %.3fs: %d raw, %d filtered, %d opportunities, %d structured, %d evidence_log",
        target_path, elapsed, counts["raw"], counts["filtered"], counts["opportunities"], counts["structured"], counts["evidence_log"]
    )
    return counts


def seed_database_if_needed(db_path: str | Path | None = None) -> bool:
    """Helper for FastAPI lifespan to auto-seed when clean."""
    res = seed_database(db_path=db_path, force=False)
    return bool(res.get("raw", 0) > 0)


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed SIP Discovery Engine SQLite database.")
    parser.add_argument("--db-path", type=str, default=None, help="Target SQLite path.")
    parser.add_argument("--force", action="store_true", help="Force re-seeding even if tables exist.")
    args = parser.parse_args()

    seed_database(db_path=args.db_path, force=args.force)


if __name__ == "__main__":
    main()
