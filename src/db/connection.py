"""
Database connection and schema initialization for the SIP Discovery Engine.

Uses SQLite with WAL mode for crash resilience. Provides:
- init_db(): Create all tables if they don't exist
- get_connection(): Get a database connection
- insert_raw_item(), insert_structured_record(), etc.
- Query helpers for common lookups
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.models.schemas import (
    EvidenceLogEntry,
    OpportunityArea,
    RawItem,
    StructuredRecord,
)
from src.utils.config import get_config


# ──────────────────────────────────────────────
# Schema Definitions
# ──────────────────────────────────────────────

RAW_ITEMS_SCHEMA = """
CREATE TABLE IF NOT EXISTS raw_items (
    raw_id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    source_native_id TEXT NOT NULL,
    source_url TEXT,
    platform_mentioned TEXT,
    collected_at TEXT NOT NULL,
    published_at TEXT,
    text_content TEXT NOT NULL,
    language_detected TEXT,
    metadata TEXT,
    UNIQUE(source, source_native_id)
);
"""

FILTERED_ITEMS_SCHEMA = """
CREATE TABLE IF NOT EXISTS filtered_items (
    raw_id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    source_native_id TEXT NOT NULL,
    source_url TEXT,
    platform_mentioned TEXT,
    published_at TEXT,
    text_content TEXT NOT NULL,
    groww_specific INTEGER NOT NULL,
    processed_at TEXT NOT NULL,
    metadata TEXT,
    FOREIGN KEY (raw_id) REFERENCES raw_items(raw_id)
);
"""

STRUCTURED_RECORDS_SCHEMA = """
CREATE TABLE IF NOT EXISTS structured_records (
    record_id TEXT PRIMARY KEY,
    raw_id TEXT NOT NULL,
    groww_specific INTEGER NOT NULL,
    lifecycle_stage TEXT DEFAULT 'unknown',
    behavior TEXT,
    driver_to_start TEXT DEFAULT 'unknown',
    expectation TEXT DEFAULT 'unknown',
    barrier_or_trigger_to_stop TEXT DEFAULT 'unknown',
    confusion_or_worry_in_app TEXT DEFAULT 'unknown',
    checking_behavior TEXT DEFAULT 'unknown',
    outside_app_behavior TEXT DEFAULT 'unknown',
    emotion TEXT DEFAULT 'unknown',
    segment TEXT,
    outcome TEXT DEFAULT 'unclear',
    evidence_span TEXT DEFAULT '',
    confidence TEXT,
    extracted_at TEXT NOT NULL,
    extraction_status TEXT DEFAULT 'success',
    model_version TEXT,
    prompt_version TEXT,
    FOREIGN KEY (raw_id) REFERENCES raw_items(raw_id)
);
"""

OPPORTUNITY_AREAS_SCHEMA = """
CREATE TABLE IF NOT EXISTS opportunity_areas (
    opportunity_id TEXT PRIMARY KEY,
    theme_name TEXT NOT NULL,
    theme_category TEXT NOT NULL,
    frequency_count INTEGER NOT NULL,
    frequency_share REAL NOT NULL,
    severity_score REAL,
    breadth_score REAL NOT NULL,
    composite_score REAL NOT NULL,
    segment_breakdown TEXT,
    lifecycle_breakdown TEXT,
    source_breakdown TEXT,
    sufficient_evidence INTEGER NOT NULL,
    evidence_level TEXT DEFAULT 'insufficient',
    computed_at TEXT NOT NULL
);
"""

EVIDENCE_LOG_SCHEMA = """
CREATE TABLE IF NOT EXISTS evidence_log (
    log_id TEXT PRIMARY KEY,
    pipeline_stage TEXT NOT NULL,
    event_type TEXT NOT NULL,
    details TEXT,
    logged_at TEXT NOT NULL
);
"""

ALL_SCHEMAS = [
    RAW_ITEMS_SCHEMA,
    FILTERED_ITEMS_SCHEMA,
    STRUCTURED_RECORDS_SCHEMA,
    OPPORTUNITY_AREAS_SCHEMA,
    EVIDENCE_LOG_SCHEMA,
]

EXPECTED_TABLES = ["raw_items", "filtered_items", "structured_records", "opportunity_areas", "evidence_log"]


# ──────────────────────────────────────────────
# Connection Management
# ──────────────────────────────────────────────

def get_db_path() -> str:
    """Get the database file path from config or environment."""
    config = get_config()
    db_path = config.get("database", {}).get("path", os.getenv("DATABASE_PATH", "data/sip_discovery.db"))
    return db_path


def get_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    """
    Get a SQLite connection with WAL mode enabled.
    
    Args:
        db_path: Optional override for the database file path.
                 If None, uses config/env.
    
    Returns:
        sqlite3.Connection configured with WAL mode and foreign keys.
    """
    if db_path is None:
        db_path = get_db_path()
    
    # Ensure the directory exists
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Optional[str] = None) -> sqlite3.Connection:
    """
    Initialize the database: create all tables if they don't exist.
    
    Args:
        db_path: Optional override for the database file path.
    
    Returns:
        sqlite3.Connection to the initialized database.
    """
    conn = get_connection(db_path)
    cursor = conn.cursor()
    
    for schema in ALL_SCHEMAS:
        cursor.execute(schema)
    
    conn.commit()
    return conn


def check_db_integrity(conn: sqlite3.Connection) -> bool:
    """
    Run PRAGMA integrity_check on the database.
    
    Returns:
        True if database passes integrity check.
    """
    result = conn.execute("PRAGMA integrity_check").fetchone()
    return result[0] == "ok"


def get_table_names(conn: sqlite3.Connection) -> list[str]:
    """Return a list of all table names in the database."""
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    return [row[0] for row in cursor.fetchall()]


# ──────────────────────────────────────────────
# Insert Operations
# ──────────────────────────────────────────────

def insert_raw_item(conn: sqlite3.Connection, item: RawItem) -> bool:
    """
    Insert a RawItem into the database. Skips duplicates (INSERT OR IGNORE).
    
    Returns:
        True if inserted, False if duplicate skipped.
    """
    try:
        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO raw_items
            (raw_id, source, source_native_id, source_url, platform_mentioned,
             collected_at, published_at, text_content, language_detected, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item.raw_id,
                item.source.value,
                item.source_native_id,
                item.source_url,
                json.dumps(item.platform_mentioned),
                item.collected_at.isoformat(),
                item.published_at.isoformat() if item.published_at else None,
                item.text,
                item.language_detected,
                item.metadata.model_dump_json(),
            ),
        )
        conn.commit()
        return cursor.rowcount > 0
    except sqlite3.Error:
        conn.rollback()
        raise


def insert_filtered_item(conn: sqlite3.Connection, item: RawItem, groww_specific: bool) -> None:
    """Insert a preprocessed and validated RawItem into the filtered_items table."""
    conn.execute(
        """
        INSERT OR REPLACE INTO filtered_items
        (raw_id, source, source_native_id, source_url, platform_mentioned,
         published_at, text_content, groww_specific, processed_at, metadata)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            item.raw_id,
            item.source.value,
            item.source_native_id,
            item.source_url,
            json.dumps(item.platform_mentioned),
            item.published_at.isoformat() if item.published_at else None,
            item.text,
            1 if groww_specific else 0,
            datetime.now().isoformat(),
            item.metadata.model_dump_json(),
        ),
    )
    conn.commit()


