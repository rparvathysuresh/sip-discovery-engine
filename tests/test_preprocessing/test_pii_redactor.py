"""
Unit tests for PIIRedactor (Indian PAN, phone numbers, email, bank account, and usernames).
"""

from src.models.schemas import RawItem, RawItemMetadata, SourceType
from src.preprocessing.pii_redactor import PIIRedactor


def test_pan_redaction():
    redactor = PIIRedactor()
    text = "My PAN number ABCDE1234F is not getting verified in Groww KYC portal."
    redacted, counts = redactor.redact(text)
    assert "[PAN]" in redacted
    assert "ABCDE1234F" not in redacted
    assert counts["pan"] == 1


def test_email_redaction():
    redactor = PIIRedactor()
    text = "Please send statement to rohan.investor99@gmail.com for my active SIPs."
    redacted, counts = redactor.redact(text)
    assert "[EMAIL]" in redacted
    assert "rohan.investor99@gmail.com" not in redacted
    assert counts["email"] == 1


def test_phone_number_redaction():
    redactor = PIIRedactor()
    text = "Call customer support at +91 9876543210 or 8765432109 to stop mandate debit."
    redacted, counts = redactor.redact(text)
    assert "[PHONE]" in redacted
    assert "9876543210" not in redacted
    assert "8765432109" not in redacted
    assert counts["phone"] == 2


def test_bank_account_redaction():
    redactor = PIIRedactor()
    text = "My SBI account number 1234567890123 has been debited twice for same SIP."
    redacted, counts = redactor.redact(text)
    assert "[ACCOUNT]" in redacted
    assert "1234567890123" not in redacted
    assert counts["account"] == 1


def test_financial_amounts_preserved():
    redactor = PIIRedactor()
    # Rupee values, percentages, and common SIP figures should NOT be masked
    text = "I invest ₹50,000 monthly, total corpus is ₹1.4L with 10% returns and Rs. 20000 in liquid fund."
    redacted, counts = redactor.redact(text)
    assert "₹50,000" in redacted
    assert "₹1.4L" in redacted
    assert "10%" in redacted
    assert "Rs. 20000" in redacted
    assert counts["account"] == 0


def test_username_hashing():
    redactor = PIIRedactor()
    text = "Thanks to u/GhostShadow410 and @RohanFin for advising to pause rather than cancel."
    redacted, counts = redactor.redact(text)
    assert "u/GhostShadow410" not in redacted
    assert "@RohanFin" not in redacted
    assert "[USER_" in redacted
    assert counts["user"] == 2


def test_pii_redactor_process_items():
    redactor = PIIRedactor()
    item = RawItem(
        source=SourceType.REDDIT,
        source_native_id="r1",
        text="Groww sent KYC error to me@example.com for PAN ABCDE1234F.",
        metadata=RawItemMetadata(),
    )
    processed = redactor.process_items([item])
    assert len(processed) == 1
    assert "[EMAIL]" in processed[0].text
    assert "[PAN]" in processed[0].text
    assert processed[0].metadata.extra["pii_redacted"]["email"] == 1
    assert processed[0].metadata.extra["pii_redacted"]["pan"] == 1

