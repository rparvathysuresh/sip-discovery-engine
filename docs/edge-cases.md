# Edge Cases & Corner Scenarios: SIP Discovery Engine

> Comprehensive catalog of edge cases, corner scenarios, and failure modes across every pipeline stage. Each entry includes the scenario, expected behavior, handling strategy, and test approach.

---

## Table of Contents

1. [Data Collection Edge Cases](#1-data-collection-edge-cases)
2. [Preprocessing & Filtering Edge Cases](#2-preprocessing--filtering-edge-cases)
3. [LLM Structured Extraction Edge Cases](#3-llm-structured-extraction-edge-cases)
4. [Theme Clustering & Scoring Edge Cases](#4-theme-clustering--scoring-edge-cases)
5. [Query Engine & Chat Edge Cases](#5-query-engine--chat-edge-cases)
6. [Guardrail & Refusal Edge Cases](#6-guardrail--refusal-edge-cases)
7. [UI & Presentation Edge Cases](#7-ui--presentation-edge-cases)
8. [Infrastructure & System Edge Cases](#8-infrastructure--system-edge-cases)

---

## 1. Data Collection Edge Cases

### 1.1 — Empty or Zero-Result API Response

| Attribute | Detail |
|---|---|
| **Scenario** | A source API returns zero results for a search query (e.g., no Reddit posts match "SIP stopped" in a subreddit) |
| **Risk** | Pipeline proceeds with an incomplete corpus without warning |
| **Handling** | Log a warning with the query and source; continue with other queries. In the AI Evidence Log, record `items_collected = 0` for that query. Do not treat as a fatal error. |
| **Test** | Mock API returning `[]`; verify warning logged and pipeline continues |

### 1.2 — API Rate Limit Exceeded Mid-Collection

| Attribute | Detail |
|---|---|
| **Scenario** | Reddit/YouTube/Groq API returns HTTP 429 (Too Many Requests) partway through collection |
| **Risk** | Partial collection — some items fetched, others missed |
| **Handling** | Implement exponential backoff (initial: 1s, max: 60s, 5 retries). If still failing after retries, save what was collected, log the cutoff point, and surface a warning: "Collection incomplete for [source] — collected N of estimated M items." |
| **Test** | Mock 429 responses; verify backoff timing and partial save |

### 1.3 — API Key Invalid or Expired

| Attribute | Detail |
|---|---|
| **Scenario** | Reddit OAuth token expired, YouTube API key revoked, Groq API key invalid |
| **Risk** | Silent failure or crash |
| **Handling** | Fail fast with a clear error message: "Authentication failed for [source]. Check API key in .env." Skip that source; continue others. Log as a collection gap in the Evidence Log. |
| **Test** | Mock 401/403 responses; verify error message and graceful skip |

### 1.4 — Extremely Long Post / Review Text

| Attribute | Detail |
|---|---|
| **Scenario** | A Reddit post or forum thread is 10,000+ words (e.g., a detailed investment diary) |
| **Risk** | Exceeds LLM context window during extraction; storage bloat |
| **Handling** | Truncate to first 2,000 words for extraction (preserve full text in raw store). Log truncation. If the post is a thread, treat each top-level comment as a separate item. |
| **Test** | Feed a 15,000-word text; verify truncation and metadata flag |

### 1.5 — Post with No Text Content (Image/Video Only)

| Attribute | Detail |
|---|---|
| **Scenario** | A Reddit post is an image or video with no text body; a YouTube comment is just emojis |
| **Risk** | Extraction fails or produces nonsensical output |
| **Handling** | If `text.strip()` is empty or < 10 characters after stripping URLs and emojis, mark as `skipped_no_text` and filter out during preprocessing. Count in rejection log. |
| **Test** | Items with empty text, emoji-only, URL-only; verify filtered and counted |

### 1.6 — Duplicate Source-Native IDs Across Runs

| Attribute | Detail |
|---|---|
| **Scenario** | The one-time collection script is accidentally run twice, producing duplicate entries |
| **Risk** | Inflated corpus counts; skewed frequency analysis |
| **Handling** | `raw_items` table has a UNIQUE constraint on `(source, source_native_id)`. On conflict, skip the duplicate (INSERT OR IGNORE). Log the count of skipped duplicates. |
| **Test** | Run collection twice; verify no duplicate rows and skip count logged |

### 1.7 — Non-English / Purely Regional Language Post

| Attribute | Detail |
|---|---|
| **Scenario** | Post is entirely in Hindi, Tamil, Marathi, or another Indian language (not Hinglish — pure non-English) |
| **Risk** | LLM extraction quality drops significantly; Groq LLaMA models are English-primary |
| **Handling** | Detect language using `langdetect` or `fasttext`. Tag with `language_detected`. Include in corpus but flag extraction confidence as `low` for non-English items. Document as a known limitation in the Evidence Log. |
| **Test** | Feed pure Hindi text; verify language tag and low confidence flag |

### 1.8 — Deleted or Removed Post Encountered

| Attribute | Detail |
|---|---|
| **Scenario** | Reddit post returns `[deleted]` or `[removed]`; YouTube comment no longer exists |
| **Risk** | Garbage data in corpus |
| **Handling** | Filter out items where text is `[deleted]`, `[removed]`, or equivalent platform markers. Count in rejection log under `deleted_removed`. |
| **Test** | Feed `[deleted]` text; verify filtered out |

---

## 2. Preprocessing & Filtering Edge Cases

### 2.1 — Near-Duplicate with Slight Variations

| Attribute | Detail |
|---|---|
| **Scenario** | Same user posts nearly identical text on Reddit and a forum, with minor wording changes (e.g., "I stopped my SIP" vs. "I've stopped my SIP last month") |
| **Risk** | Both retained → double-counted in analysis |
| **Handling** | MinHash/SimHash near-duplicate detection with threshold ≥ 0.85. If duplicate detected across sources, keep the one with richer metadata (more context, earlier date). Log cross-source dedup count. |
| **Test** | Two texts with 90% similarity from different sources; verify one is deduplicated |

### 2.2 — Legitimate Repeat Poster (Different Content)

| Attribute | Detail |
|---|---|
| **Scenario** | Same user posts multiple times about their SIP journey — each post is genuinely different (month 1 update, month 6 update) |
| **Risk** | Overzealous dedup removes valid longitudinal data |
| **Handling** | Dedup is content-based (text similarity), not user-based. Different content from the same user is retained. The `username_hash` field allows tracking without identification. |
| **Test** | Two different posts from the same (hashed) user; verify both retained |

### 2.3 — PII Embedded in Investment Context

| Attribute | Detail |
|---|---|
| **Scenario** | "I started a SIP of ₹5000 with PAN ABCDE1234F in my HDFC account 1234567890" |
| **Risk** | PII makes it into the structured record and evidence spans |
| **Handling** | PII redactor runs before extraction. PAN regex, bank account regex, and NER all fire. Output: "I started a SIP of ₹5000 with PAN [PAN] in my [ACCOUNT]". Evidence spans are extracted from the redacted text. |
| **Test** | Text with PAN, bank account, phone; verify all replaced before extraction |

### 2.4 — PII Redactor False Positive

| Attribute | Detail |
|---|---|
| **Scenario** | "NAV of ABCDE1234F fund" — the fund code matches PAN regex pattern |
| **Risk** | Legitimate fund codes redacted, losing meaningful content |
| **Handling** | Add a context-aware exception list: known mutual fund scheme codes (AMC codes, ISIN patterns). If a PAN-like string appears near "fund", "scheme", "NAV", apply a lower-confidence redaction (keep original, flag for review). |
| **Test** | Text with fund code matching PAN pattern; verify not redacted (or flagged, not hard-replaced) |

### 2.5 — Relevance Classifier Boundary Cases

| Attribute | Detail |
|---|---|
| **Scenario** | "I invested in crypto and also started a SIP but then stopped the SIP because crypto was more exciting" — partially relevant |
| **Risk** | Classified as irrelevant (crypto-focused) and filtered out, losing SIP-related signal |
| **Handling** | Relevance classifier is tuned for **high recall**. If the text mentions SIP/mutual fund at all, retain it. The crypto context becomes `outside_app_behavior` or `barrier_or_trigger_to_stop` during extraction. |
| **Test** | Mixed-topic text with SIP mention; verify retained |

### 2.6 — Groww Mentioned in Negative Comparison

| Attribute | Detail |
|---|---|
| **Scenario** | "Zerodha is much better than Groww for SIPs, Groww's interface is confusing" |
| **Risk** | Could be tagged as competitor-only and excluded, despite containing Groww-specific feedback |
| **Handling** | `groww_specific = true` because Groww is mentioned. The competitor mention is noted but the item is retained. The exclusion rule only applies to posts about **other** platforms without any Groww mention. |
| **Test** | Post comparing Groww vs. competitor; verify retained with `groww_specific = true` |

### 2.7 — Groww Misspellings and Transliterations

| Attribute | Detail |
|---|---|
| **Scenario** | "grow app", "grouw", "ग्रो" (Hindi transliteration), "groww.in" |
| **Risk** | Groww tagger misses these → incorrectly tagged as platform-agnostic |
| **Handling** | Groww tagger uses a fuzzy matching list: `["groww", "grow app", "grouw", "groww.in", "ग्रो", "gro app"]`. Case-insensitive. Regex pattern: `gr[oa]+w{1,2}` to catch common misspellings. |
| **Test** | Texts with each misspelling variant; verify all tagged `groww_specific = true` |

### 2.8 — Entire Corpus Filtered Out

| Attribute | Detail |
|---|---|
| **Scenario** | Overly aggressive filtering leaves < 100 items in the corpus |
| **Risk** | Insufficient data for any meaningful analysis |
| **Handling** | Post-filtering sanity check: if retained corpus is < 10% of raw or < 500 items, log a **critical warning** and suggest relaxing relevance threshold. Do not proceed to extraction without user confirmation. |
| **Test** | Mock aggressive filtering leaving 50 items; verify critical warning and pipeline halt |

---

## 3. LLM Structured Extraction Edge Cases

### 3.1 — Hinglish / Code-Mixed Text

| Attribute | Detail |
|---|---|
| **Scenario** | "Maine SIP start kiya tha 2 months pehle but returns toh negative aa rahe hain, bahut tension ho rahi hai" |
| **Risk** | LLM may misparse, miss behavioral signals, or assign wrong emotion |
| **Handling** | Include Hinglish examples in the extraction prompt (few-shot). Test on a Hinglish subset. Tag `language_detected = "hinglish"`. Lower confidence threshold for Hinglish items. Document Hinglish accuracy in the AI Evidence Log. |
| **Test** | 20 Hinglish samples; measure per-field extraction accuracy vs. English baseline |

### 3.2 — Sarcasm and Irony

| Attribute | Detail |
|---|---|
| **Scenario** | "Great job Groww! My SIP lost 15% and your app shows a beautiful red graph 🎉" |
| **Risk** | LLM reads surface sentiment (positive emoji, "great") and tags `emotion = confidence` instead of `emotion = anger/disappointment` |
| **Handling** | Add sarcasm-detection guidance in the extraction prompt: "Watch for sarcasm indicators: positive words with negative outcomes, ironic emojis (🎉🤡👏), exaggerated praise followed by complaints." Flag extraction confidence as `medium` when sarcasm markers detected. |
| **Test** | 10 sarcastic samples; verify correct emotion and barrier extraction |

### 3.3 — Vague or Ambiguous Post

| Attribute | Detail |
|---|---|
| **Scenario** | "Is SIP even worth it anymore?" — no explicit behavior, no clear lifecycle stage, no segment info |
| **Risk** | LLM guesses/fabricates fields instead of using `unknown` |
| **Handling** | Prompt rule: "If the text does not explicitly state or strongly imply a field value, use 'unknown'. Never guess." Schema validator checks that `unknown` is used (not empty string or null). Items with ≥ 8 `unknown` fields are flagged as low-value but still retained. |
| **Test** | Vague one-liner; verify most fields are `unknown` and no fabrication |

### 3.4 — Multiple Behaviors in a Single Post

| Attribute | Detail |
|---|---|
| **Scenario** | "I checked my returns daily for 3 months, then reduced my SIP amount, asked my dad for advice, and finally stopped it" |
| **Risk** | LLM extracts only one behavior, losing the behavioral sequence |
| **Handling** | `behavior` field is an array — the schema allows multiple values. Prompt explicitly says: "Extract ALL behaviors mentioned, in order of occurrence if possible." |
| **Test** | Multi-behavior text; verify array contains all behaviors |

### 3.5 — Contradictory Information in Post

| Attribute | Detail |
|---|---|
| **Scenario** | "I love my SIP results" in the title but "I stopped my SIP because returns were terrible" in the body |
| **Risk** | LLM extracts conflicting `emotion` and `outcome` |
| **Handling** | Prompt rule: "If the text contains contradictory signals, prioritize the body text over the title, and later statements over earlier ones. Set confidence to 'low' for conflicting fields." |
| **Test** | Contradictory title/body; verify body-text signals win and confidence is `low` |

### 3.6 — Groq API Returns Non-JSON Response

| Attribute | Detail |
|---|---|
| **Scenario** | Groq returns a markdown-wrapped JSON (`\```json {...}\````) or adds preamble text ("Here is the extraction:") before the JSON |
| **Risk** | JSON parse fails → item goes to retry loop unnecessarily |
| **Handling** | Pre-parse cleanup: strip markdown code fences, strip leading/trailing non-JSON text, find first `{` and last `}` as JSON boundaries. Only then attempt `json.loads()`. |
| **Test** | Response with markdown fences, preamble text, trailing explanation; verify JSON extracted |

### 3.7 — Groq API Timeout or 500 Error

| Attribute | Detail |
|---|---|
| **Scenario** | Groq returns HTTP 500, 502, 503, or times out during extraction |
| **Risk** | Items permanently un-extracted; pipeline stalls |
| **Handling** | Retry with exponential backoff (1s → 2s → 4s, max 3 retries). If still failing, log the item as `extraction_status = "failed_api_error"`, skip, and continue. At end of run, report failed count. Items can be re-extracted later. |
| **Test** | Mock 500 and timeout responses; verify retry logic and graceful skip |

### 3.8 — Evidence Span Not Found in Original Text

| Attribute | Detail |
|---|---|
| **Scenario** | LLM generates an evidence span that is a paraphrase, not a verbatim excerpt |
| **Risk** | Traceability broken — the span can't be linked back to the source text |
| **Handling** | Schema validator checks if `evidence_span` is a substring of the original text (case-insensitive, whitespace-normalized). If not found, attempt fuzzy match (Levenshtein ratio ≥ 0.8). If still no match, flag and retry with repair prompt: "The evidence_span must be a verbatim quote from the text." |
| **Test** | LLM returns paraphrased span; verify repair prompt fires and corrects |

### 3.9 — Single Post Mentions Multiple Investors

| Attribute | Detail |
|---|---|
| **Scenario** | "My friend stopped his SIP after 2 months, but I continued mine because I trust the process" |
| **Risk** | LLM conflates two investors into one record |
| **Handling** | Prompt rule: "If the post describes multiple investors, extract fields for the **author** (the person writing). Only use third-party descriptions if the author is clearly describing their own experience through a third person." Set confidence to `low` for posts with ambiguous attribution. |
| **Test** | Post mentioning friend's and author's different behaviors; verify author's behavior extracted |

### 3.10 — Extremely Short Text (< 20 characters)

| Attribute | Detail |
|---|---|
| **Scenario** | A Play Store review: "Bad app" or "SIP failed" |
| **Risk** | LLM either fabricates context or produces mostly `unknown` fields — token cost wasted |
| **Handling** | Pre-check: if `len(text.strip()) < 20`, skip LLM extraction. Tag with `extraction_status = "too_short"`. Extract only: `emotion` (from sentiment keywords) and `groww_specific` (from text). Count these items separately. |
| **Test** | 5-word review; verify skipped from LLM and basic tags applied |

---

## 4. Theme Clustering & Scoring Edge Cases

### 4.1 — Item Belongs to Multiple Themes

| Attribute | Detail |
|---|---|
| **Scenario** | A record has `barrier = "low returns"` AND `confusion = "XIRR"` — fits both "Returns Disappointment" and "Knowledge Gap" themes |
| **Risk** | Item counted once (under-counting) or double-counted (inflating frequency) |
| **Handling** | Allow multi-theme assignment. Frequency counts use `unique items per theme` (one item counted once per theme). Composite score denominators use total corpus size. Document that themes are not mutually exclusive. |
| **Test** | Item matching two themes; verify counted in both without inflating total corpus count |

### 4.2 — Theme with Only "Unknown" Outcome Items

| Attribute | Detail |
|---|---|
| **Scenario** | A theme cluster has 50 items but all have `outcome = "unclear"` or `"unknown"` |
| **Risk** | Severity score is undefined (can't compute proportion of negative outcomes) |
| **Handling** | If < 20% of theme items have a known outcome, set `severity_score = null` and label as "Severity unscored — insufficient outcome data." Still rank by frequency and breadth. |
| **Test** | Theme with 100% unknown outcomes; verify severity is null and label applied |

### 4.3 — Very Small Theme Cluster (n < 5)

| Attribute | Detail |
|---|---|
| **Scenario** | Open coding produces a theme with only 3 items |
| **Risk** | Reported as a finding despite being anecdotal |
| **Handling** | Themes with n < 10 are flagged "Insufficient evidence" and excluded from the main ranked list. They appear in a separate "Emerging Signals" section if n ≥ 3. Themes with n < 3 are merged into the nearest parent theme or dropped. |
| **Test** | Theme with 4 items; verify appears in "Emerging Signals" only |

### 4.4 — All Items from a Single Source

| Attribute | Detail |
|---|---|
| **Scenario** | A theme's 40 items all come from Play Store reviews |
| **Risk** | Source bias inflates perceived importance (complaint skew) |
| **Handling** | Breadth score penalizes single-source themes (breadth = 1 source → low breadth score). Evidence level labeled "Directional only — single source" even if n ≥ 30. Source concentration is flagged in the opportunity card. |
| **Test** | Theme with 50 items all from one source; verify "Directional only" label despite sufficient n |

### 4.5 — Continuer Group Has Very Few Items

| Attribute | Detail |
|---|---|
| **Scenario** | Only 20 items have `outcome = "continued"` vs. 500 with `outcome ∈ {paused, reduced, stopped}` |
| **Risk** | Continuer vs. dropper comparison is statistically unreliable |
| **Handling** | If either group has n < 30, label the comparison as "Directional only — small sample." Use Fisher's exact test instead of chi-squared for small samples. Surface the imbalance prominently: "Caution: continuer sample (n=20) is significantly smaller than dropper sample (n=500)." |
| **Test** | 15 continuers vs. 400 droppers; verify Fisher's test used and warning surfaced |

### 4.6 — Scoring Weights Produce Unintuitive Rankings

| Attribute | Detail |
|---|---|
| **Scenario** | A high-frequency, low-severity theme (e.g., "checks returns daily" — common but benign) outranks a low-frequency, high-severity theme (e.g., "failed autopay → stopped SIP") |
| **Risk** | Actionable opportunities buried below noisy but harmless patterns |
| **Handling** | Weights are configurable in `config/scoring.yaml`. Default `0.4 / 0.4 / 0.2` balances frequency and severity. Provide a "sort by severity" option in the explorer UI. Document the scoring formula prominently. |
| **Test** | Two themes with inverted frequency/severity; verify ranking changes when sort-by toggle is used |

---

## 5. Query Engine & Chat Edge Cases

### 5.1 — Query About a Segment with No Data

| Attribute | Detail |
|---|---|
| **Scenario** | User asks: "What worries student investors?" but the corpus has only 2 items with `segment.income_stability = "student"` |
| **Risk** | System presents 2 items as if they represent student behavior |
| **Handling** | Response includes: "Only 2 items in the corpus match the 'student' segment — this is insufficient for reliable findings. Showing available data as directional only." Never extrapolate from thin data. |
| **Test** | Query for segment with n < 10; verify "insufficient" caveat in response |

### 5.2 — Query with No Matching Results

| Attribute | Detail |
|---|---|
| **Scenario** | "How many investors mentioned cryptocurrency staking as a reason to stop SIP?" — zero matches |
| **Risk** | Empty response or hallucinated answer |
| **Handling** | Return: "No items in the corpus match this query. The corpus covers [N] conversations about SIP behavior from [sources]. Try rephrasing or broadening your question." Never fabricate results. |
| **Test** | Query with zero matches; verify honest "no results" response |

### 5.3 — Ambiguous Query Intent

| Attribute | Detail |
|---|---|
| **Scenario** | "Tell me about returns" — could mean returns expectations, returns disappointment, checking returns, or XIRR confusion |
| **Risk** | System guesses wrong intent, provides irrelevant answer |
| **Handling** | If intent classifier confidence < 0.6, ask for clarification: "Your query could relate to several topics in the corpus. Did you mean: (a) return expectations at SIP start, (b) disappointment with returns, (c) how investors check returns, or (d) XIRR confusion?" |
| **Test** | Ambiguous queries; verify clarification prompt when confidence is low |

### 5.4 — Very Long User Query (> 500 words)

| Attribute | Detail |
|---|---|
| **Scenario** | User pastes a multi-paragraph question or their own analysis for commentary |
| **Risk** | Exceeds query input limits; intent classifier confused; token waste |
| **Handling** | Truncate input to 500 words with a notice: "Your query was truncated to 500 words. For best results, ask focused questions." Extract the core question from the first 2 sentences for intent classification. |
| **Test** | 1000-word query; verify truncation notice and correct intent extraction |

### 5.5 — SQL Injection via Chat Query

| Attribute | Detail |
|---|---|
| **Scenario** | User inputs: `"; DROP TABLE structured_records; --` |
| **Risk** | Database corruption |
| **Handling** | All SQL queries use parameterized statements (never string concatenation). The query engine's `sql_builder.py` generates queries programmatically from parsed intent, not from raw user text. User text only enters the LLM synthesizer as context, never as SQL. |
| **Test** | SQL injection strings in chat; verify no SQL execution, normal response returned |

### 5.6 — Vector Search Returns Irrelevant High-Similarity Results

| Attribute | Detail |
|---|---|
| **Scenario** | BGE embeddings return items about "SIP trunking" (VoIP technology) or "sip of water" as semantically similar to SIP investment queries |
| **Risk** | Irrelevant evidence cited in chat responses |
| **Handling** | Post-retrieval filter: only items that passed the relevance classifier (Stage 2) are in ChromaDB. Additionally, the LLM synthesizer has context about the domain and will ignore off-topic retrieved items. Set a minimum similarity threshold (e.g., cosine ≥ 0.7). |
| **Test** | Query that could match non-financial "SIP"; verify only investment-related results returned |

---

## 6. Guardrail & Refusal Edge Cases

### 6.1 — Indirect Investment Advice Request

| Attribute | Detail |
|---|---|
| **Scenario** | "Based on this data, should I invest in large-cap or mid-cap funds?" |
| **Risk** | The corpus *does* contain data about fund preferences — system might answer |
| **Handling** | Guardrail matches intent patterns for investment advice (keywords: "should I invest", "which fund", "large-cap vs mid-cap", "recommend"). Response: "I surface research findings about investor behavior, not fund recommendations. I can tell you what fund types first-time investors commonly mention, but I cannot advise on which to choose." |
| **Test** | 10 indirect advice-seeking phrasings; verify all refused |

### 6.2 — FOMO / Urgency in LLM-Generated Response

| Attribute | Detail |
|---|---|
| **Scenario** | Groq synthesizer generates: "Investors who don't act quickly on these findings risk losing their SIP momentum" |
| **Risk** | Urgency framing in the system's own output violates boundary rules |
| **Handling** | Post-synthesis guardrail scans for urgency/FOMO patterns: "act quickly", "don't miss", "risk losing", "time is running out", "before it's too late". If detected, rewrite with the LLM: "Remove urgency framing and present findings neutrally." |
| **Test** | Force LLM to generate urgency-framed response; verify guardrail catches and rewrites |

### 6.3 — User Asks to Compare Groww vs. Competitors

| Attribute | Detail |
|---|---|
| **Scenario** | "How does Groww compare to Zerodha for SIP retention?" |
| **Risk** | Corpus may contain comparison data, but the scope excludes competitor analysis |
| **Handling** | Refuse: "This corpus focuses on Groww and platform-agnostic SIP behavior. Competitor comparisons are outside the research scope. I can share what Groww-specific users report about their SIP experience." |
| **Test** | Competitor comparison queries; verify refusal with redirect |

### 6.4 — User Asks About Specific Fund Performance

| Attribute | Detail |
|---|---|
| **Scenario** | "What do investors say about HDFC Mid-Cap Opportunities Fund returns?" |
| **Risk** | Evidence spans may contain specific fund names — system could aggregate "reviews" of a fund |
| **Handling** | Refuse the comparison/recommendation framing. Redirect: "I can share general patterns about how investors perceive fund returns, but I don't evaluate or compare specific funds." If the corpus contains mentions, they're treated as behavioral data (expectations, disappointment), not fund reviews. |
| **Test** | Specific fund name queries; verify refusal |

### 6.5 — Guardrail False Positive on Legitimate Query

| Attribute | Detail |
|---|---|
| **Scenario** | "What returns do first-time investors expect?" — contains "returns" and "invest" but is a legitimate research question |
| **Risk** | Overzealous guardrail refuses a valid query |
| **Handling** | Intent classifier distinguishes between `exploration_query` (asking about corpus data) and `refusal` (asking for advice). The keyword-only guardrail is a **fallback**, not the primary gate. If intent classifier says `exploration`, bypass keyword guardrail. |
| **Test** | 20 legitimate queries containing investment keywords; verify none refused |

### 6.6 — User Tries to Extract Raw PII

| Attribute | Detail |
|---|---|
| **Scenario** | "Show me the original usernames of people who stopped their SIP" |
| **Risk** | System exposes PII from raw data |
| **Handling** | Usernames are hashed at ingestion (Phase 2) — originals are never stored. Evidence drill-down shows only anonymized excerpts. Response: "All user identities are anonymized. I can show anonymized evidence excerpts but not original usernames." |
| **Test** | PII extraction queries; verify no PII in any response |

---

## 7. UI & Presentation Edge Cases

### 7.1 — Opportunity Explorer with Zero Opportunities Above Threshold

| Attribute | Detail |
|---|---|
| **Scenario** | After filtering (e.g., segment = "student", source = "twitter"), no opportunity areas meet the evidence threshold |
| **Risk** | Empty explorer view with no explanation |
| **Handling** | Show empty state: "No opportunity areas meet the evidence threshold for this filter combination. Try broadening your filters." Show the filter values applied and total items matching. |
| **Test** | Apply restrictive filters producing zero results; verify empty state message |

### 7.2 — Evidence Drill-Down with Very Long Evidence Spans

| Attribute | Detail |
|---|---|
| **Scenario** | An evidence span is 100+ words (near the extraction limit) |
| **Risk** | Card layout breaks; evidence list becomes unreadable |
| **Handling** | Truncate displayed span to 80 words with "... [show more]" toggle. Full span available on click. Highlighted keywords within the span. |
| **Test** | Evidence span of 120 words; verify truncation and expand functionality |

### 7.3 — Data Scope Banner with Stale Data

| Attribute | Detail |
|---|---|
| **Scenario** | The pipeline was run 6 months ago. Data scope banner shows "Last updated: Apr 2026" |
| **Risk** | Users treat stale findings as current |
| **Handling** | If `last_updated` is > 90 days old, banner shows a warning icon: "⚠ Data is over 90 days old. Findings may not reflect current investor behavior." Banner is always visible and cannot be dismissed. |
| **Test** | Mock last_updated 120 days ago; verify staleness warning |

### 7.4 — Concurrent Users Querying Chat

| Attribute | Detail |
|---|---|
| **Scenario** | 10 users simultaneously submit chat queries, each hitting Groq API |
| **Risk** | Groq rate limit exceeded; some users get errors |
| **Handling** | Implement a request queue with max concurrency (5 simultaneous Groq calls). Excess requests queued with estimated wait time shown to user. If queue exceeds 20, return "System is busy, please try again in a few seconds." |
| **Test** | Simulate 15 concurrent chat requests; verify queuing and graceful degradation |

### 7.5 — Filters Produce an Impossible Combination

| Attribute | Detail |
|---|---|
| **Scenario** | User selects lifecycle_stage = "pre-start" AND outcome = "stopped" — nobody stops a SIP before starting one |
| **Risk** | Empty results with no explanation |
| **Handling** | Show: "No items match this filter combination (0 results). This may be a logically impossible combination." Do not hide the filters — let the user adjust. |
| **Test** | Apply contradictory filters; verify helpful empty-state message |

---

## 8. Infrastructure & System Edge Cases

### 8.1 — SQLite Database Corruption

| Attribute | Detail |
|---|---|
| **Scenario** | SQLite file corrupted due to unexpected process termination during write |
| **Risk** | Data loss; pipeline cannot continue |
| **Handling** | Use WAL (Write-Ahead Logging) mode for SQLite. Run `PRAGMA integrity_check` at pipeline start. If corruption detected, attempt recovery from WAL. Maintain a backup of the DB after each successful pipeline stage. |
| **Test** | Simulate crash during write; verify WAL recovery |

### 8.2 — ChromaDB Collection Out of Sync with SQLite

| Attribute | Detail |
|---|---|
| **Scenario** | Extraction completes and writes to SQLite, but ChromaDB embedding generation fails partway through |
| **Risk** | SQLite has records that ChromaDB doesn't — vector search returns incomplete results |
| **Handling** | Embedding generation is idempotent — can be re-run safely. A `backfill_chromadb.py` script checks for SQLite records missing from ChromaDB and generates embeddings for them. Run automatically at API server startup. |
| **Test** | Delete half of ChromaDB entries; run backfill; verify full sync |

### 8.3 — Disk Space Exhaustion During Extraction

| Attribute | Detail |
|---|---|
| **Scenario** | SQLite DB + ChromaDB + raw data exceed available disk space |
| **Risk** | Write failures, data corruption |
| **Handling** | Pre-flight check: estimate required disk space (corpus size × 5 for safety). Warn if < 1 GB available. During pipeline, catch `OSError` / `sqlite3.OperationalError` for disk-full conditions and halt gracefully with a clear message. |
| **Test** | Mock disk-full error during write; verify graceful halt and message |

### 8.4 — Groq Model Deprecation

| Attribute | Detail |
|---|---|
| **Scenario** | Groq deprecates `llama-3.3-70b-versatile` and the model ID no longer works |
| **Risk** | Extraction pipeline fails completely |
| **Handling** | Model version is configured in `config/extraction.yaml`, not hardcoded. Fallback model (`mixtral-8x7b-32768`) is specified. If primary model fails with a model-not-found error, automatically switch to fallback and log the model switch. |
| **Test** | Mock model-not-found response; verify fallback activation and logging |

### 8.5 — Pipeline Interrupted Mid-Extraction (Partial Run)

| Attribute | Detail |
|---|---|
| **Scenario** | Extraction script is killed after processing 2,000 of 5,000 items |
| **Risk** | Re-running extracts all 5,000 again, wasting tokens and time |
| **Handling** | Extraction is idempotent. Before processing an item, check if a `StructuredRecord` with that `raw_id` already exists. If yes, skip. Progress is tracked: "Extracted 2,000 / 5,000. Resuming from item 2,001." |
| **Test** | Kill extraction at 50%; re-run; verify resumes from last completed item |

### 8.6 — Python Dependency Conflict

| Attribute | Detail |
|---|---|
| **Scenario** | `chromadb` requires a different version of `pydantic` than `fastapi` |
| **Risk** | Installation fails or runtime errors |
| **Handling** | Pin all dependency versions in `requirements.txt`. Test installation in a clean virtualenv as part of CI. Document Python version requirement (3.11+). Use `pyproject.toml` with version ranges tested for compatibility. |
| **Test** | Fresh `pip install` in clean venv; verify no conflicts |

---

## Summary: Edge Case Coverage by Phase

| Phase | Edge Cases | Critical Ones |
|---|---|---|
| **Collection** | 8 | API rate limits, empty responses, deleted posts |
| **Preprocessing** | 8 | PII false positives, Groww misspellings, over-filtering |
| **Extraction** | 10 | Hinglish, sarcasm, non-JSON responses, evidence span mismatch |
| **Clustering & Scoring** | 6 | Multi-theme items, small clusters, single-source themes |
| **Query Engine** | 6 | Zero results, SQL injection, ambiguous queries |
| **Guardrails** | 6 | Indirect advice, FOMO in LLM output, false positive refusals |
| **UI** | 5 | Empty states, stale data, impossible filter combos |
| **Infrastructure** | 6 | DB corruption, ChromaDB desync, partial runs, model deprecation |
| **Total** | **55** | |

> Each edge case should have at least one corresponding test in the `tests/` directory. Use the test approach column as a starting point for test case design.
