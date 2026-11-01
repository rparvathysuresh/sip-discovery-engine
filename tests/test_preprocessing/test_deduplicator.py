"""
Unit tests for Deduplicator (exact and near-duplicate SimHash detection).
"""

from src.models.schemas import RawItem, RawItemMetadata, SourceType
from src.preprocessing.deduplicator import Deduplicator


def _make_item(item_id: str, text: str) -> RawItem:
    return RawItem(
        raw_id=item_id,
        source=SourceType.REDDIT,
        source_native_id=item_id,
        text=text,
        metadata=RawItemMetadata(thread_title=text[:20]),
    )


def test_exact_duplicate_detection():
    dedup = Deduplicator()
    text = "Should I stop my monthly SIP in Nippon Small Cap due to market crash?"

    is_dup1, orig1, match1 = dedup.check_duplicate("item_1", text)
    assert not is_dup1
    assert orig1 is None

    # Exact same text with case and punctuation variation
    text_dup = "  should I stop my monthly sip in nippon small cap due to market crash?!!  "
    is_dup2, orig2, match2 = dedup.check_duplicate("item_2", text_dup)
    assert is_dup2
    assert orig2 == "item_1"
    assert match2 == "exact"


def test_near_duplicate_simhash():
    dedup = Deduplicator(simhash_threshold=4)
    original = "I had started a monthly SIP on Groww app for 5k, and now it is in negative trend with 4.7k loss."
    # Minor word variation (near duplicate)
    variant = "I had started a monthly SIP on Groww app for 5000, and now it is in negative trend with 4700 loss."

    is_dup1, _, _ = dedup.check_duplicate("item_orig", original)
    assert not is_dup1

    is_dup2, orig2, match2 = dedup.check_duplicate("item_var", variant)
    assert is_dup2
    assert orig2 == "item_orig"
    assert match2 == "near"


def test_distinct_items_not_flagged():
    dedup = Deduplicator()
    item1 = "How do I skip SIP for two months on Groww without paying penalty charges?"
    item2 = "Why is AMC rejecting my KYC verification when uploading bank statement?"

    is_dup1, _, _ = dedup.check_duplicate("i1", item1)
    is_dup2, _, _ = dedup.check_duplicate("i2", item2)

    assert not is_dup1
    assert not is_dup2
    assert dedup.stats["unique"] == 2


def test_deduplicator_process_items():
    dedup = Deduplicator()
    items = [
        _make_item("id_1", "Starting my first SIP of 1000 rupees in UTI Nifty 50 Index fund."),
        _make_item("id_2", "Starting my first SIP of 1000 rupees in UTI Nifty 50 Index fund."),
        _make_item("id_3", "Bank mandate failed on debit date, what should I do?"),
    ]

    retained, rejected = dedup.process_items(items)
    assert len(retained) == 2
    assert len(rejected) == 1
    assert rejected[0]["raw_id"] == "id_2"
    assert rejected[0]["reason"] == "duplicate_exact"

