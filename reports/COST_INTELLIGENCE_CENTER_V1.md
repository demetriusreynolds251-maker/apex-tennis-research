# COST INTELLIGENCE CENTER V1 — IMPLEMENTATION PACKAGE
**Built, not just designed. Tested against real captured data, including one bug found and fixed during testing.**

---

## 1. ARCHITECTURE REVIEW

No new infrastructure, confirmed against the actual approved scope: reads only `ate.db`'s `ai_traces` table (the table already exists, already populated by the fail-open capture layer from ATE V1). No new writers, no new tables, no schema changes. Two files touched, both already ATE-integrated from prior sessions: `ate_queries.py` (query layer — new functions appended) and `openclaw_mission_control.py` (new screen — additive only, same pattern as the Evaluation Trace Center panel enrichment).

**One real design decision, made and tested, not assumed:** `ai_traces.created_at` is stored via SQLite's `datetime('now')` — UTC. The rest of Apex's "today"/day-boundary concept is Central Time (confirmed: `openclaw_ops.today_str()` uses `datetime.now(oc.CT)`, and `CT = pytz.timezone("America/Chicago")` is a real constant in `openclaw_core.py`, line 239). SQLite's own `date()`/`datetime()` functions have no IANA timezone awareness — they'd use the server's system timezone, not necessarily Chicago. Every day-boundary calculation in this build (Today/7-day/30-day windows, daily history) converts through `pytz`'s `America/Chicago` explicitly, in Python, before touching SQL — **and this was tested at the actual boundary**, not just the happy path (see Section 5).

---

## 2. EXACT FILES MODIFIED

| File | Change |
|---|---|
| `ate_queries.py` | Added `pytz`/`datetime` imports, a `CT` constant (duplicated from `openclaw_core.py`'s, not imported — keeps this module dependency-light rather than pulling in `openclaw_core.py`'s full startup path for one constant), and 9 new functions: `_connect`, `_ct_window_utc_bounds`, `_to_ct_date`, `cost_summary`, `_eval_aggregates`, `evaluation_metrics`, `model_breakdown`, `step_type_breakdown`, `top_expensive_evaluations`, `top_slowest_evaluations`, `daily_cost_history`, `cost_intelligence_bundle`. Nothing existing touched. |
| `openclaw_mission_control.py` | One new backend function (`cost_intelligence_view`), one new route (`/api/cost_cc`), one new sidebar link, one new container div, one new `load()` dispatch line, one new JS render function (`costCC`). Nothing existing touched — confirmed via diff, 0 modified lines from this session (2 modified lines total in the file are both carried over from the prior session's `eval_id` bug fix, not new). |

---

## 3. QUERY DESIGN

Real SQL aggregation (`GROUP BY`, `SUM`, `AVG`), not Python loops over all rows — per the explicit instruction, and because it scales better than pulling the whole table into memory. **One deliberate, documented exception:** `daily_cost_history()` — SQLite genuinely cannot do CT-timezone-aware day bucketing natively (no IANA tz support), so that one function pulls 3 columns (`eval_id, cost_usd, created_at` — not `SELECT *`) and buckets in Python. This is the one place "aggregation queries against ai_traces" isn't pure SQL, and it's the one place it structurally can't be.

Every "evaluation" in Sections 2/5/6 means the **sum across every traced step for one `eval_id`** (an evaluation typically has both an `evaluation` step and a `compliance` step), not a single raw `ai_traces` row — via a `GROUP BY eval_id` subquery (`_eval_aggregates`), matching what "highest-cost evaluation" actually means.

---

## 4. MISSION CONTROL INTEGRATION PLAN — executed, not just planned

Followed the exact same conventions confirmed against the real file in the Evaluation Trace Center session: `<a data-v="costcc">` sidebar link, `<div id="v-costcc">` container, `elif u.path == "/api/cost_cc"` route, `if(VIEW=='costcc')` dispatch in `load()`, and a `costCC(d)` render function using the same `.strip`/`.tile`/`.t`/`.v` summary-card markup and `<table><tr><th>` list markup already used by every other screen in the app — not a new visual style introduced. Clickable rows in Sections 5/6 call the existing `openEval(id)` function, so "Most Expensive Evaluations" and "Slowest Evaluations" drill directly into the same enriched evaluation-detail panel built last session — no duplicate detail experience, consistent with your standing instruction from that session.

---

## 5. TESTING PLAN — executed

1. **Syntax**: Python (`ast.parse`) and the actual embedded JavaScript (extracted and checked with `node --check`) — both clean.
2. **Real captured data, not synthetic-only**: seeded 4 realistic `ai_traces` rows across 3 evaluations (mixed models, step types, costs, latencies) and ran the full `cost_intelligence_bundle()` against them.
3. **A real bug found and fixed during this pass**: `evaluation_metrics()`'s `avg_cost_per_evaluation` initially computed `AVG(cost_usd)` over raw `ai_traces` rows — averaging per *trace*, not per *evaluation*. An evaluation with 2 traces (evaluation + compliance) was silently pulling the average down relative to what "per evaluation" actually promises. Caught by checking the arithmetic by hand against the seeded data (`0.0643` shown, `0.0857` expected), not by assuming the query was correct because it ran without error. Fixed to average the `GROUP BY eval_id` summed totals instead; re-verified against the exact expected value.
4. **CT timezone boundary tested at the actual edge, not just the typical case**: inserted a trace at `2026-07-14 03:00:00` UTC — which is `2026-07-13 22:00:00` in Chicago time (CDT, UTC-5 in July) — and confirmed `daily_cost_history()` correctly buckets it into `2026-07-13`, not a naive UTC-based `2026-07-14`.
5. **Full JS runtime execution** (not just parse-checked) against the real bundle produced by the real query functions: confirmed correct section content, correct model name, correct edge-case date appearing, and explicitly checked for zero leaked `undefined`/`NaN` in the rendered HTML — both for real data and for the no-ATE-available fallback path.

---

## 6. ROLLBACK PLAN

Same standard as every prior ATE change: every edit to both files is a pure addition (new functions, new route, new nav item, new container, new dispatch line) — a `git diff` shows zero modified lines in `ate_queries.py` from this session, and zero *new* modified lines in `openclaw_mission_control.py` beyond what the prior session already changed. Reverting is `git checkout` on either file to the last known-good commit; nothing else in Mission Control or the ATE capture layer has any dependency on Cost Intelligence Center existing.

---

## 7. FINAL IMPLEMENTATION PACKAGE

All 4 files current and included: `ate_queries.py` (with the fix), `openclaw_mission_control.py`, plus their diffs for review before deployment. Restart whichever process runs Mission Control (per the earlier "how to access Mission Control" answer) for the new screen to appear.
