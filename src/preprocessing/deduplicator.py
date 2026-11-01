"""
src/preprocessing/deduplicator.py — Exact and near-duplicate detection.

Uses SHA-256 for exact duplicates and 64-bit SimHash with Hamming distance
for near-duplicate detection (e.g., cross-posted discussions, reposts, syndicated reviews).
"""

from __future__ import annotations

import hashlib
import re
from typing import Any, Optional

from src.models.schemas import RawItem
from src.utils.logging import get_logger

logger = get_logger(__name__)


def _normalize_text(text: str) -> str:
    """Normalize text by lowering, removing punctuation and extra whitespace."""
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    return " ".join(text.split())


def _compute_simhash(text: str) -> int:
    """
    Compute a 64-bit SimHash fingerprint for text using word shingles.
    """
    tokens = _normalize_text(text).split()
    if not tokens:
        return 0

    # Build word 3-grams if enough tokens, otherwise use unigrams + bigrams
    features: list[str] = []
    if len(tokens) >= 3:
        features = [" ".join(tokens[i : i + 3]) for i in range(len(tokens) - 2)]
    else:
        features = tokens

    v = [0] * 64
    for feature in features:
        # MD5 gives 128 bits, take first 64 bits
        h = int.from_bytes(hashlib.md5(feature.encode("utf-8")).digest()[:8], "big")
        for i in range(64):
            bit = (h >> i) & 1
            if bit == 1:
                v[i] += 1
            else:
                v[i] -= 1

    fingerprint = 0
    for i in range(64):
        if v[i] > 0:
            fingerprint |= 1 << i

    return fingerprint


def _hamming_distance(h1: int, h2: int) -> int:
    """Compute Hamming distance between two 64-bit integer hashes."""
    x = h1 ^ h2
    return bin(x).count("1")


def _jaccard_similarity(s1: set[str], s2: set[str]) -> float:
    """Compute Jaccard similarity between two token sets."""
    if not s1 or not s2:
        return 0.0
    return len(s1 & s2) / len(s1 | s2)


class Deduplicator:
    """
    Detects exact and near-duplicate text across collected records.
    """

    def __init__(self, simhash_threshold: int = 3, similarity_threshold: float = 0.70):
        """
        Args:
            simhash_threshold: Maximum Hamming distance for near-duplicates (default: 3).
            similarity_threshold: Minimum Jaccard token overlap for near-duplicates (default: 0.70).
        """
        self.simhash_threshold = simhash_threshold
        self.similarity_threshold = similarity_threshold
        # Maps exact normalized text hash -> original item_id
        self._exact_hashes: dict[str, str] = {}
        # Stores list of (simhash, tokens_set, item_id, text_length)
        self._entries: list[tuple[int, set[str], str, int]] = []
        self.stats = {
            "total_checked": 0,
            "exact_duplicates": 0,
            "near_duplicates": 0,
            "unique": 0,
        }

    def check_duplicate(self, item_id: str, text: str) -> tuple[bool, Optional[str], str]:
        """
        Check if an item is an exact or near duplicate of any previously seen item.

        Args:
            item_id: Unique ID of the candidate item.
            text: Text content of the candidate item.

        Returns:
            (is_duplicate, original_item_id, match_type)
            match_type is 'exact', 'near', or ''
        """
        self.stats["total_checked"] += 1
        normalized = _normalize_text(text)
        if not normalized:
            return False, None, ""

        # 1. Exact match check
        exact_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        if exact_hash in self._exact_hashes:
            self.stats["exact_duplicates"] += 1
            return True, self._exact_hashes[exact_hash], "exact"

        # 2. Near-duplicate check via SimHash and Jaccard token overlap
        words = normalized.split()
        if len(words) >= 4:
            sh = _compute_simhash(normalized)
            norm_len = len(normalized)
            tokens = set(words)

            for existing_sh, existing_tokens, existing_id, existing_len in self._entries:
                # Length filter: only compare items with similar length (within 35%)
                if abs(norm_len - existing_len) / max(norm_len, existing_len) > 0.35:
                    continue

                dist = _hamming_distance(sh, existing_sh)
                jaccard = _jaccard_similarity(tokens, existing_tokens)

                if dist <= self.simhash_threshold or jaccard >= self.similarity_threshold:
                    self.stats["near_duplicates"] += 1
                    return True, existing_id, "near"

            # Register entry
            self._entries.append((sh, tokens, item_id, norm_len))

        # Register exact hash
        self._exact_hashes[exact_hash] = item_id
        self.stats["unique"] += 1
        return False, None, ""

    def process_items(
        self, items: list[RawItem]
    ) -> tuple[list[RawItem], list[dict[str, Any]]]:
        """
        Filter a batch of RawItems, retaining only unique records.

        Returns:
            (retained_items, rejected_records)
        """
        retained: list[RawItem] = []
        rejected: list[dict[str, Any]] = []

        for item in items:
            is_dup, orig_id, match_type = self.check_duplicate(item.raw_id, item.text)
            if is_dup:
                rejected.append({
                    "raw_id": item.raw_id,
                    "reason": f"duplicate_{match_type}",
                    "original_id": orig_id,
                    "source": item.source.value,
                })
            else:
                retained.append(item)

        return retained, rejected

    def reset(self) -> None:
        """Clear all stored hashes and statistics."""
        self._exact_hashes.clear()
        self._entries.clear()
        self.stats = {
            "total_checked": 0,
            "exact_duplicates": 0,
            "near_duplicates": 0,
            "unique": 0,
        }
