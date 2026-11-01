# Context: SIP Retention Discovery Engine

> This document captures the full project context derived from the problem statement. It serves as a single-source reference for anyone working on the project.

---

## Overview

Build a discovery engine that identifies, quantifies and compares the reasons first-time mutual fund investors in India **pause, reduce, or let lapse** their SIP in the months after starting it, using **Groww** as the reference product context. The system draws exclusively from publicly available user conversations: App Store and Play Store reviews, Reddit (Indian investing communities), investing forums, YouTube comments on personal finance videos, social media and Q&A communities. It uses no internal Groww data.

The system must go beyond sentiment analysis and summarization. Every finding must be traceable to **structured, countable signals** (a behavior, a driver, a barrier, an emotion, a segment, a lifecycle stage), so that opportunity areas can be ranked and compared, not just described.

---

## Business Context

- **Role:** Product Manager on the Growth Team at Groww.
- **Core Insight:** Starting a SIP is easy — a few taps, a small monthly amount, a quiet promise to your future self. Staying with it is harder. Months pass, life gets busier, early statements look underwhelming, and the SIP that felt right in month one becomes something users stop thinking about, pause, or let lapse.
- **Strategic Goal:** Increase the percentage of first-time mutual fund investors who still have an active SIP 12 months after starting their first one.
- **Definition:** An *active SIP* means at least one successful instalment in the last 30 days.
- **Key Principle:** The underlying user problem is **not given**. The engine's job is to discover it from evidence before any solution is proposed.

---

## Objective

Design and implement a structured-extraction-based discovery engine that:

1. Collects a one-time snapshot of public conversations about SIPs and first-time investing in India
2. Extracts structured behavioral signals from each piece of feedback (not just sentiment or summary)
3. Quantifies and compares opportunity areas tied to SIP drop-off and retention
4. Answers open research questions with segment-aware, frequency-ranked evidence, not anecdote
5. Documents how insights were generated and validated (the **AI Evidence Log**)

---

## Scope of Work

### 1. Corpus Definition

- **Product scope:** Groww is the chosen product. The corpus consists of:
  - (a) Groww app reviews and conversations that mention Groww
  - (b) Platform-agnostic conversations about SIPs and first-time investing in India (e.g. "why did I stop my SIP", "SIP not giving returns") that describe investor behavior without being tied to another app
- **Tagging:** Every item carries a `groww_specific` tag (Groww-mentioned vs. platform-agnostic), and findings are reported with that split visible
- **Investor scope:** First-time or early-stage mutual fund investors; SIPs in the first 12 to 18 months of life
- **Target sources:**
  - App Store reviews
  - Play Store reviews
  - Reddit (e.g. r/IndiaInvestments, r/personalfinanceindia, r/IndianStreetBets, r/mutualfunds and similar)
  - Investing forums (e.g. TradingQnA, Value Research / Freefincal community threads)
  - YouTube comments on personal finance videos (SIP explainers, "SIP not working", market crash videos)
  - Social media conversations (public X/Twitter posts, where API terms allow)
  - Other public Q&A conversations about SIPs
- **Collection mode:** One-time snapshot (no recurring pipeline, scheduler, or orchestrator). Data is collected once, processed through the full pipeline, and served as a static corpus. Respects each source's API terms and rate limits during the collection run
- **Traceability:** Record for every item: source, date, platform mentioned, and a source-native ID or URL

### 2. Structured Extraction

Every collected item must be passed through an LLM-based extraction step (using **Groq** as the inference provider) that outputs a validated JSON record.

**Schema (extend as the data demands):**

| Field | Description |
|---|---|
| `lifecycle_stage` | pre-start, month 0–1, months 2–3, months 4–6, months 7–12, 12+, lapsed/restarted, unknown |
| `behavior` | e.g. checks returns frequently, pauses SIP, reduces amount, stops SIP, switches fund, redeems, increases amount, ignores app, seeks outside advice |
| `driver_to_start` | e.g. habit building, tax saving, peer/influencer, family advice, goal-based, FOMO-free curiosity, employer/salary trigger |
| `expectation` | what the user expected to happen (returns timeline, safety, liquidity) |
| `barrier_or_trigger_to_stop` | e.g. low/negative returns, market volatility, income disruption, expense spike, forgotten/hidden mandate, failed autopay, confusing statement, lack of visibility into progress, distrust, better alternative |
| `confusion_or_worry_in_app` | e.g. NAV vs returns, XIRR, folio/units, SIP date and failure, mandate setup, pause vs cancel, charges |
| `checking_behavior` | what they check and how often (daily NAV, portfolio value, XIRR, statements) |
| `outside_app_behavior` | what they do when unsure: Google, YouTube, Reddit, family/friends, advisor, other apps, spreadsheets |
| `emotion` | anxiety, regret, disappointment, confidence, indifference, anger |
| `segment` | income stability (stable, variable, student, none), age band, source of money (salary, parental, freelance, bonus), influencer (self, friend, family, finfluencer, platform) |
| `outcome` | continued, paused, reduced, stopped, unclear |
| `evidence_span` | short verbatim excerpt supporting the tags (kept under a small word limit) |
| `confidence` | extractor confidence per field, with `unknown` allowed |

**Rules:** Fields the text does not support must be `unknown`, never guessed. Duplicates, bots, promotional spam and off-topic items must be filtered and counted.

### 3. Discovery Engine — Core Research Questions

The system must answer, with quantified and segment-aware evidence:

