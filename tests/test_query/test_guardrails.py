"""
Unit tests for src/query/guardrails.py.
Verifies all compliance guardrail test cases specified in Phase 6.
"""

import pytest

from src.query.guardrails import GuardrailsChecker


@pytest.fixture
def guardrails():
    return GuardrailsChecker()


def test_refuse_investment_advice(guardrails):
    """Test 1: 'Which mutual fund should I invest in?' -> Polite refusal + redirect"""
    queries = [
        "Which mutual fund should I invest in?",
        "which fund to buy",
        "Can you recommend a fund for SIP?",
        "What is the best mutual fund for 2026?",
    ]
    for q in queries:
        is_refusal, msg, reason = guardrails.check_query_refusal(q)
        assert is_refusal is True, f"Query '{q}' should be refused"
        assert reason == "investment_advice"
        assert "not to recommend specific funds" in msg.lower()


def test_block_fomo_and_urgency(guardrails):
    """Test 2: 'Invest now or you'll miss out!' -> Blocked FOMO framing"""
    queries = [
        "Invest now or you'll miss out!",
        "Don't miss this opportunity to invest",
        "Is there a market crash incoming?",
        "Tell me a foolproof strategy for SIP",
    ]
    for q in queries:
        is_refusal, msg, reason = guardrails.check_query_refusal(q)
        assert is_refusal is True, f"Query '{q}' should trigger FOMO block"
        assert reason == "fomo_framing"
        assert "neutrality guardrails" in msg.lower()


def test_allow_legitimate_research_query(guardrails):
    """Test 3: 'What confuses investors about XIRR?' -> Normal response allowed"""
    queries = [
        "What confuses investors about XIRR?",
        "How many users stopped their SIP due to autopay failure?",
        "What are the top reasons for drop-off in month 0 to 1?",
    ]
    for q in queries:
        is_refusal, msg, reason = guardrails.check_query_refusal(q)
        assert is_refusal is False, f"Query '{q}' should NOT be refused"
        assert msg is None
        assert reason == "allowed"


def test_refuse_competitor_comparison(guardrails):
    """Test 4: 'Compare Groww vs Zerodha' -> Refusal competitor comparison"""
    queries = [
        "Compare Groww vs Zerodha",
        "groww vs coin",
        "which broker is better, groww or angelone?",
    ]
    for q in queries:
        is_refusal, msg, reason = guardrails.check_query_refusal(q)
        assert is_refusal is True, f"Query '{q}' should trigger competitor refusal"
        assert reason == "competitor_comparison"
        assert "head-to-head competitor" in msg.lower()


def test_sanitize_response(guardrails):
    """Verify response sanitization removes recommendations or FOMO phrases."""
    dirty_text = "You should invest now or you'll miss out on massive gains! Also you should invest in HDFC Top 100 fund."
    clean_text = guardrails.sanitize_response(dirty_text)
    assert "invest now or you'll miss out" not in clean_text.lower()
    assert "[neutral framing required]" in clean_text
    assert "[recommendation removed per compliance rules]" in clean_text

