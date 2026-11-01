# AI Evidence Log & Audit Trail

> **System:** SIP Retention Discovery Engine  
> **Repository:** `SIP Discovery Engine`  
> **Status:** Production Ready  

---

## Purpose

The AI Evidence Log provides a continuous, tamper-evident audit trail for every automated transformation in the behavioral discovery pipeline. It documents:

1. **Data Collection Provenance:** Source native IDs, collection timestamps, and query parameters.
2. **Preprocessing & Anonymization Audit:** Counts of deduplicated, spam-filtered, and PII-redacted records.
3. **LLM Extraction Traceability:** Exact model identifiers, prompt versions, JSON schema validation pass rates, and auto-repair iterations.
4. **Theme Clustering & Opportunity Scoring:** Mathematical score derivations ($0.4 \times \text{freq} + 0.4 \times \text{sev} + 0.2 \times \text{breadth}$), contingency tables, and Chi-square statistics.
5. **Guardrail Enforcements:** Pre- and post-generation policy checks preventing investment advice, competitor comparisons, and FOMO urgency framing.
6. **Gold Sample Validation:** Benchmark evaluation against 50 expert-annotated ground-truth records.
7. **Known Failure Cases:** Edge cases across Hinglish, sarcasm, ambiguity, and their architectural mitigations.

---

## Log Directory Structure

```
docs/ai-evidence-log/
├── README.md                           # This document — overview & audit standards
├── pipeline_metadata.md                # System metadata: models, prompts, source mix & volume
├── gold_sample_validation_report.md    # Empirical agreement metrics vs benchmark targets
└── failure_cases.md                    # 10 documented failure modes with verbatim examples & fixes
```

---

## Database Storage & API Access

All audit events are recorded in the SQLite database table `evidence_log`:

```sql
CREATE TABLE evidence_log (
    log_id TEXT PRIMARY KEY,
    pipeline_stage TEXT NOT NULL,
    event_type TEXT NOT NULL,
    details TEXT,
    logged_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

Audit entries are accessible programmatically via:
- REST API: `GET /api/v1/evidence-log?stage={stage}&limit=50`
- Web UI: Tab 3 (**AI Evidence Log**) in the dashboard.