1. Why do people start a SIP, and what do they expect to happen?
2. What changes in their behavior in the months after starting?
3. What leads investors to pause, reduce or stop a SIP?
4. What do investors check, and how often, once they have started?
5. What confuses or worries them inside the app?
6. What do they do outside the app when they feel unsure?
7. What separates investors who continue from those who quietly drop off?
8. How do these patterns differ across segments (income stability, age, source of money, who influenced them)?
9. What unmet needs emerge consistently across conversations?

**Requirements:**

- Each feedback item is tagged with structured fields rather than left as free text
- Each opportunity area is backed by a **count and share of corpus**, with a **severity score** (linked to how directly it precedes pause/stop outcomes), not only a qualitative label
- Opportunity areas are **ranked** by frequency and severity, and comparable across segments, lifecycle stages and sources
- Each answer can be traced back to the underlying source conversations
- Continuers vs. droppers are compared explicitly, so that retention drivers are surfaced alongside drop-off causes

### 4. Validation & AI Evidence Log

Maintain an **AI Evidence Log** recording:

- **Collection:** sources, queries/subreddits/videos used, date ranges, volumes collected vs. retained after filtering
- **Prompts & model versions** (Groq models) used for extraction, theme clustering and synthesis, with iterations
- **Theme discovery process** (e.g. open coding on a sample → codebook → full-corpus tagging)
- **Quality checks:** human-labeled gold sample (50–100 items) with per-field precision/agreement, inter-run consistency, spot checks of evidence spans against original text
- **Known failure cases** (sarcasm, Hinglish, code-mixed text, vague posts) and how they were handled
- **Error corrections:** cases where the AI was wrong or overreached and what was changed

---

## Refusal / Boundary Handling

The system must **not**:

- Recommend, name for recommendation, or compare specific mutual funds, stocks or AMCs as investment choices
- Generate guidance that uses **fear, FOMO or urgency-based** framing (e.g. "invest now or miss out", "market will crash")
- Fabricate or infer behavioral claims not grounded in collected source data
- Present a single anecdote or outlier as a general trend
- Attribute a finding to a segment or driver without sufficient supporting volume

**Evidence thresholds:** Headline findings require n ≥ 30 items and at least 2 independent sources. Otherwise the finding must be labeled "insufficient evidence" or "directional only." Questions asking for investment advice, return predictions or fund picks must be declined politely.

---

## User Interface (Minimal)

1. **Chat** — Ask ad hoc questions against the collected, tagged corpus. Answers cite counts and link to anonymized source items.
2. **Opportunity Explorer** — A browsable, ranked view of opportunity areas with frequency, severity, segment breakdown, lifecycle-stage breakdown and source mix. Filterable, not chat-only.
3. **Evidence Drill-Down** — From any opportunity area, open the supporting items (anonymized excerpts with source and date).
4. **Data Scope Banner** — Always visible, e.g. "Based on N public conversations from [sources], collected [date range], last updated [date]."

---

## Constraints

### Data & Sources
- Use only publicly available conversations and reviews; respect each source's terms of service and API rate limits
- Use official APIs (e.g. Reddit API, YouTube Data API) or compliant data vendors/public datasets — do not scrape sources whose terms disallow it
- No private, authenticated or platform-internal data

### Privacy & Security
- Do not collect, store or process PII (real names, contact details, account, folio, PAN, bank or order details) beyond what is inherent in public post metadata
- Hash or drop usernames; redact any PII that appears inside text
- Anonymize and aggregate findings before reporting; never surface individuals as identifiable examples

### Content Restrictions
- No fund, stock, or investment recommendations, and no product or nudge recommendations generated by the engine itself — it surfaces research findings, not actions
- Findings are presented as evidence-backed patterns, not certainties, unless supported by sufficient volume

### Transparency
- Every quantified finding shows its supporting count and source volume
- Source mix, date range and last-updated date are visible alongside any analysis
- Known biases must be surfaced in outputs:
  - Review-site skew toward complaints
  - Reddit skew toward urban/male/finance-literate users
  - Survivorship bias in lapsed users who stop posting

---

## Expected Deliverables

1. **README** — Setup instructions, sources and categories covered, architecture and workflow (collection → extraction → clustering → synthesis → UI), known limitations
2. **Extracted/Tagged Dataset** — Structured and queryable (e.g. SQLite/Parquet/CSV with schema documentation)
3. **Opportunity-Area Summary** — Answering the core research questions with quantified, segment-aware evidence, ranked by frequency and severity
4. **Research Findings Summary** (`research-findings-summary.md`) — Auto-generated document presenting all 9 research question answers, ranked opportunity areas, continuer-vs-dropper comparison, segment breakdowns, and source mix analysis with full counts and evidence levels
5. **AI Evidence Log** — (per section 4 above)
6. **Working Prototype** — Minimal UI (chat, opportunity explorer, scope banner)

---

## Success Criteria

- Structured, queryable dataset of tagged feedback across all target sources
- Each of the nine research questions answered with a quantified, segment-aware breakdown
- Opportunity areas ranked by frequency and severity, with clear links to the 12-month active-SIP metric
- Continuers vs. droppers meaningfully contrasted
- No finding presented without traceable supporting evidence; thin-evidence claims explicitly flagged
- AI Evidence Log shows measured extraction quality, not just assertions
- System demonstrably declines fund recommendations and fear/FOMO/urgency framing

---

## Summary

The goal is a trustworthy, evidence-grounded discovery engine that surfaces and ranks the real reasons first-time investors drift away from their SIPs. It prioritizes traceable, quantified findings over generic summarization, giving the Growth team a defensible basis for choosing where to intervene to raise 12-month SIP retention — without recommending funds or relying on fear, FOMO or urgency.
