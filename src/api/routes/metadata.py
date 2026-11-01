"""
Metadata API route for the SIP Discovery Engine.

GET /api/v1/metadata — returns data scope, corpus counts, date range, and known biases for the banner.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from fastapi import APIRouter, Depends, Request

from src.db.connection import get_connection

router = APIRouter(prefix="/api/v1", tags=["metadata"])


def get_db():
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()


@router.get("/metadata")
def get_metadata(conn: sqlite3.Connection = Depends(get_db)) -> dict[str, Any]:
    """
    Retrieve persistent data scope metrics for the UI banner.
    """
    # Counts
    cur = conn.execute("SELECT count(*) FROM filtered_items")
    filtered_count = cur.fetchone()[0]

    cur = conn.execute("SELECT count(*) FROM raw_items")
    raw_count = cur.fetchone()[0]

    cur = conn.execute("SELECT count(*) FROM structured_records")
    structured_count = cur.fetchone()[0]

    cur = conn.execute("SELECT count(*) FROM opportunity_areas")
    opp_count = cur.fetchone()[0]

    # Split
    cur = conn.execute("SELECT groww_specific, count(*) FROM filtered_items GROUP BY groww_specific")
    split = dict(cur.fetchall())
    groww_count = split.get(1, 0)
    agnostic_count = split.get(0, 0)

    # Sources
    cur = conn.execute("SELECT DISTINCT source FROM filtered_items ORDER BY source")
    sources = [r[0] for r in cur.fetchall()]

    # Dates
    cur = conn.execute("SELECT min(published_at), max(published_at) FROM filtered_items WHERE published_at IS NOT NULL")
    d_min, d_max = cur.fetchone()

    return {
        "status": "success",
        "data": {
            "total_filtered_items": filtered_count,
            "total_raw_collected": raw_count,
            "total_structured_records": structured_count,
            "total_opportunity_areas": opp_count,
            "groww_specific_count": groww_count,
            "platform_agnostic_count": agnostic_count,
            "groww_percentage": round((groww_count / max(1, filtered_count)) * 100, 1),
            "sources": sources,
            "date_range": {
                "start": (d_min[:10] if d_min else "2014-09-19"),
                "end": (d_max[:10] if d_max else "2026-11-01"),
            },
            "known_biases": [
                "Review-site skew toward complaints and transactional failures",
                "Reddit skew toward urban, male, and high-literacy investors",
                "Survivorship bias in lapsed investors who stop posting online",
            ],
        },
    }

