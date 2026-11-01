"""
Opportunities API route for the SIP Discovery Engine.

GET /api/v1/opportunities — returns ranked opportunity areas with optional filters.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query

from src.api.routes.metadata import get_db

router = APIRouter(prefix="/api/v1", tags=["opportunities"])


@router.get("/opportunities")
def get_opportunities(
    category: Optional[str] = Query(None, description="Filter by category name"),
    evidence_level: Optional[str] = Query(None, description="Filter by evidence level (sufficient, directional, insufficient)"),
    min_score: Optional[float] = Query(None, description="Filter by minimum composite score"),
    limit: int = Query(50, ge=1, le=100),
    conn: sqlite3.Connection = Depends(get_db),
) -> dict[str, Any]:
    """
    Retrieve ranked opportunity areas with multi-dimensional breakdowns.
    """
    where_clauses = ["1=1"]
    params: list[Any] = []

    if category:
        where_clauses.append("LOWER(theme_category) LIKE ?")
        params.append(f"%{category.lower()}%")

    if evidence_level:
        where_clauses.append("LOWER(evidence_level) = ?")
        params.append(evidence_level.lower())

    if min_score is not None:
        where_clauses.append("composite_score >= ?")
        params.append(min_score)

    where_sql = " AND ".join(where_clauses)
    sql = f"""
        SELECT opportunity_id, theme_name, theme_category, frequency_count,
               frequency_share, severity_score, breadth_score, composite_score,
               segment_breakdown, lifecycle_breakdown, source_breakdown,
               sufficient_evidence, evidence_level, computed_at
        FROM opportunity_areas
        WHERE {where_sql}
        ORDER BY composite_score DESC, frequency_count DESC
        LIMIT ?
    """
    params.append(limit)

    cur = conn.execute(sql, params)
    rows = cur.fetchall()

    items = []
    for r in rows:
        items.append({
            "opportunity_id": r["opportunity_id"],
            "theme_name": r["theme_name"],
            "theme_category": r["theme_category"],
            "frequency_count": r["frequency_count"],
            "frequency_share": round(r["frequency_share"], 4),
            "severity_score": round(r["severity_score"], 4) if r["severity_score"] is not None else 0.0,
            "breadth_score": round(r["breadth_score"], 4),
            "composite_score": round(r["composite_score"], 4),
            "segment_breakdown": json.loads(r["segment_breakdown"]) if r["segment_breakdown"] else {},
            "lifecycle_breakdown": json.loads(r["lifecycle_breakdown"]) if r["lifecycle_breakdown"] else {},
            "source_breakdown": json.loads(r["source_breakdown"]) if r["source_breakdown"] else {},
            "sufficient_evidence": bool(r["sufficient_evidence"]),
            "evidence_level": r["evidence_level"],
            "computed_at": r["computed_at"],
        })

    return {
        "status": "success",
        "total": len(items),
        "data": items,
    }

