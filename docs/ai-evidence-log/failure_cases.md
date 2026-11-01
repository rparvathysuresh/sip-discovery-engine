# AI Evidence Log: Known Failure Cases & Resolutions

> **Document Version:** 1.0.0  
> **Phase:** Phase 8 — Validation, Evidence Log & Polish (Task 8.4)  
> **Scope:** Documents edge cases, failure patterns, and architectural mitigations in structured extraction and classification across Indian retail investor discussions.

---

## Failure Mode Taxonomy

```
Total Documented Cases: 10
Categories:
├── Linguistic & Code-Mixing (Hinglish, Sarcasm, Colloquialisms)
├── Structural Sparsity (Extreme brevity, Missing tenure, Vague expressions)
└── Conceptual Ambiguity (Multi-intent conflicts, Currency/number normalization, Inverted sentiment)
```

---

## Documented Failure Cases

### Case FAIL-001: Heavy Sarcasm / Irony
- **Raw Excerpt:** *"Groww is the best app in the universe! It debits my bank account twice every month and gives zero customer support. What a genius feature!"*
- **Naive LLM Failure:** Classifies sentiment as `positive` and outcome as `continued` due to superficial words like *"best app"* and *"genius feature"*.
- **Mitigation / Resolution:** Few-shot prompt engineering in `src/extraction/prompts/extraction_v1.txt` instructs the model to detect contrastive irony and prioritize functional outcomes (`double debit`, `zero support`) over sarcastic compliments. Emotion mapped to `anger` / `frustration`.
- **Status:** Resolved in `extraction_v1` and verified.

---

### Case FAIL-002: Code-Mixed Hinglish Slang
- **Raw Excerpt:** *"Bhai mandate reject ho gaya aur HDFC ne 300 ka chuna laga diya. SIP bandh kar raha hu abhi."*
- **Naive Failure:** English-only tokenizers and regexes fail on *"chuna laga diya"* (incurred a penalty/loss) and *"mandate reject ho gaya"*.
- **Mitigation / Resolution:** Groq LLM prompt explicitly includes Hindi/Hinglish idiom guides. Theme clusterer includes regex stems matching `bounce`, `penalty`, `mandate`, `hdfc`, `reject`.
- **Status:** Resolved.

---

### Case FAIL-003: Extreme Brevity / Zero Context
- **Raw Excerpt:** *"Worst app. Total loss."*
- **Naive Failure:** Hallucinates specific lifecycle stages (e.g. `months_2_3`) or specific mutual fund barriers without evidence.
- **Mitigation / Resolution:** Schema validator enforces that if text is under 15 words and lacks temporal markers, `lifecycle_stage` defaults to `unknown`, `segment` defaults to `unknown`, and `evidence_span` must directly quote the verbatim input.
- **Status:** Resolved.

---

### Case FAIL-004: Inverted Sentiment (Positive Tone on Negative Outcome)
- **Raw Excerpt:** *"Finally broke free from my monthly SIP habit! Kept seeing portfolio in red every morning and felt sick. Withdrew everything and feel so peaceful now."*
- **Naive Failure:** Model detects relief/peace (`confidence` or `satisfaction`) and mislabels as a successful journey.
- **Mitigation / Resolution:** The outcome taxonomy is strictly grounded on the SIP retention state: if funds were redeemed/stopped, `outcome` is forced to `stopped`. Primary barrier identified as `market correction panic / red portfolio anxiety`.
- **Status:** Resolved.

---

### Case FAIL-005: Indian Currency Symbol Ambiguity (`₹` vs `Rs.` vs `INR`)
- **Raw Excerpt:** *"Debited ₹500 thrice instead of single debit of Rs 500. Total INR 1500 gone."*
- **Naive Failure:** Regex parsers searching strictly for `\d+` or `Rs \d+` miss UTF-8 currency symbol `₹` or token boundaries.
- **Mitigation / Resolution:** Preprocessor and clusterer normalize `₹`, `rs.`, `rs`, and `inr` to lowercase `rs` before keyword matching and regex evaluation.
- **Status:** Resolved.

---

### Case FAIL-006: Multi-Intent Conflict (Continuer Experiencing Bug)
- **Raw Excerpt:** *"I love Groww and have 12 active SIPs running for 2 years, but yesterday one mandate got stuck on processing. Please fix this bug!"*
- **Naive Failure:** Classifier marks the user as `stopped` or `churned` because of the mandate bug trigger.
- **Mitigation / Resolution:** Intent classification distinguishes between structural churn triggers and temporary bug reports from loyal continuers. `outcome` is correctly tagged as `continued`, with `lifecycle_stage = months_12_plus`.
- **Status:** Resolved.

---

### Case FAIL-007: Implicit Churn / Passive Disengagement
- **Raw Excerpt:** *"Haven't logged into mutual fund app in 8 months. Salary account changed so mandate probably stopped on its own. Too lazy to re-link."*
- **Naive Failure:** Keyword search for "cancel" or "pause" finds no match; misses the passive dropout.
- **Mitigation / Resolution:** Added `forgotten / inactive sip` theme in `config/codebook_v1.yaml` with keywords `[salary account changed, haven't logged in, too lazy, stopped on its own]`. Outcome tagged as `stopped`.
- **Status:** Resolved.

---

### Case FAIL-008: XIRR vs Absolute Returns Misunderstanding
- **Raw Excerpt:** *"Absolute returns show 15% but annualised XIRR is only 4.8%. The app math is broken, AMC is cheating us."*
- **Naive Failure:** Treated as general technical bug rather than financial concept literacy gap.
- **Mitigation / Resolution:** Tagged under category `XIRR & Returns Misunderstanding` with theme `xirr vs absolute return confusion`. Enables targeted educational retention interventions.
- **Status:** Resolved.

---

### Case FAIL-009: Competitor Comparison Query Injection
- **Raw Excerpt:** *"Should I stop my Groww SIP and switch completely to Zerodha Coin or Kuvera?"*
- **Naive Query Engine Failure:** Generates competitor comparisons or subjective advice.
- **Mitigation / Resolution:** Pre-execution Guardrail (`src/query/guardrails.py`) intercepts queries containing competitor pairs (`Groww vs Zerodha`, `switch to Zerodha`) and emits a policy refusal with educational redirection.
- **Status:** Resolved and enforced by middleware.

---

### Case FAIL-010: FOMO / Get-Rich-Quick Framing
- **Raw Excerpt:** *"Invest now or you'll miss out on the crypto / small cap rally! Double your money in 6 months."*
- **Naive Query Engine Failure:** Synthesizes speculative hype or urgent market-timing claims.
- **Mitigation / Resolution:** Guardrail regex detects FOMO urgency triggers (`invest now or you'll miss out`, `double your money`) and immediately issues a policy block.
- **Status:** Resolved and covered in test suite.

