"""
Core Query Engine for the SIP Discovery Engine.

Orchestrates:
Intent Classification -> SQL Aggregation -> Vector Search -> Synthesis -> Guardrails
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from src.db.connection import get_connection, init_db
from src.models.schemas import StructuredRecord
from src.query.guardrails import GuardrailsChecker
from src.query.intent_classifier import IntentClassifier, IntentType, QueryIntent
from src.query.sql_builder import SQLBuilder
from src.query.synthesizer import Synthesizer
from src.query.vector_search import VectorSearch
from src.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class QueryResponse:
    query: str
    intent: str
    answer: str
    total_matching: int
    citations: list[dict[str, Any]] = field(default_factory=list)
    evidence_level: str = "insufficient"
    latency_seconds: float = 0.0


class QueryEngine:
    """
    End-to-end query processing and synthesis engine.
    """

    def __init__(
        self,
        db_path: Optional[str] = None,
        vector_search: Optional[VectorSearch] = None,
        groq_client: Optional[Any] = None,
        in_memory_vector: bool = False,
    ):
        self.db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None
        self.guardrails = GuardrailsChecker()
        self.classifier = IntentClassifier(guardrails=self.guardrails)
        self.sql_builder = SQLBuilder()
        self.vector_search = vector_search or VectorSearch(in_memory=in_memory_vector)
        self.synthesizer = Synthesizer(groq_client=groq_client, guardrails=self.guardrails)

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = get_connection(self.db_path)
        return self._conn

    def index_evidence(self) -> int:
        """
        Ensure all structured records from SQLite DB are indexed in the vector store.
        """
        conn = self._get_conn()
        cur = conn.execute("SELECT * FROM structured_records")
        rows = cur.fetchall()
        records: list[StructuredRecord] = []

        for r in rows:
            rec = StructuredRecord(
                record_id=r["record_id"],
                raw_id=r["raw_id"],
                groww_specific=bool(r["groww_specific"]),
                lifecycle_stage=r["lifecycle_stage"],
                barrier_or_trigger_to_stop=r["barrier_or_trigger_to_stop"] or "",
                confusion_or_worry_in_app=r["confusion_or_worry_in_app"] or "",
                evidence_span=r["evidence_span"] or "",
            )
            records.append(rec)

        indexed = self.vector_search.index_evidence_spans(records)
        logger.info("QueryEngine indexed %d records into vector search.", indexed)
        return indexed

    def query(self, query_text: str) -> QueryResponse:
        """
        Execute full natural-language query pipeline.
        """
        t0 = time.perf_counter()
        conn = self._get_conn()

        # 1. Intent Classification (includes guardrail refusal check)
        intent = self.classifier.classify(query_text)

        if intent.intent_type == IntentType.REFUSAL:
            latency = round(time.perf_counter() - t0, 3)
            return QueryResponse(
                query=query_text,
                intent=intent.intent_type.value,
                answer=intent.refusal_message or self.guardrails.default_refusal_message,
                total_matching=0,
                citations=[],
                evidence_level="insufficient",
                latency_seconds=latency,
            )

        # 2. SQL Aggregation
        try:
            sql_data = self.sql_builder.build_and_execute(intent, conn)
        except Exception as e:
            logger.warning("SQLBuilder execution failed (%s), using empty fallback", e)
            sql_data = {"total_matching": 0, "results": []}

        # 3. Vector Semantic Search for Evidence Spans
        search_filter = None
        if "groww_specific" in intent.filters:
            search_filter = {"groww_specific": "true" if intent.filters["groww_specific"] else "false"}

        evidence_spans = self.vector_search.search(query_text, top_k=5, where_filter=search_filter)

        # Total corpus count
        try:
            cur = conn.execute("SELECT count(*) FROM structured_records")
            total_corpus = cur.fetchone()[0] or 1
        except Exception:
            total_corpus = 1

        total_matching = sql_data.get("total_matching", len(evidence_spans))

        # 4. Response Synthesis
        answer = self.synthesizer.synthesize(
            query=query_text,
            intent=intent,
            sql_data=sql_data,
            evidence_spans=evidence_spans,
            total_corpus_size=total_corpus,
        )

        evidence_level = self.guardrails.get_evidence_level(
            total_matching,
            len(set([e.get("metadata", {}).get("source", "app") for e in evidence_spans])) or 1,
        )

        latency = round(time.perf_counter() - t0, 3)

        return QueryResponse(
            query=query_text,
            intent=intent.intent_type.value,
            answer=answer,
            total_matching=total_matching,
            citations=evidence_spans,
            evidence_level=evidence_level,
            latency_seconds=latency,
        )

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

