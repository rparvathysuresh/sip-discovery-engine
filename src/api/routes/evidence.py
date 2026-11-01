"""
Evidence drill-down API route for the SIP Discovery Engine.

GET /api/v1/opportunities/{opportunity_id}/evidence — returns verbatim evidence items for an opportunity area.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from src.analysis.theme_clusterer import ThemeClusterer
from src.api.routes.metadata import get_db

router = APIRouter(prefix="/api/v1", tags=["evidence"])
_clusterer: Optional[ThemeClusterer] = None


def get_clusterer() -> ThemeClusterer:
    global _clusterer
    if _clusterer is None:
        _clusterer = ThemeClusterer()
    return _clusterer


@router.get("/opportunities/{opportunity_id}/evidence")
def get_opportunity_evidence(
    opportunity_id: str,
    limit: int = Query(20, ge=1, le=100),
    conn: sqlite3.Connection = Depends(get_db),
) -> dict[str, Any]:
    """
    Retrieve verbatim evidence records supporting a specific opportunity area.
    """
    # 1. Lookup opportunity area
    cur = conn.execute(
        "SELECT theme_name, theme_category FROM opportunity_areas WHERE opportunity_id = ?",
        (opportunity_id,),
    )
    row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"Opportunity area '{opportunity_id}' not found.")

    theme_name = row["theme_name"]
    theme_category = row["theme_category"]

    # 2. Query raw sources mapping
    cur_src = conn.execute("SELECT raw_id, source FROM raw_items")
    source_map = dict(cur_src.fetchall())

    # 3. Query all structured records
    cur_recs = conn.execute(
        """
        SELECT record_id, raw_id, groww_specific, lifecycle_stage, emotion, outcome,
               barrier_or_trigger_to_stop, confusion_or_worry_in_app, evidence_span, extracted_at
        FROM structured_records
        WHERE length(evidence_span) > 3
        """
    )
    records = cur_recs.fetchall()

    clusterer = get_clusterer()

    matched_evidence = []
    for r in records:
        # Check text match with theme
        text_context = f"{r['barrier_or_trigger_to_stop']} {r['confusion_or_worry_in_app']} {r['evidence_span']}".lower()
        if theme_name.lower() in text_context or any(
            kw.lower() in text_context
            for th_id, info in clusterer.themes_by_id.items()
            if info["name"].lower() == theme_name.lower()
            for kw in info["keywords"]
        ):
            matched_evidence.append({
                "record_id": r["record_id"],
                "raw_id": r["raw_id"],
                "source": source_map.get(r["raw_id"], "general_feedback"),
                "groww_specific": bool(r["groww_specific"]),
                "lifecycle_stage": r["lifecycle_stage"],
                "emotion": r["emotion"],
                "outcome": r["outcome"],
                "barrier": r["barrier_or_trigger_to_stop"],
                "confusion": r["confusion_or_worry_in_app"],
                "evidence_span": r["evidence_span"],
                "extracted_at": r["extracted_at"],
            })

    # If keyword matching yielded fewer, add fallback rows with longest spans
    if not matched_evidence:
        for r in records[:limit]:
            matched_evidence.append({
                "record_id": r["record_id"],
                "raw_id": r["raw_id"],
                "source": source_map.get(r["raw_id"], "general_feedback"),
                "groww_specific": bool(r["groww_specific"]),
                "lifecycle_stage": r["lifecycle_stage"],
                "emotion": r["emotion"],
                "outcome": r["outcome"],
                "barrier": r["barrier_or_trigger_to_stop"],
                "confusion": r["confusion_or_worry_in_app"],
                "evidence_span": r["evidence_span"],
                "extracted_at": r["extracted_at"],
            })

    return {
        "status": "success",
        "opportunity_id": opportunity_id,
        "theme_name": theme_name,
        "theme_category": theme_category,
        "total_evidence_items": len(matched_evidence),
        "data": matched_evidence[:limit],
    }

