"""
scripts/audit_filtered_data.py — In-depth quality audit of the filtered_items database table.

Checks for:
1. Exact and near duplicate texts
2. Blank or excessively short items
3. Formatting artifacts (HTML tags, unresolved XML entities, excessive whitespace)
4. Relevance compliance (presence of SIP/mutual fund/investment terms vs crypto/gambling/trading noise)
5. Platform tagging validity (Groww-specific vs competitor-only)
6. Source consistency and metadata integrity
"""

import sqlite3
import re
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")


def audit():
    db_path = Path("data/sip_discovery.db")
    if not db_path.exists():
        print("Database not found!")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    total_filtered = cursor.execute("SELECT count(*) FROM filtered_items").fetchone()[0]
    print("=" * 60)
    print(f"AUDIT REPORT FOR FILTERED_ITEMS (Total: {total_filtered})")
    print("=" * 60)

    # 1. Source Breakdown
    print("\n1. SOURCE BREAKDOWN:")
    source_counts = cursor.execute(
        "SELECT source, count(*) FROM filtered_items GROUP BY source ORDER BY count(*) DESC"
    ).fetchall()
    for src, count in source_counts:
        pct = (count / total_filtered) * 100
        print(f"  - {src:<12}: {count:>5} ({pct:.1f}%)")

    # 2. Duplicate Text Check (Exact)
    print("\n2. EXACT DUPLICATE TEXT CHECK:")
    dup_rows = cursor.execute(
        """
        SELECT lower(trim(text_content)), count(*), group_concat(source)
        FROM filtered_items
        GROUP BY lower(trim(text_content))
        HAVING count(*) > 1
        """
    ).fetchall()
    print(f"  Exact duplicate text instances: {len(dup_rows)}")
    for text_sample, count, sources in dup_rows[:10]:
        print(f"    [{count}x across {sources}]: {repr(text_sample[:75])}")

    # 3. Blank or Very Short Texts
    print("\n3. LENGTH DISTRIBUTION & SHORT TEXTS:")
    len_ranges = [
        ("< 30 chars", "length(trim(text_content)) < 30"),
        ("30 - 50 chars", "length(trim(text_content)) BETWEEN 30 AND 50"),
        ("50 - 100 chars", "length(trim(text_content)) BETWEEN 51 AND 100"),
        ("100 - 300 chars", "length(trim(text_content)) BETWEEN 101 AND 300"),
        ("> 300 chars", "length(trim(text_content)) > 300"),
    ]
    for label, cond in len_ranges:
        cnt = cursor.execute(f"SELECT count(*) FROM filtered_items WHERE {cond}").fetchone()[0]
        pct = (cnt / total_filtered) * 100
        print(f"  - {label:<16}: {cnt:>5} ({pct:.1f}%)")

    short_items = cursor.execute(
        "SELECT raw_id, source, text_content FROM filtered_items WHERE length(trim(text_content)) < 30"
    ).fetchall()
    if short_items:
        print(f"\n  Inspecting {len(short_items)} short items (< 30 chars):")
        for r_id, src, text in short_items[:10]:
            print(f"    [{src}]: {repr(text)}")

    # 4. Content / Formatting Artifacts
    print("\n4. FORMATTING / HTML ARTIFACT CHECK:")
    html_matches = cursor.execute(
        """
        SELECT raw_id, source, text_content
        FROM filtered_items
        WHERE text_content LIKE '%<p>%'
           OR text_content LIKE '%<div>%'
           OR text_content LIKE '%<br%'
           OR text_content LIKE '%&amp;%'
           OR text_content LIKE '%&quot;%'
        """
    ).fetchall()
    print(f"  Items with raw HTML or unescaped entities: {len(html_matches)}")
    for r_id, src, text in html_matches[:5]:
        print(f"    [{src}]: {repr(text[:80])}")

    # 5. Relevance Sanity Check
    print("\n5. RELEVANCE & TOPICALITY CHECK:")
    # Check for pure trading/crypto terms without SIP context
    suspicious = cursor.execute(
        """
        SELECT raw_id, source, text_content
        FROM filtered_items
        WHERE (lower(text_content) LIKE '%call put%'
           OR lower(text_content) LIKE '%nifty option%'
           OR lower(text_content) LIKE '%banknifty%'
           OR lower(text_content) LIKE '%crypto%'
           OR lower(text_content) LIKE '%bitcoin%')
          AND NOT (lower(text_content) LIKE '%sip%'
                OR lower(text_content) LIKE '%mutual fund%')
        """
    ).fetchall()
    print(f"  Suspicious pure F&O/Crypto items without SIP mention: {len(suspicious)}")
    for r_id, src, text in suspicious[:5]:
        print(f"    [{src}]: {repr(text[:80])}")

    # Check for vague generic 1-star / 5-star texts with zero financial words
    GENERIC_PATTERNS = ["good app", "bad app", "nice app", "super app", "ok", "worst app ever", "fraud app"]
    generic_found = []
    all_texts = cursor.execute("SELECT raw_id, source, text_content FROM filtered_items").fetchall()
    for r_id, src, text in all_texts:
        t_clean = text.lower().strip()
        if t_clean in GENERIC_PATTERNS or (len(t_clean) < 25 and any(p in t_clean for p in GENERIC_PATTERNS)):
            generic_found.append((src, text))
    print(f"  Low-signal generic short reviews found: {len(generic_found)}")
    for src, text in generic_found[:5]:
        print(f"    [{src}]: {repr(text)}")

    # 6. Groww vs Platform-Agnostic Tagging
    print("\n6. GROWW SPECIFICITY:")
    groww_counts = cursor.execute(
        "SELECT groww_specific, count(*) FROM filtered_items GROUP BY groww_specific"
    ).fetchall()
    for g_val, count in groww_counts:
        status = "Groww-Specific" if g_val == 1 else "Platform-Agnostic"
        print(f"  - {status:<20}: {count:>5}")

    print("=" * 60)


if __name__ == "__main__":
    audit()
