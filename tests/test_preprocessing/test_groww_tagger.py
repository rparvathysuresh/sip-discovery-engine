"""
Unit tests for GrowwTagger (platform detection, Groww tagging, competitor-only filtering).
"""

from src.models.schemas import RawItem, RawItemMetadata, SourceType
from src.preprocessing.groww_tagger import GrowwTagger


def test_groww_appstore_playstore_tagged_groww_specific():
    tagger = GrowwTagger()
    item = RawItem(
        source=SourceType.PLAYSTORE,
        source_native_id="ps_1",
        text="App interface is clean but mandate failure is confusing.",
        metadata=RawItemMetadata(),
    )
    groww_spec, comp_only, platforms = tagger.tag_item(item)
    assert groww_spec is True
    assert comp_only is False
    assert "groww" in platforms


def test_groww_explicit_mention():
    tagger = GrowwTagger()
    item = RawItem(
        source=SourceType.REDDIT,
        source_native_id="rd_1",
        text="Why does Groww demat account lock mutual funds when switching folios?",
        metadata=RawItemMetadata(),
    )
    groww_spec, comp_only, platforms = tagger.tag_item(item)
    assert groww_spec is True
    assert comp_only is False
    assert "groww" in platforms


def test_general_platform_agnostic_sip():
    tagger = GrowwTagger()
    item = RawItem(
        source=SourceType.FORUM,
        source_native_id="f_1",
        text="Should I stop my monthly SIP in index funds when market crosses all-time high?",
        metadata=RawItemMetadata(),
    )
    groww_spec, comp_only, platforms = tagger.tag_item(item)
    assert groww_spec is False
    assert comp_only is False


def test_competitor_only_filtered():
    tagger = GrowwTagger()
    item = RawItem(
        source=SourceType.FORUM,
        source_native_id="f_comp",
        text="Zerodha support is not resolving my Coin portal login error on Kite app.",
        metadata=RawItemMetadata(),
    )
    groww_spec, comp_only, platforms = tagger.tag_item(item)
    assert groww_spec is False
    assert comp_only is True


def test_groww_tagger_process_items():
    tagger = GrowwTagger()
    items = [
        RawItem(source=SourceType.REDDIT, source_native_id="1", text="Groww SIP is easy", metadata=RawItemMetadata()),
        RawItem(source=SourceType.FORUM, source_native_id="2", text="Zerodha support kite app bug", metadata=RawItemMetadata()),
    ]
    retained, rejected = tagger.process_items(items)
    assert len(retained) == 1
    assert retained[0].metadata.extra["groww_specific"] is True
    assert len(rejected) == 1
    assert rejected[0]["reason"] == "competitor_only"

