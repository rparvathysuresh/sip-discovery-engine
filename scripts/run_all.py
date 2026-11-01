"""
End-to-End Pipeline Runner (Phase 8 - Task 8.5).
Executes the full pipeline sequentially:
Preprocessing -> Analysis -> Findings Generation -> Validation -> Guardrail Audit -> Dataset Export.
"""

import argparse
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PYTHON_EXE = sys.executable


def run_step(step_name: str, script_rel_path: str, args: list[str] = None):
    print("\n" + "=" * 70)
    print(f"   STAGE: {step_name.upper()}")
    print("=" * 70)
    cmd = [PYTHON_EXE, str(PROJECT_ROOT / script_rel_path)] + (args or [])
    t0 = time.perf_counter()
    res = subprocess.run(cmd, cwd=str(PROJECT_ROOT))
    elapsed = time.perf_counter() - t0
    if res.returncode != 0:
        print(f"\n[FAIL] Step '{step_name}' failed with exit code {res.returncode}")
        sys.exit(res.returncode)
    print(f"[OK] Step '{step_name}' completed in {elapsed:.2f}s")


def main():
    parser = argparse.ArgumentParser(description="SIP Discovery Engine End-to-End Pipeline")
    parser.add_argument("--with-collection", action="store_true", help="Include raw data collection step")
    parser.add_argument("--with-extraction", action="store_true", help="Include full Groq extraction step")
    args = parser.parse_args()

    print("=" * 70)
    print("   SIP DISCOVERY ENGINE — END-TO-END PIPELINE ORCHESTRATION")
    print(f"   Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    start_total = time.perf_counter()

    # 1. Collection (optional / snapshot)
    if args.with_collection:
        run_step("1. Raw Data Collection", "scripts/run_collection.py")
    else:
        print("\n[INFO] Skipping raw collection (using existing collected snapshot of 5,268 items)")

    # 2. Preprocessing & Filtering
    prep_args = [] if args.with_extraction else ["--no-llm"]
    run_step("2. Preprocessing & Filtering", "scripts/run_preprocessing.py", prep_args)

    # 3. Extraction (optional for live Groq API)
    if args.with_extraction:
        run_step("3. Groq LLM Structured Extraction", "scripts/run_extraction.py")
    else:
        print("\n[INFO] Skipping online LLM re-extraction (using validated structured records)")

    # 4. Opportunity Clustering & Scoring
    run_step("4. Theme Clustering & Opportunity Scoring", "scripts/run_analysis.py")

    # 5. Research Findings Generation
    run_step("5. Research Findings Synthesis", "scripts/generate_findings.py")

    # 6. Gold Sample Extraction Validation
    run_step("6. Gold Sample Benchmark Validation", "scripts/validate_gold_sample.py")

    # 7. SEBI Guardrail & Refusal Audit
    run_step("7. Guardrail & Policy Audit", "scripts/audit_guardrails.py")

    # 8. Dataset Export (CSV / JSON / Parquet / Schema)
    run_step("8. Dataset Export & Manifest Generation", "scripts/export_dataset.py")

    # 9. Performance Spot-Check
    run_step("9. Performance & Latency Spot-Check", "scripts/check_performance.py")

    total_time = time.perf_counter() - start_total
    print("\n" + "=" * 70)
    print("   END-TO-END PIPELINE COMPLETED SUCCESSFULLY!")
    print(f"   Total Pipeline Runtime: {total_time:.2f}s")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