def count_filtered_items(conn: sqlite3.Connection) -> int:
    """Return total count of filtered items."""
    cursor = conn.execute("SELECT COUNT(*) FROM filtered_items")
    return cursor.fetchone()[0]


def insert_structured_record(conn: sqlite3.Connection, record: StructuredRecord) -> None:
    """Insert a StructuredRecord into the database."""
    conn.execute(
        """
        INSERT OR REPLACE INTO structured_records
        (record_id, raw_id, groww_specific, lifecycle_stage, behavior,
         driver_to_start, expectation, barrier_or_trigger_to_stop,
         confusion_or_worry_in_app, checking_behavior, outside_app_behavior,
         emotion, segment, outcome, evidence_span, confidence,
         extracted_at, extraction_status, model_version, prompt_version)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            record.record_id,
            record.raw_id,
            1 if record.groww_specific else 0,
            record.lifecycle_stage.value,
            json.dumps(record.behavior),
            record.driver_to_start,
            record.expectation,
            record.barrier_or_trigger_to_stop,
            record.confusion_or_worry_in_app,
            record.checking_behavior,
            record.outside_app_behavior,
            record.emotion.value,
            record.segment.model_dump_json(),
            record.outcome.value,
            record.evidence_span,
            record.confidence.model_dump_json(),
            record.extracted_at.isoformat(),
            record.extraction_status.value,
            record.model_version,
            record.prompt_version,
        ),
    )
    conn.commit()


def insert_opportunity_area(conn: sqlite3.Connection, area: OpportunityArea) -> None:
    """Insert an OpportunityArea into the database."""
    conn.execute(
        """
        INSERT OR REPLACE INTO opportunity_areas
        (opportunity_id, theme_name, theme_category, frequency_count,
         frequency_share, severity_score, breadth_score, composite_score,
         segment_breakdown, lifecycle_breakdown, source_breakdown,
         sufficient_evidence, evidence_level, computed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            area.opportunity_id,
            area.theme_name,
            area.theme_category,
            area.frequency_count,
            area.frequency_share,
            area.severity_score,
            area.breadth_score,
            area.composite_score,
            json.dumps(area.segment_breakdown),
            json.dumps(area.lifecycle_breakdown),
            json.dumps(area.source_breakdown),
            1 if area.sufficient_evidence else 0,
            area.evidence_level,
            area.computed_at.isoformat(),
        ),
    )
    conn.commit()


