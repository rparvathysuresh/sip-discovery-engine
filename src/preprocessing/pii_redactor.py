"""
src/preprocessing/pii_redactor.py — Privacy preserving PII redaction.

Redacts Indian PAN cards, phone numbers (+91), email addresses, bank accounts,
and hashes usernames (u/username or @username) to protect investor privacy.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

from src.models.schemas import RawItem
from src.utils.logging import get_logger

logger = get_logger(__name__)

# Regular expressions for Indian PII patterns
PAN_REGEX = re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b")
EMAIL_REGEX = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
PHONE_REGEX = re.compile(r"(?:\+91[\s-]?)?[6-9]\d{9}\b")
# Bank account: 9 to 18 contiguous digits, excluding common timestamps/numbers or numbers preceded by currency
ACCOUNT_REGEX = re.compile(r"(?<![₹$€£\d])\b\d{9,18}\b(?!\d)")

# Reddit / Twitter user handles: u/username or @username
USER_HANDLE_REGEX = re.compile(r"(?:^|(?<=\s))(?:u/|@)([A-Za-z0-9_-]{3,25})\b")


def _hash_username(username: str) -> str:
    """Consistently hash a username to an anonymous identifier [USER_<short_hash>]."""
    short_hash = hashlib.sha256(username.lower().encode("utf-8")).hexdigest()[:6]
    return f"[USER_{short_hash}]"


class PIIRedactor:
    """
    Scans and redacts PII from text content while preserving financial context
    (e.g., SIP amounts, returns, fund names).
    """

    def __init__(self):
        self.stats = {
            "total_processed": 0,
            "pan_redacted": 0,
            "phone_redacted": 0,
            "email_redacted": 0,
            "account_redacted": 0,
            "user_redacted": 0,
        }

    def redact(self, text: str) -> tuple[str, dict[str, int]]:
        """
        Redact all detected PII entities from text.

        Returns:
            (redacted_text, counts_dict)
        """
        counts = {
            "pan": 0,
            "phone": 0,
            "email": 0,
            "account": 0,
            "user": 0,
        }
        self.stats["total_processed"] += 1

        # 1. Redact Indian PAN
        pan_matches = PAN_REGEX.findall(text)
        if pan_matches:
            counts["pan"] = len(pan_matches)
            self.stats["pan_redacted"] += len(pan_matches)
            text = PAN_REGEX.sub("[PAN]", text)

        # 2. Redact Email addresses
        email_matches = EMAIL_REGEX.findall(text)
        if email_matches:
            counts["email"] = len(email_matches)
            self.stats["email_redacted"] += len(email_matches)
            text = EMAIL_REGEX.sub("[EMAIL]", text)

        # 3. Redact Indian Phone Numbers (+91 or 10-digit mobile starting 6-9)
        phone_matches = PHONE_REGEX.findall(text)
        if phone_matches:
            counts["phone"] = len(phone_matches)
            self.stats["phone_redacted"] += len(phone_matches)
            text = PHONE_REGEX.sub("[PHONE]", text)

        # 4. Redact Bank Account Numbers (9-18 digits)
        account_matches = ACCOUNT_REGEX.findall(text)
        if account_matches:
            counts["account"] = len(account_matches)
            self.stats["account_redacted"] += len(account_matches)
            text = ACCOUNT_REGEX.sub("[ACCOUNT]", text)

        # 5. Hash usernames (u/username or @username)
        def _replace_user(m: re.Match) -> str:
            counts["user"] += 1
            self.stats["user_redacted"] += 1
            return _hash_username(m.group(1))

        text = USER_HANDLE_REGEX.sub(_replace_user, text)

        return text, counts

    def process_items(self, items: list[RawItem]) -> list[RawItem]:
        """
        Redact PII in-place across a list of RawItems, returning updated items.
        """
        redacted_items: list[RawItem] = []
        for item in items:
            clean_text, counts = self.redact(item.text)
            # Create updated RawItem with cleaned text
            item_dict = item.model_dump()
            item_dict["text"] = clean_text
            # Record PII redaction metadata
            if any(counts.values()):
                if not item_dict.get("metadata"):
                    item_dict["metadata"] = {}
                if "extra" not in item_dict["metadata"] or item_dict["metadata"]["extra"] is None:
                    item_dict["metadata"]["extra"] = {}
                item_dict["metadata"]["extra"]["pii_redacted"] = counts

            redacted_items.append(RawItem(**item_dict))

        return redacted_items
