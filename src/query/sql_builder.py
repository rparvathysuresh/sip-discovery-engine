"""
SQL Aggregation Query Builder for the SIP Discovery Engine.

Generates safe, parameterized SQLite aggregation queries from structured QueryIntent
and executes them against the structured_records table.
"""

from __future__ import annotations

import sqlite3
from typing import Any, Optional

from src.query.intent_classifier import IntentType, QueryIntent
from src.utils.logging import get_logger

logger = get_logger(__name__)


class SQLBuilder:
    """
    Constructs and executes parameterized SQL aggregation queries based on QueryIntent.
    """

    def __init__(self, conn: Optional[sqlite3.Connection] = None):
        self.conn = conn

    def build_and_execute(
        self, intent: QueryIntent, conn: Optional[sqlite3.Connection] = None
    ) -> dict[str, Any]:
        """
        Build and execute the appropriate SQL query for the given intent.

        Returns a dictionary containing:
            - total_matching: int
            - results: list[dict]
            - sql_query: str
            - parameters: list
        """
        c = conn or self.conn
        if c is None:
            raise ValueError("No active database connection provided to SQLBuilder.")

        if intent.intent_type == IntentType.COUNT:
            return self._execute_count_query(intent, c)
        elif intent.intent_type == IntentType.COMPARISON:
            return self._execute_comparison_query(intent, c)
        elif intent.intent_type == IntentType.DRILL_DOWN:
            return self._execute_drill_down_query(intent, c)
        else:
            return self._execute_general_aggregation(intent, c)

    def _execute_count_query(self, intent: QueryIntent, conn: sqlite3.Connection) -> dict[str, Any]:
        """Generate count aggregation with optional grouping."""
        where_clauses = ["1=1"]
        params: list[Any] = []

        if "groww_specific" in intent.filters:
            where_clauses.append("groww_specific = ?")
            params.append(1 if intent.filters["groww_specific"] else 0)

        if "outcome" in intent.filters:
            where_clauses.append("outcome = ?")
            params.append(intent.filters["outcome"])

        if "lifecycle_stage" in intent.filters:
            where_clauses.append("lifecycle_stage = ?")
            params.append(intent.filters["lifecycle_stage"])

        if intent.theme_focus:
            words = [w for w in intent.theme_focus.split("_") if len(w) > 3 and w not in {"rules", "friction", "failure"}]
            if not words:
                words = intent.theme_focus.split("_")[:1]
            word_conditions = []
            for w in words:
                word_conditions.append("(LOWER(barrier_or_trigger_to_stop) LIKE ? OR LOWER(confusion_or_worry_in_app) LIKE ? OR LOWER(evidence_span) LIKE ?)")
                kw_param = f"%{w}%"
                params.extend([kw_param, kw_param, kw_param])
            where_clauses.append(f"({' OR '.join(word_conditions)})")

        where_sql = " AND ".join(where_clauses)

        # Total matching
        count_sql = f"SELECT count(*) FROM structured_records WHERE {where_sql}"
        total = conn.execute(count_sql, params).fetchone()[0]

        # Breakdown by outcome
        breakdown_sql = f"""
            SELECT outcome, count(*) as count, round(count(*) * 100.0 / max(1, {total}), 1) as pct
            FROM structured_records
            WHERE {where_sql}
            GROUP BY outcome
            ORDER BY count DESC
        """
        cur = conn.execute(breakdown_sql, params)
        breakdown = [dict(r) for r in cur.fetchall()]

        return {
            "total_matching": total,
            "results": breakdown,
            "sql_query": breakdown_sql.strip(),
            "parameters": params,
        }

    def _execute_comparison_query(self, intent: QueryIntent, conn: sqlite3.Connection) -> dict[str, Any]:
        """Generate cross-tab comparison between outcomes (continued vs droppers)."""
        sql = """
            SELECT
                CASE
                    WHEN outcome = 'continued' THEN 'continuer'
                    WHEN outcome IN ('paused', 'reduced', 'stopped') THEN 'dropper'
                    ELSE 'unclear'
                END as outcome_group,
                emotion,
                count(*) as count
            FROM structured_records
            WHERE outcome != 'unclear'
            GROUP BY outcome_group, emotion
            ORDER BY outcome_group, count DESC
        """
        cur = conn.execute(sql)
        rows = [dict(r) for r in cur.fetchall()]

        # Total counts
        cur_tot = conn.execute(
            """
            SELECT
                SUM(CASE WHEN outcome = 'continued' THEN 1 ELSE 0 END) as continuers,
                SUM(CASE WHEN outcome IN ('paused', 'reduced', 'stopped') THEN 1 ELSE 0 END) as droppers
            FROM structured_records
            """
        )
        totals = dict(cur_tot.fetchone())

        return {
            "total_matching": (totals.get("continuers", 0) or 0) + (totals.get("droppers", 0) or 0),
            "group_totals": totals,
            "results": rows,
            "sql_query": sql.strip(),
            "parameters": [],
        }

    def _execute_drill_down_query(self, intent: QueryIntent, conn: sqlite3.Connection) -> dict[str, Any]:
        """Retrieve specific evidence spans matching the theme or filters."""
        where_clauses = ["length(evidence_span) > 5"]
        params: list[Any] = []

        if intent.theme_focus:
            words = [w for w in intent.theme_focus.split("_") if len(w) > 3 and w not in {"rules", "friction", "failure"}]
            if not words:
                words = intent.theme_focus.split("_")[:1]
            word_conditions = []
            for w in words:
                word_conditions.append("(LOWER(evidence_span) LIKE ? OR LOWER(barrier_or_trigger_to_stop) LIKE ? OR LOWER(confusion_or_worry_in_app) LIKE ?)")
                kw_param = f"%{w}%"
                params.extend([kw_param, kw_param, kw_param])
            where_clauses.append(f"({' OR '.join(word_conditions)})")

        where_sql = " AND ".join(where_clauses)
        sql = f"""
            SELECT record_id, raw_id, groww_specific, lifecycle_stage, emotion, outcome, evidence_span
            FROM structured_records
            WHERE {where_sql}
            ORDER BY length(evidence_span) DESC
            LIMIT 10
        """
        cur = conn.execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()]

        return {
            "total_matching": len(rows),
            "results": rows,
            "sql_query": sql.strip(),
            "parameters": params,
        }

    def _execute_general_aggregation(self, intent: QueryIntent, conn: sqlite3.Connection) -> dict[str, Any]:
        """General overview aggregation."""
        cur = conn.execute("SELECT count(*) FROM structured_records")
        total = cur.fetchone()[0]

        cur_outcomes = conn.execute(
            "SELECT outcome, count(*) as count FROM structured_records GROUP BY outcome ORDER BY count DESC"
        )
        outcomes = [dict(r) for r in cur_outcomes.fetchall()]

        cur_emotions = conn.execute(
            "SELECT emotion, count(*) as count FROM structured_records GROUP BY emotion ORDER BY count DESC"
        )
        emotions = [dict(r) for r in cur_emotions.fetchall()]

        return {
            "total_matching": total,
            "results": {"outcomes": outcomes, "emotions": emotions},
            "sql_query": "SELECT count(*) FROM structured_records",
            "parameters": [],
        }

