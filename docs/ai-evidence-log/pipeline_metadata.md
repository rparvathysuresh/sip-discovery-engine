# Pipeline Metadata & Model Configuration

> **Generated:** 2026-11-01  
> **Pipeline Version:** 1.0.0  
> **Observation Window:** September 2014 – November 2026  

---

## 1. Corpus Volume & Pipeline Funnel

| Stage | Input Items | Filtered / Transformed | Retained Items | Notes |
|---|---|---|---|---|
| **Raw Collection** | — | — | **5,268** | Across 7 channels (Play Store, App Store, Reddit, YouTube, Forums, Quora, Curated Manual) |
| **Exact Deduplication** | 5,268 | -1,088 | 4,180 | MD5 + SimHash exact/near-duplicate hashing |
| **Spam / Bot Removal** | 4,180 | -539 | 3,641 | Bot patterns, promotional spam, and short spam |
| **PII Redaction** | 3,641 | 10 redacted | 3,641 | Phone numbers, emails, folio IDs, and account numbers masked |
| **Relevance & Noise Filter** | 3,641 | -1,081 irrelevant, -7 competitor | **1,742** | High-precision SIP retention filter |
| **Groww Tagging** | 1,742 | 1,190 Groww / 552 Agnostic | **1,742** | 68.3% Groww-specific split |
| **Opportunity Clustering** | 1,742 | 20 sub-themes | **8 Opportunity Areas** | Scored by Frequency (0.4) + Severity (0.4) + Breadth (0.2) |

---

## 2. LLM Model & Inference Configuration

| Component | Primary Configuration | Fallback Configuration | Rationale |
|---|---|---|---|
| **Inference Provider** | Groq Cloud API | Local Deterministic Rules | Ultra-low latency, high token throughput |
| **Primary Model** | `openai/gpt-oss-120b` | `openai/gpt-oss-20b` | High reasoning capacity for nuanced Hinglish and implicit emotion |
| **Response Format** | `{"type": "json_object"}` | Strict regex JSON extraction | Enforces valid JSON payloads from LLM |
| **Temperature** | 0.1 | 0.0 | Near-deterministic structured extraction |
| **Max Tokens** | 2,048 | 1,024 | Accommodates multi-field extraction payload |

---

## 3. Active Prompt Versions

### `extraction_v1` (`src/extraction/prompts/extraction_v1.txt`)
- **Inputs:** Raw user conversation text, source platform, platform mentions.
- **Outputs:** Pydantic schema matching `StructuredRecord`:
  - `groww_specific`: bool
  - `lifecycle_stage`: enum (`pre_start`, `month_0_1`, `months_2_3`, `months_4_6`, `months_7_12`, `months_12_plus`, `lapsed_restarted`, `unknown`)
  - `behavior`: list of strings
  - `driver_to_start`: string
  - `expectation`: string
  - `barrier_or_trigger_to_stop`: string
  - `confusion_or_worry_in_app`: string
  - `checking_behavior`: string
  - `outside_app_behavior`: string
  - `emotion`: enum (`anxiety`, `anger`, `disappointment`, `confidence`, `neutral`, `confusion`, `frustration`)
  - `segment`: object (`income_stability`, `age_band`, `source_of_money`, `influencer`)
  - `outcome`: enum (`continued`, `paused`, `reduced`, `stopped`, `unknown`)
  - `evidence_span`: verbatim substring from source text

### `repair_prompt` (`src/extraction/prompts/repair_prompt.txt`)
- **Trigger:** Invoked when raw LLM response fails Pydantic schema validation or contains unescaped characters.
- **Behavior:** Feeds validation errors back to model for targeted 1-step repair.

---

## 4. Embedding & Vector Index Configuration

| Parameter | Value |
|---|---|
| **Vector Engine** | ChromaDB (Persistent Disk Backend: `data/chroma/`) |
| **Distance Metric** | Cosine Similarity (`hnsw:space: cosine`) |
| **Indexed Collection** | `sip_evidence_spans` |
| **Indexed Documents** | Verbatim `evidence_span` + `barrier_or_trigger_to_stop` + `confusion_or_worry_in_app` |
| **Metadata Tagging** | `record_id`, `raw_id`, `source`, `groww_specific`, `lifecycle_stage`, `outcome` |

---

## 5. SEBI Guardrails & Safety Policies

- **Prohibited:** Investment advice ("which fund to buy"), return predictions, subjective AMC rankings, competitor comparisons ("Groww vs Zerodha").
- **Prohibited:** FOMO urgency framing ("invest now or you'll miss out").
- **Required:** Evidence tier labels (`SUFFICIENT EVIDENCE`, `DIRECTIONAL EVIDENCE`, `INSUFFICIENT EVIDENCE`).
- **Enforcement Layers:** Dual-layer enforcement via `src/query/guardrails.py` (pre-query intent check) and `src/api/middleware/refusal_middleware.py` (HTTP response interceptor).

