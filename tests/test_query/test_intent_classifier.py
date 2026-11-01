"""
Unit tests for src/query/intent_classifier.py.
Verifies all 5 intent types: Count, Comparison, Drill-down, Exploration, Refusal.
"""

import pytest

from src.query.intent_classifier import IntentClassifier, IntentType


@pytest.fixture
def classifier():
    return IntentClassifier()


def test_classify_count_query(classifier):
    """Test count query classification."""
    intent = classifier.classify("How many investors mentioned autopay failure?")
    assert intent.intent_type == IntentType.COUNT
    assert intent.theme_focus == "autopay_mandate_failure"

    intent2 = classifier.classify("What percentage of users stopped SIP in month 0 to 1?")
    assert intent2.intent_type == IntentType.COUNT
    assert "outcome" in intent2.dimensions


def test_classify_comparison_query(classifier):
    """Test comparison query classification."""
    intent = classifier.classify("Compare continuers vs droppers on checking behavior")
    assert intent.intent_type == IntentType.COMPARISON
    assert "continuer_vs_dropper" in intent.dimensions

    intent2 = classifier.classify("Difference between salaried and freelance drop-off rates")
    assert intent2.intent_type == IntentType.COMPARISON


def test_classify_drill_down(classifier):
    """Test drill-down query classification."""
    intent = classifier.classify("Show me evidence for 'returns disappointment'")
    assert intent.intent_type == IntentType.DRILL_DOWN

    intent2 = classifier.classify("Quotes about kyc rejection in Groww")
    assert intent2.intent_type == IntentType.DRILL_DOWN
    assert intent2.theme_focus == "onboarding_kyc_friction"


def test_classify_exploration_query(classifier):
    """Test exploration query classification."""
    intent = classifier.classify("What worries first-time investors in months 2 to 3?")
    assert intent.intent_type == IntentType.EXPLORATION
    assert "lifecycle_stage" in intent.dimensions

    intent2 = classifier.classify("Why do people stop their mutual fund SIPs?")
    assert intent2.intent_type == IntentType.EXPLORATION


def test_classify_refusal(classifier):
    """Test refusal classification."""
    intent = classifier.classify("Which mutual fund should I invest in for high returns?")
    assert intent.intent_type == IntentType.REFUSAL
    assert intent.refusal_reason == "investment_advice"
    assert intent.refusal_message is not None

