"""
Unit tests for RelevanceClassifier (domain relevance heuristic & zero-shot LLM check).
"""

from unittest.mock import MagicMock

from src.models.schemas import RawItem, RawItemMetadata, SourceType
from src.preprocessing.relevance_classifier import RelevanceClassifier


def _make_item(item_id: str, text: str) -> RawItem:
    return RawItem(
        raw_id=item_id,
        source=SourceType.REDDIT,
        source_native_id=item_id,
        text=text,
        metadata=RawItemMetadata(),
    )


def test_relevance_classifier_heuristic_positive():
    classifier = RelevanceClassifier(use_llm=False)
    text = "Started my first SIP on Groww with ₹500 in Parag Parikh Flexi Cap. When does NAV get allotted?"
    is_rel, conf, reason = classifier.classify(text)
    assert is_rel is True
    assert conf >= 0.80
    assert "sip_keyword" in reason or "groww" in reason


def test_relevance_classifier_pure_trading_negative():
    classifier = RelevanceClassifier(use_llm=False)
    text = "Join for Nifty call option and put option intraday call jackpot tips!"
    is_rel, conf, reason = classifier.classify(text)
    assert is_rel is False
    assert conf >= 0.80


def test_relevance_classifier_with_mocked_llm():
    mock_client = MagicMock()
    mock_client.chat_completion.return_value = {
        "content": '{"relevant": true, "confidence": 0.88, "reason": "user discusses first-time financial doubts"}'
    }

    classifier = RelevanceClassifier(groq_client=mock_client, use_llm=True)
    # Text without explicit SIP keywords to trigger LLM path
    text = "I feel so anxious when my money goes into negative returns during my first year of saving."
    is_rel, conf, reason = classifier.classify(text)

    assert is_rel is True
    assert conf == 0.88
    assert "llm" in reason
    assert mock_client.chat_completion.called


def test_relevance_classifier_process_items():
    classifier = RelevanceClassifier(use_llm=False)
    items = [
        _make_item("1", "Should I stop my mutual fund SIP during market downturn?"),
        _make_item("2", "Best crypto trading futures and options bot"),
    ]
    retained, rejected = classifier.process_items(items)
    assert len(retained) == 1
    assert retained[0].raw_id == "1"
    assert len(rejected) == 1
    assert rejected[0]["raw_id"] == "2"