def insert_evidence_log_entry(conn: sqlite3.Connection, entry: EvidenceLogEntry) -> None:
    """Insert an EvidenceLogEntry into the database."""
    conn.execute(
        """
        INSERT INTO evidence_log
        (log_id, pipeline_stage, event_type, details, logged_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            entry.log_id,
            entry.pipeline_stage,
            entry.event_type,
            json.dumps(entry.details),
            entry.logged_at.isoformat(),
        ),
    )
    conn.commit()


# ──────────────────────────────────────────────
# Query Helpers
# ──────────────────────────────────────────────

def count_raw_items(conn: sqlite3.Connection) -> int:
    """Return the total number of raw items."""
    return conn.execute("SELECT COUNT(*) FROM raw_items").fetchone()[0]


def count_structured_records(conn: sqlite3.Connection) -> int:
    """Return the total number of structured records."""
    return conn.execute("SELECT COUNT(*) FROM structured_records").fetchone()[0]


def raw_item_exists(conn: sqlite3.Connection, source: str, source_native_id: str) -> bool:
    """Check if a raw item with the given source and native ID already exists."""
    row = conn.execute(
        "SELECT 1 FROM raw_items WHERE source = ? AND source_native_id = ?",
        (source, source_native_id),
    ).fetchone()
    return row is not None


def structured_record_exists(conn: sqlite3.Connection, raw_id: str) -> bool:
    """Check if a structured record already exists for a given raw_id."""
    row = conn.execute(
        "SELECT 1 FROM structured_records WHERE raw_id = ?",
        (raw_id,),
    ).fetchone()
    return row is not None


def get_corpus_stats(conn: sqlite3.Connection) -> dict:
    """
    Get corpus-level statistics for the data scope banner.
    
    Returns:
        Dict with total_items, sources, date_range, groww_specific_count, etc.
    """
    total = count_structured_records(conn)
    
    sources_rows = conn.execute(
        "SELECT DISTINCT source FROM raw_items"
    ).fetchall()
    sources = [row[0] for row in sources_rows]
    
    date_range = conn.execute(
        "SELECT MIN(published_at), MAX(published_at) FROM raw_items WHERE published_at IS NOT NULL"
    ).fetchone()
    
    groww_count = conn.execute(
        "SELECT COUNT(*) FROM structured_records WHERE groww_specific = 1"
    ).fetchone()[0]
    
    return {
        "total_items": total,
        "sources": sources,
        "date_range": {
            "start": date_range[0] if date_range else None,
            "end": date_range[1] if date_range else None,
        },
        "groww_specific_count": groww_count,
        "platform_agnostic_count": total - groww_count,
    }
