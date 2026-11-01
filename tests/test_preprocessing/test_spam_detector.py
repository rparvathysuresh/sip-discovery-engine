"""
Unit tests for SpamDetector (heuristic spam, promotional, repetition, and short text filter).
"""

from src.models.schemas import RawItem, RawItemMetadata, SourceType
from src.preprocessing.spam_detector import SpamDetector


def _make_item(item_id: str, text: str) -> RawItem:
    return RawItem(
        raw_id=item_id,
        source=SourceType.PLAYSTORE,
        source_native_id=item_id,
        text=text,
        metadata=RawItemMetadata(),
    )


def test_too_short_text():
    detector = SpamDetector(min_text_length=15)
    is_spam, reason = detector.check_spam("Good app")
    assert is_spam
    assert reason == "too_short"


def test_promotional_referral_spam():
    detector = SpamDetector()
    text = "Join our Telegram channel for 100% daily guaranteed returns and stock tips! Call now."
    is_spam, reason = detector.check_spam(text)
    assert is_spam
    assert reason == "promo_or_referral"

    text2 = "Use my referral code GROWW999 to get 100 rs free cash bonus on signup!"
    is_spam2, reason2 = detector.check_spam(text2)
    assert is_spam2
    assert reason2 == "promo_or_referral"


def test_character_repetition_spam():
    detector = SpamDetector()
    text = "This app is a big scaaaaaaaaam and frauddddddd, don't download!"
    is_spam, reason = detector.check_spam(text)
    assert is_spam
    assert reason == "excessive_character_repetition"


def test_legitimate_sip_review_passes():
    detector = SpamDetector()
    text = "My SIP of ₹2,000 in Parag Parikh Flexi Cap failed today because bank balance was low. Will Groww charge a penalty?"
    is_spam, reason = detector.check_spam(text)
    assert not is_spam
    assert reason is None


def test_spam_detector_process_items():
    detector = SpamDetector()
    items = [
        _make_item("1", "Nice"),
        _make_item("2", "Join my whatsapp group for intraday trading tips"),
        _make_item("3", "How do I pause my SIP for 3 months on Groww? Please guide."),
    ]
    retained, rejected = detector.process_items(items)
    assert len(retained) == 1
    assert retained[0].raw_id == "3"
    assert len(rejected) == 2

