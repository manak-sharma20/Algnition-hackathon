# Demo Video Script
*AIgnition 3.0 — Probabilistic Revenue Forecasting*

Target length: **3.5–4 minutes**. Covers the four things the brief requires: data ingestion, forecast generation, budget simulation, AI-generated business insights.

Record screen + voice (QuickTime screen recording or similar is fine). Practice the terminal section once so the timing feels natural — everything else is just clicking through the UI at a normal pace.

## Before you hit record

- Have two windows ready to alt-tab between: a terminal at the repo root, and Chrome with the War Room UI (`npm run dev` already running in the background, tab open but not yet navigated).
- Close other tabs/apps — nothing else visible.
- Terminal font size bumped up so it's readable on screen.

---

## 0:00–0:20 — Cold open (problem framing)

**[ON SCREEN]** Just your face or a title card — whatever's simplest. No terminal yet.

**[SAY]**
> "Digital marketing agencies plan ad budgets across Google, Meta, and Microsoft Ads using spreadsheets and gut feel. We built a system that replaces that with probabilistic forecasts — P10, P50, P90 ranges instead of a single guess — plus AI-generated explanations of *why* the models disagree. This is AIgnition — the War Room."

---

## 0:20–1:10 — Data ingestion + forecast generation (terminal)

**[ON SCREEN]** Terminal, repo root.

```bash
ls data/
```

**[SAY]**
> "Here's our input — the real Google Ads, Bing Ads, and Meta Ads exports from the challenge dataset. Three completely different raw schemas: Google reports spend in micros, Bing uses PascalCase columns, and Meta's 'conversion' field is actually revenue, not a count. Our pipeline detects and handles each one automatically."

```bash
./run.sh
```

**[SAY — while it runs, ~8 seconds]**
> "One command. It reads the raw CSVs, engineers features — lag revenue, rolling ROAS, seasonality flags — then loads our trained model and generates forecasts for every campaign, for 30, 60, and 90-day planning windows."

**[ON SCREEN]** Let the "Wrote 408 rows to ./output/predictions.csv" line land on screen.

```bash
column -s, -t output/predictions.csv | head -6
```

**[SAY]**
> "136 real campaigns, three forecast horizons each — that's our 408-row output. Revenue and ROAS ranges, plus a disagreement score and an uncertainty level for every single row."

---

## 1:10–1:50 — Channel Command Center (product overview)

**[ON SCREEN]** Switch to Chrome, navigate to the app if not already loaded. Let the globe animation settle for a second before talking.

**[SAY]**
> "This is the War Room. It loads that same predictions file. Front and center — projected revenue for the next 30 days across all three channels, with the full P10 to P90 range."

**[ON SCREEN]** Point at the P10/P50/P90 toggle in the bottom dock. Click P10, then P90, then back to P50.

**[SAY]**
> "This toggle reshuffles the *entire* dashboard between worst-case, expected, and best-case — every number, every chart, everywhere, at once."

**[ON SCREEN]** Point at the three channel cards (Google/Meta/Microsoft). Click into a budget field and change the number.

**[SAY]**
> "Each channel shows a ROAS health bar — green above 4x, amber 2 to 4x, red below — and its revenue range. Editing the budget here recomputes the projection live, using that channel's own current efficiency."

---

## 1:50–2:35 — Tribunal Verdict Panel (forecast generation + AI insight #1)

**[ON SCREEN]** Click the "TRIBUNAL" tab.

**[SAY]**
> "Every forecast here actually comes from three independent models — Prophet for seasonality, XGBoost for non-linear spend interactions, and Ridge as a simple sanity check. When they agree, great. When they don't, that's a real signal, not noise."

**[ON SCREEN]** Scroll to the campaign table, point at a row with a red or amber "Conflict"/"Diverge" badge.

**[SAY]**
> "This row's models disagree by double digits — flagged automatically."

**[ON SCREEN]** Click "Explain" on that row. Wait for the response (2–3 seconds).

**[SAY — while it loads, then read the result once it appears]**
> "That calls an LLM — Groq's API in our case — live, with the three models' actual numbers. It explains in plain English why they're diverging, not a canned template."

---

## 2:35–3:15 — Battle View (budget simulation + AI insight #2)

**[ON SCREEN]** Click the "BATTLE" tab.

**[SAY]**
> "This is budget simulation. Two allocations, side by side."

**[ON SCREEN]** Change a budget number in Allocation B (make it meaningfully bigger on one channel).

**[SAY]**
> "Change the spend, and projected revenue and blended ROAS update immediately — a winner gets flagged automatically."

**[ON SCREEN]** Click "Ask the tribunal to compare tradeoffs." Wait for the one-sentence response.

**[SAY]**
> "And this is the AI layer again — one sentence, generated live, weighing the actual tradeoff between the two plans."

---

## 3:15–3:45 — Close (engineering credibility)

**[ON SCREEN]** Back to terminal, or just talking head.

**[SAY]**
> "A few things we're proud of under the hood: this runs entirely offline — the only network call anywhere is the AI narration in the browser. We have 58 automated tests, and we didn't just trust that the numbers *looked* right — we ran a real backtest, holding out actual data the models never saw, to check accuracy honestly. That's AIgnition — thank you."

---

## Notes for recording

- If the "Explain" or "Ask the tribunal" calls are slow or fail on the day (free-tier API), have a fallback: re-record just that clip once with a fresh page load, or narrate over a static screenshot of a working response you captured earlier.
- Don't apologize on camera for the AI response taking a couple of seconds — a short natural pause while it loads is fine and honestly reads as "this is really calling an API live," not a canned demo.
- If you want a shorter cut (~2 min) for a secondary submission field, keep: cold open (trimmed to 10s) → terminal run.sh (trimmed to 20s) → Command Center P10/P50/P90 toggle (15s) → Tribunal "Explain" (30s) → Battle View compare (30s) → one-line close (10s).
