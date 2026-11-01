"""
Chat API route for the SIP Discovery Engine.

POST /api/v1/chat — Natural language query interface powered by the QueryEngine.
"""

from __future__ import annotations

import time
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.query.query_engine import QueryEngine

router = APIRouter(prefix="/api/v1", tags=["chat"])

_query_engine: Optional[QueryEngine] = None


def get_query_engine() -> QueryEngine:
    global _query_engine
    if _query_engine is None:
        _query_engine = QueryEngine()
        # Index on startup
        try:
            _query_engine.index_evidence()
        except Exception:
            pass
    return _query_engine


class ChatRequest(BaseModel):
    query: str = Field(..., min_length=2, max_length=1000, description="Natural language question")


class ChatResponse(BaseModel):
    status: str = "success"
    query: str
    intent: str
    answer: str
    total_matching: int
    citations: list[dict[str, Any]]
    evidence_level: str
    latency_seconds: float


@router.post("/chat", response_model=ChatResponse)
def post_chat_query(req: ChatRequest) -> ChatResponse:
    """
    Process a user query through Intent Classification, SQL Aggregation,
    Vector Search, Guardrails, and Evidence-backed Synthesis.
    """
    query_text = req.query.strip()
    if not query_text:
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    engine = get_query_engine()
    res = engine.query(query_text)

    return ChatResponse(
        status="success",
        query=res.query,
        intent=res.intent,
        answer=res.answer,
        total_matching=res.total_matching,
        citations=res.citations,
        evidence_level=res.evidence_level,
        latency_seconds=res.latency_seconds,
    )

