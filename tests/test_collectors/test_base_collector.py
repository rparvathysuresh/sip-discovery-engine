"""
Tests for BaseCollector interface and detect_platforms utility (Phase 1.1).
"""

from typing import Optional
from unittest.mock import patch
import pytest

from src.collectors.base_collector import BaseCollector, detect_platforms
from src.models.schemas import RawItem, SourceType


class ConcreteDummyCollector(BaseCollector):
    """Minimal concrete subclass for testing BaseCollector."""

    def get_source_name(self) -> str:
        return "dummy_source"

    @property
    def source_type(self) -> SourceType:
        return SourceType.OTHER

    def collect_snapshot(self, limit: Optional[int] = None) -> list[RawItem]:
        return [
            RawItem(
                source=self.source_type,
                source_native_id="item_01",
                text="Test post discussing SIP on Groww.",
                platform_mentioned=["groww"],
            )
        ]


class IncompleteCollector(BaseCollector):
    """Subclass missing abstract methods."""
    pass


def test_base_collector_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        BaseCollector()  # type: ignore


def test_incomplete_subclass_cannot_be_instantiated():
    with pytest.raises(TypeError):
        IncompleteCollector()  # type: ignore


def test_concrete_subclass_inheritance():
    collector = ConcreteDummyCollector(config={"rate_limit": 10})
    assert collector.get_source_name() == "dummy_source"
    assert collector.source_type == SourceType.OTHER
    assert collector.config.get("rate_limit") == 10

    items = collector.collect_snapshot()
    assert len(items) == 1
    assert items[0].source == SourceType.OTHER
    assert items[0].source_native_id == "item_01"


@patch("time.sleep")
def test_respect_rate_limit(mock_sleep):
    collector = ConcreteDummyCollector()
    collector.respect_rate_limit(1.5)
    mock_sleep.assert_called_once_with(1.5)


def test_detect_platforms_groww():
    text = "Started my monthly mutual fund SIP in Groww app 3 months back."
    platforms = detect_platforms(text)
    assert "groww" in platforms
    assert len(platforms) == 1


def test_detect_platforms_multiple():
    text = "Comparing Groww vs Zerodha Coin for direct mutual funds."
    platforms = detect_platforms(text)
    assert "groww" in platforms
    assert "zerodha" in platforms


def test_detect_platforms_none():
    text = "Why do mutual fund SIPs give negative returns in early months?"
    platforms = detect_platforms(text)
    assert platforms == []


def test_detect_platforms_word_boundary_safety():
    # 'growing' should not trigger 'groww'
    text = "The mutual fund industry is growing rapidly in India."
    platforms = detect_platforms(text)
    assert "groww" not in platforms
    assert platforms == []

