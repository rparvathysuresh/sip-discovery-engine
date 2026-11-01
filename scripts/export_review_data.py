#!/usr/bin/env python3
"""
scripts/export_review_data.py — Exports raw and filtered dataset to CSV, JSON, and Markdown formats.

Produces:
  - data/filtered_items.csv (tabular format for Excel / Google Sheets)
  - data/raw_items.csv (all collected items before filtering)
  - data/filtered_items.json (complete structured JSON)
  - data/raw_items.json (raw archive JSON)
  - data/review_corpus.md (formatted Markdown document for human review)
"""

from __future__ import annotations

import csv
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"


def export_data(db_path: Path = DATA_DIR / "sip_discovery.db") -> dict[str, Any]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 1. Fetch raw items
    cursor.execute(
        """
        SELECT raw_id, source, source_native_id, source_url, platform_mentioned,
               collected_at, published_at, text_content, language_detected, metadata
        FROM raw_items
        ORDER BY source, collected_at DESC
        """
    )
    raw_rows = [dict(r) for r in cursor.fetchall()]

    # 2. Fetch filtered items (Prioritize qualitative sources: Reddit, Quora, Twitter, YouTube)
    cursor.execute(
        """
        SELECT raw_id, source, source_native_id, source_url, platform_mentioned,
               published_at, text_content, groww_specific, processed_at, metadata
        FROM filtered_items
        ORDER BY 
            CASE source
                WHEN 'reddit' THEN 1
                WHEN 'quora' THEN 2
                WHEN 'twitter' THEN 3
                WHEN 'youtube' THEN 4
                WHEN 'forum' THEN 5
                WHEN 'appstore' THEN 6
                WHEN 'playstore' THEN 7
                ELSE 8
            END,
            groww_specific DESC
        """
    )
    filtered_rows = [dict(r) for r in cursor.fetchall()]
    conn.close()

    # --- Write raw_items.json & filtered_items.json ---
    raw_json_path = DATA_DIR / "raw_items.json"
    raw_json_path.write_text(json.dumps(raw_rows, indent=2, ensure_ascii=False), encoding="utf-8")

    filtered_json_path = DATA_DIR / "filtered_items.json"
    filtered_json_path.write_text(json.dumps(filtered_rows, indent=2, ensure_ascii=False), encoding="utf-8")

    # --- Write raw_items.csv ---
    raw_csv_path = DATA_DIR / "raw_items.csv"
    with open(raw_csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow([
            "raw_id",
            "source",
            "source_native_id",
            "platform_mentioned",
            "published_at",
            "source_url",
            "text_content",
        ])
        for r in raw_rows:
            writer.writerow([
                r["raw_id"],
                r["source"],
                r["source_native_id"],
                r["platform_mentioned"],
                r["published_at"] or "",
                r["source_url"] or "",
                r["text_content"],
            ])

    # --- Write filtered_items.csv ---
    filtered_csv_path = DATA_DIR / "filtered_items.csv"
    with open(filtered_csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow([
            "item_number",
            "source",
            "collection_type",
            "groww_specific",
            "source_native_id",
            "thread_title",
            "platform_mentioned",
            "published_at",
            "source_url",
            "text_content",
            "raw_id",
        ])
        for idx, r in enumerate(filtered_rows, 1):
            meta = json.loads(r["metadata"]) if r["metadata"] else {}
            title = meta.get("thread_title") or ""
            is_manual = (r["source_native_id"] or "").startswith("manual_raw_")
            coll_type = "Manual Curated" if is_manual else "Automated Live"
            writer.writerow([
                idx,
                r["source"],
                coll_type,
                "Yes" if r["groww_specific"] else "No",
                r["source_native_id"],
                title,
                r["platform_mentioned"],
                r["published_at"] or "",
                r["source_url"] or "",
                r["text_content"],
                r["raw_id"],
            ])

    # --- Write review_corpus.md ---
    md_path = DATA_DIR / "review_corpus.md"
    md_lines = [
        "# SIP Discovery Engine — Filtered Corpus Review",
        "",
        f"> **Total Retained Items:** {len(filtered_rows)}  ",
        f"> **Total Raw Collected Items:** {len(raw_rows)}  ",
        "> **Anonymization:** PII (PAN, emails, phones, accounts, handles) redacted.  ",
        "",
        "---",
        "",
    ]

    # Group by source using preferred qualitative priority order
    by_source: dict[str, list[dict]] = {}
    for r in filtered_rows:
        by_source.setdefault(r["source"], []).append(r)

    PREFERRED_SOURCE_ORDER = ["reddit", "quora", "twitter", "youtube", "forum", "appstore", "playstore"]
    # Include any sources not explicitly in the preferred list
    for s in by_source:
        if s not in PREFERRED_SOURCE_ORDER:
            PREFERRED_SOURCE_ORDER.append(s)

    item_num = 1
    for src in PREFERRED_SOURCE_ORDER:
        items = by_source.get(src, [])
        if not items:
            continue
        md_lines.append(f"## Source: `{src.upper()}` ({len(items)} items)\n")
        for it in items:
            meta = json.loads(it["metadata"]) if it["metadata"] else {}
            title = meta.get("thread_title") or "No title"
            groww_tag = "**Groww Specific:** Yes" if it["groww_specific"] else "**Groww Specific:** No (Platform-Agnostic)"
            platforms = it["platform_mentioned"] or "[]"
            date_str = it["published_at"] or "N/A"
            url = it["source_url"] or "#"

            md_lines.append(f"### {item_num}. {title}")
            md_lines.append(f"- **Source:** `{src}` | {groww_tag}")
            md_lines.append(f"- **Platforms Detected:** `{platforms}` | **Published:** {date_str}")
            md_lines.append(f"- **Source URL:** [{url}]({url})\n")
            md_lines.append("```text")
            md_lines.append(it["text_content"])
            md_lines.append("```\n")
            md_lines.append("---\n")
            item_num += 1

    md_path.write_text("\n".join(md_lines), encoding="utf-8")

    # --- Write dedicated curated_manual_reviews.csv and curated_manual_reviews.md ---
    manual_rows = [r for r in filtered_rows if (r["source_native_id"] or "").startswith("manual_raw_")]
    curated_csv_path = DATA_DIR / "curated_manual_reviews.csv"
    with open(curated_csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow([
            "item_number",
            "source",
            "groww_specific",
            "source_native_id",
            "source_url",
            "text_content",
        ])
        for r in manual_rows:
            writer.writerow([
                r["source_native_id"].replace("manual_raw_", "#"),
                r["source"],
                "Yes" if r["groww_specific"] else "No",
                r["source_native_id"],
                r["source_url"] or "",
                r["text_content"],
            ])

    curated_md_path = DATA_DIR / "curated_manual_reviews.md"
    curated_lines = [
        "# SIP Discovery Engine — Curated Online Reviews (300 Dataset)",
        "",
        f"> **Total Retained Curated Items:** {len(manual_rows)}  ",
        "> Curated multi-channel reviews from Reddit, Quora, Twitter/X, YouTube, Play Store, and App Store.",
        "",
        "---",
        "",
    ]
    for r in manual_rows:
        num = r["source_native_id"].replace("manual_raw_", "#")
        url = r["source_url"] or "#"
        curated_lines.append(f"### {num} ({r['source'].upper()})")
        curated_lines.append(f"- **Source:** `{r['source']}` | **Groww Specific:** {'Yes' if r['groww_specific'] else 'No'}")
        curated_lines.append(f"- **Source URL:** [{url}]({url})\n")
        curated_lines.append("```text")
        curated_lines.append(r["text_content"])
        curated_lines.append("```\n")
        curated_lines.append("---\n")
    curated_md_path.write_text("\n".join(curated_lines), encoding="utf-8")

    return {
        "raw_count": len(raw_rows),
        "filtered_count": len(filtered_rows),
        "manual_count": len(manual_rows),
        "files_generated": [
            str(filtered_csv_path),
            str(filtered_json_path),
            str(md_path),
            str(curated_csv_path),
            str(curated_md_path),
            str(raw_csv_path),
            str(raw_json_path),
        ],
    }


def main() -> None:
    print("Exporting database records for human review...")
    stats = export_data()
    print(f"\nSuccessfully exported {stats['filtered_count']} filtered items and {stats['raw_count']} raw items:")
    for f in stats["files_generated"]:
        print(f"  - {f}")


if __name__ == "__main__":
    main()

