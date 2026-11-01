"""
AI Evidence Log API route for the SIP Discovery Engine.

GET /api/v1/evidence-log — audit trail entries across all pipeline stages.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query

from src.api.routes.metadata import get_db

router = APIRouter(prefix="/api/v1", tags=["evidence-log"])


@router.get("/evidence-log")
def get_evidence_log(
    stage: Optional[str] = Query(None, description="Filter by pipeline stage (collection, preprocessing, extraction, analysis, synthesis)"),
    limit: int = Query(50, ge=1, le=200),
    conn: sqlite3.Connection = Depends(get_db),
) -> dict[str, Any]:
    """
    Retrieve audit trail entries from the AI Evidence Log.
    """
    where_clauses = ["1=1"]
    params: list[Any] = []

    if stage:
        where_clauses.append("pipeline_stage = ?")
        params.append(stage)

    where_sql = " AND ".join(where_clauses)
    sql = f"""
        SELECT log_id, pipeline_stage, event_type, details, logged_at
        FROM evidence_log
        WHERE {where_sql}
        ORDER BY logged_at DESC
        LIMIT ?
    """
    params.append(limit)

    cur = conn.execute(sql, params)
    rows = cur.fetchall()

    entries = []
    for r in rows:
        details_obj = json.loads(r["details"]) if r["details"] else {}
        entries.append({
            "log_id": r["log_id"],
            "pipeline_stage": r["pipeline_stage"],
            "event_type": r["event_type"],
            "details": details_obj,
            "logged_at": r["logged_at"],
        })

    return {
        "status": "success",
        "total": len(entries),
        "data": entries,
    }

