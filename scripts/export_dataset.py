"""
Export Dataset Script (Phase 8 - Task 8.7).
Exports SQLite database tables into CSV, JSON, and Parquet formats
with complete schema documentation in data/exports/SCHEMA.md.
"""

import csv
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.db.connection import get_connection
from src.utils.logging import get_logger

logger = get_logger("export_dataset")

TABLES_TO_EXPORT = [
    "filtered_items",
    "structured_records",
    "opportunity_areas",
    "evidence_log",
]


def export_table_to_csv_and_json(conn: sqlite3.Connection, table_name: str, export_dir: Path) -> int:
    """Export a SQLite table to CSV and JSON formats."""
    cur = conn.execute(f"SELECT * FROM {table_name}")
    col_names = [description[0] for description in cur.description]
    rows = cur.fetchall()

    # 1. Export CSV
    csv_file = export_dir / f"{table_name}.csv"
    with open(csv_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(col_names)
        for r in rows:
            writer.writerow([r[c] for c in col_names])

    # 2. Export JSON
    json_file = export_dir / f"{table_name}.json"
    json_rows = []
    for r in rows:
        row_dict = {}
        for c in col_names:
            val = r[c]
            # Try parsing JSON strings for cleaner JSON output
            if isinstance(val, str) and (val.startswith("{") or val.startswith("[")):
                try:
                    row_dict[c] = json.loads(val)
                except Exception:
                    row_dict[c] = val
            else:
                row_dict[c] = val
        json_rows.append(row_dict)

    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(json_rows, f, indent=2)

    # 3. Optional Parquet export if pandas & pyarrow are installed
    try:
        import pandas as pd
        df = pd.DataFrame([dict(r) for r in rows])
        parquet_file = export_dir / f"{table_name}.parquet"
        df.to_parquet(parquet_file, index=False)
        logger.info(f"Exported {table_name} to Parquet ({len(rows)} rows)")
    except ImportError:
        pass

    logger.info(f"Exported {table_name}: {len(rows)} rows -> {csv_file.name}, {json_file.name}")
    return len(rows)


def generate_schema_documentation(export_dir: Path):
    """Generate comprehensive documentation for exported dataset tables."""
    schema_file = export_dir / "SCHEMA.md"
    content = [
        "# SIP Discovery Engine — Dataset Schema Documentation",
        "",
        f"> **Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  ",
        "> **Format Support:** CSV, JSON (and Parquet when pyarrow is installed)  ",
        "",
        "---",
        "",
        "## 1. `filtered_items` (Cleaned Behavioral Corpus)",
        "",
        "| Column | Type | Description |",
        "|---|---|---|",
        "| `raw_id` | UUID | Primary key from raw collection |",
        "| `source` | STRING | Platform source (`playstore`, `reddit`, `youtube`, `forum`, `quora`, `twitter`, `raw_dataset`) |",
        "| `source_native_id` | STRING | Source-specific post/comment/review ID |",
        "| `source_url` | STRING | Web URL to public conversation (if available) |",
        "| `platform_mentioned`| JSON ARRAY | Financial platforms explicitly mentioned (e.g. `['groww']`, `['zerodha']`) |",
        "| `groww_specific` | BOOLEAN | `1` if conversation specifically concerns Groww; `0` if platform-agnostic |",
        "| `published_at` | TIMESTAMP | Original publication date of user post |",
        "| `text_content` | TEXT | Cleaned, anonymized, and PII-redacted text content |",
        "| `filtered_at` | TIMESTAMP | Timestamp of filtering pipeline execution |",
        "",
        "## 2. `structured_records` (LLM-Extracted Behavioral Signals)",
        "",
        "| Column | Type | Description |",
        "|---|---|---|",
        "| `record_id` | UUID | Primary key for structured extraction |",
        "| `raw_id` | UUID | Foreign key referencing `filtered_items(raw_id)` |",
        "| `groww_specific` | BOOLEAN | Inherited platform specificity flag |",
        "| `lifecycle_stage` | ENUM | Stage: `pre_start`, `month_0_1`, `months_2_3`, `months_4_6`, `months_7_12`, `months_12_plus`, `lapsed_restarted`, `unknown` |",
        "| `behavior` | JSON ARRAY | Array of extracted behavior tags |",
        "| `driver_to_start` | STRING | Initial motivation or financial goal |",
        "| `expectation` | STRING | User expectation (returns, liquidity, automation) |",
        "| `barrier_or_trigger_to_stop` | STRING | Specific barrier or trigger leading toward pause/stop |",
        "| `confusion_or_worry_in_app` | STRING | In-app UX, metric, or navigation confusion |",
        "| `checking_behavior` | STRING | Frequency or style of checking investment portfolio |",
        "| `outside_app_behavior` | STRING | Discussions with peers, family, fin-influencers, or advisors |",
        "| `emotion` | ENUM | Dominant emotion: `anxiety`, `anger`, `disappointment`, `confidence`, `neutral`, `confusion`, `frustration` |",
        "| `segment` | JSON OBJECT | Demographic inference: `income_stability`, `age_band`, `source_of_money`, `influencer` |",
        "| `outcome` | ENUM | Retention outcome: `continued`, `paused`, `reduced`, `stopped`, `unknown` |",
        "| `evidence_span` | TEXT | Exact verbatim quote supporting the extracted signals |",
        "| `confidence` | JSON OBJECT | Extraction confidence score dictionary |",
        "| `extracted_at` | TIMESTAMP | Timestamp of LLM extraction |",
        "| `model_version` | STRING | Active LLM model (`openai/gpt-oss-120b`) |",
        "| `prompt_version` | STRING | Extraction prompt version (`extraction_v1`) |",
        "",
        "## 3. `opportunity_areas` (Ranked Behavioral Themes)",
        "",
        "| Column | Type | Description |",
        "|---|---|---|",
        "| `opportunity_id` | UUID | Primary key for opportunity area |",
        "| `theme_name` | STRING | Descriptive theme name |",
        "| `theme_category` | STRING | High-level category (e.g. `Mandate & Transaction Failure`) |",
        "| `frequency_count` | INTEGER | Total records matching this theme |",
        "| `frequency_share` | FLOAT | Normalized share of corpus ($N / \\text{Total}$) |",
        "| `severity_score` | FLOAT | Proportion of records where outcome in {`paused`, `reduced`, `stopped`} |",
        "| `breadth_score` | FLOAT | Cross-channel and cross-segment distribution score |",
        "| `composite_score` | FLOAT | Composite score: $0.4 \\times F + 0.4 \\times S + 0.2 \\times B$ |",
        "| `segment_breakdown` | JSON OBJECT | Cross-tabulation by demographic segment |",
        "| `lifecycle_breakdown` | JSON OBJECT | Cross-tabulation by tenure lifecycle stage |",
        "| `source_breakdown` | JSON OBJECT | Breakdown by data collection source |",
        "| `evidence_level` | ENUM | Evidence threshold: `sufficient`, `directional`, `insufficient` |",
        "| `sufficient_evidence` | BOOLEAN | True if record count >= 5 |",
        "| `computed_at` | TIMESTAMP | Timestamp of analysis calculation |",
        "",
        "## 4. `evidence_log` (Pipeline Audit Trail)",
        "",
        "| Column | Type | Description |",
        "|---|---|---|",
        "| `log_id` | UUID | Primary key for log event |",
        "| `pipeline_stage` | STRING | Stage: `collection`, `preprocessing`, `extraction`, `analysis`, `synthesis`, `validation` |",
        "| `event_type` | STRING | Event descriptor (e.g. `gold_sample_benchmarked`, `cluster_scored`) |",
        "| `details` | JSON OBJECT | Stage-specific metadata, counts, and parameters |",
        "| `logged_at` | TIMESTAMP | Timestamp of log event creation |",
        "",
        "---",
        "*SIP Retention Discovery Engine — Export Manifest*",
    ]

    schema_file.write_text("\n".join(content), encoding="utf-8")
    logger.info(f"Wrote schema documentation to {schema_file}")


def main():
    print("=" * 70)
    print("   SIP DISCOVERY ENGINE - DATASET EXPORT (PHASE 8 - TASK 8.7)")
    print("=" * 70)

    export_dir = PROJECT_ROOT / "data" / "exports"
    export_dir.mkdir(parents=True, exist_ok=True)

    conn = get_connection()
    total_exported = 0

    for table in TABLES_TO_EXPORT:
        count = export_table_to_csv_and_json(conn, table, export_dir)
        total_exported += count
        print(f"Exported {table:<22} -> {count:>6} rows")

    conn.close()

    generate_schema_documentation(export_dir)

    print("-" * 70)
    print(f"Export completed successfully. Total records exported across 4 tables: {total_exported}")
    print(f"Files saved in: {export_dir}")
    print("=" * 70)


if __name__ == "__main__":
    main()

