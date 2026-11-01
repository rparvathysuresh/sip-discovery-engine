"""
Semantic vector search engine for evidence spans using ChromaDB.

Embeds and indexes verbatim evidence spans extracted from structured records,
allowing semantic retrieval of quotes and citations for user queries.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import chromadb
from chromadb.config import Settings

from src.models.schemas import StructuredRecord
from src.utils.logging import get_logger

logger = get_logger(__name__)

DEFAULT_CHROMA_DIR = Path("data/chroma")
COLLECTION_NAME = "sip_evidence_spans"


class VectorSearch:
    """
    ChromaDB-backed semantic search engine for evidence spans.
    """

    def __init__(
        self,
        persist_dir: Optional[Path | str] = None,
        in_memory: bool = False,
        collection_name: Optional[str] = None,
    ):
        """
        Initialize ChromaDB client and evidence spans collection.
        """
        self.in_memory = in_memory
        coll_name = collection_name or COLLECTION_NAME
        if in_memory:
            self.client = chromadb.Client()
            try:
                self.client.delete_collection(name=coll_name)
            except Exception:
                pass
            logger.info("Initialized in-memory ChromaDB client")
        else:
            self.persist_dir = Path(persist_dir or DEFAULT_CHROMA_DIR)
            self.persist_dir.mkdir(parents=True, exist_ok=True)
            self.client = chromadb.PersistentClient(path=str(self.persist_dir))
            logger.info("Initialized persistent ChromaDB client at %s", self.persist_dir)

        self.collection = self.client.get_or_create_collection(
            name=coll_name,
            metadata={"hnsw:space": "cosine"},
        )

    def index_evidence_spans(self, records: list[StructuredRecord]) -> int:
        """
        Index evidence spans from a list of StructuredRecords.
        Skips empty spans or records without text.

        Returns:
            Number of indexed records.
        """
        valid_records = [r for r in records if r.evidence_span and len(r.evidence_span.strip()) > 3]
        if not valid_records:
            logger.info("No valid evidence spans to index.")
            return 0

        ids = [r.record_id for r in valid_records]
        documents = [r.evidence_span.strip() for r in valid_records]
        metadatas = [
            {
                "record_id": r.record_id,
                "raw_id": r.raw_id,
                "groww_specific": "true" if r.groww_specific else "false",
                "lifecycle_stage": r.lifecycle_stage.value if hasattr(r.lifecycle_stage, "value") else str(r.lifecycle_stage),
                "emotion": r.emotion.value if hasattr(r.emotion, "value") else str(r.emotion),
                "outcome": r.outcome.value if hasattr(r.outcome, "value") else str(r.outcome),
                "barrier": r.barrier_or_trigger_to_stop[:100] if r.barrier_or_trigger_to_stop else "unknown",
                "confusion": r.confusion_or_worry_in_app[:100] if r.confusion_or_worry_in_app else "unknown",
            }
            for r in valid_records
        ]

        # Upsert documents
        self.collection.upsert(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
        )
        count = len(valid_records)
        logger.info("Indexed %d evidence spans into ChromaDB collection '%s'", count, COLLECTION_NAME)
        return count

    def search(
        self,
        query: str,
        top_k: int = 5,
        where_filter: Optional[dict[str, Any]] = None,
    ) -> list[dict[str, Any]]:
        """
        Search for evidence spans semantically similar to the query.

        Args:
            query: User search text.
            top_k: Number of nearest evidence spans to retrieve.
            where_filter: Optional ChromaDB metadata filter.

        Returns:
            List of matching evidence dicts.
        """
        if self.count() == 0:
            return []

        limit = min(top_k, self.count())
        kwargs: dict[str, Any] = {
            "query_texts": [query],
            "n_results": limit,
        }
        if where_filter:
            kwargs["where"] = where_filter

        try:
            results = self.collection.query(**kwargs)
        except Exception as e:
            logger.warning("Vector search query failed: %s", e)
            return []

        retrieved: list[dict[str, Any]] = []
        if not results or not results["ids"] or not results["ids"][0]:
            return []

        ids = results["ids"][0]
        docs = results["documents"][0] if results["documents"] else [""] * len(ids)
        metas = results["metadatas"][0] if results["metadatas"] else [{}] * len(ids)
        dists = results["distances"][0] if results["distances"] else [0.0] * len(ids)

        for rec_id, doc, meta, dist in zip(ids, docs, metas, dists):
            # Cosine distance: similarity = 1 - distance
            similarity = round(max(0.0, 1.0 - dist), 3) if dist is not None else 1.0
            retrieved.append({
                "record_id": rec_id,
                "raw_id": meta.get("raw_id", ""),
                "evidence_span": doc,
                "similarity": similarity,
                "metadata": meta,
            })

        return retrieved

    def count(self) -> int:
        """Return total number of items in the vector collection."""
        return self.collection.count()

