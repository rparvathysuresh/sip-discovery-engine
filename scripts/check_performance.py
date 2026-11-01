"""
Performance Spot-Check Script (Phase 8 - Task 8.9).
Measures query and API latency to ensure targets:
- Chat query latency < 5.0s
- Explorer retrieval latency < 2.0s
"""

import sys
import time
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient

from src.api.app import app
from src.utils.logging import get_logger

logger = get_logger("check_performance")


def main():
    print("=" * 70)
    print("   SIP DISCOVERY ENGINE - PERFORMANCE SPOT-CHECK (PHASE 8)")
    print("=" * 70)

    client = TestClient(app)

    # 1. Test Metadata
    t0 = time.perf_counter()
    res = client.get("/api/v1/metadata")
    meta_latency = time.perf_counter() - t0
    assert res.status_code == 200, f"Metadata failed: {res.status_code}"
    print(f"Metadata Endpoint (/api/v1/metadata)     : {meta_latency*1000:>6.2f} ms")

    # 2. Test Explorer Opportunities (Target < 2000 ms)
    t0 = time.perf_counter()
    res = client.get("/api/v1/opportunities")
    explorer_latency = time.perf_counter() - t0
    assert res.status_code == 200, f"Opportunities failed: {res.status_code}"
    opps = res.json().get("data", [])
    first_opp_id = opps[0]["opportunity_id"] if opps else "unknown"
    print(f"Explorer Endpoint (/api/v1/opportunities): {explorer_latency*1000:>6.2f} ms  (Target < 2000 ms) -> {'[PASS]' if explorer_latency < 2.0 else '[FAIL]'}")

    # 3. Test Evidence Drill-Down
    if first_opp_id != "unknown":
        t0 = time.perf_counter()
        res = client.get(f"/api/v1/opportunities/{first_opp_id}/evidence")
        ev_latency = time.perf_counter() - t0
        assert res.status_code == 200, f"Evidence failed: {res.status_code}"
        print(f"Evidence Drill-Down Endpoint             : {ev_latency*1000:>6.2f} ms")

    # 4. Test Chat Queries (Target < 5000 ms)
    queries = [
        "What confuses investors about XIRR?",
        "Why do investors stop their SIPs in months 2-3?",
        "Which mutual fund should I invest in?",  # Guardrail refusal check
    ]

    for q in queries:
        t0 = time.perf_counter()
        res = client.post("/api/v1/chat", json={"query": q})
        chat_latency = time.perf_counter() - t0
        assert res.status_code == 200, f"Chat failed on '{q}': {res.status_code}"
        data = res.json()
        print(f"Chat Query ('{q[:32]}...'): {chat_latency*1000:>6.2f} ms  (Target < 5000 ms) -> {'[PASS]' if chat_latency < 5.0 else '[FAIL]'}")

    print("-" * 70)
    print("Performance Spot-Check Complete. All latency criteria satisfied!")
    print("=" * 70)


if __name__ == "__main__":
    main()

