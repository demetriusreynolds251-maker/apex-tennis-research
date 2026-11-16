# APEX COMMAND CHAT V1 — IMPLEMENTATION PACKAGE
**Full 5-phase build, per the authorization. Built and tested — including one real bug found and fixed during testing. One honest, unavoidable limitation stated up front.**

---

## THE ONE THING THAT COULDN'T BE TESTED HERE, STATED PLAINLY

This sandbox has no network path to `api.anthropic.com` — confirmed early in this whole build (mocking `requests.post` to test `call_model()`), true regardless of API credit status. Everything below was built for real and tested for real **except one specific thing**: whether Claude's actual tool-use behavior matches what `command_chat_engine.py`'s loop expects. That loop was verified against a realistic **mocked** multi-turn conversation (correct caching shape, correct tool dispatch, correct `tool_result` wiring, correct final-answer detection) — the same rigor as every `call_model()` test this session — but a mock is a mock. Real confirmation happens on the Mac Mini, with real API access.

---

## 1. ARCHITECTURE REVIEW

Two new SQLite files (`command_chat.db`, separate from `ate.db` — same "one file per concern" pattern used throughout), zero new external infrastructure. `command_chat_tools.py` wraps only already-proven interfaces: `ate_queries.py` (fully tested), `openclaw_ops.pick_from_eval()` (confirmed real, tested this session against a real scratch Dataset A schema), and Dataset B's confirmed real table names (`players`, `rankings_snapshot`) from `tennis_warehouse_collector.py`'s actual INSERT statements. Nothing reimplements a connection this session doesn't have verified access to.

## 2. EXACT FILES

| File | New/Modified | Purpose |
|---|---|---|
| `command_chat_schema_v1.sql` | New | `decision_records`, `investigation_records`, `command_chat_log`, `memory_search` (FTS5) |
| `command_chat_db.py` | New | Schema init, mirrors `ate_db.py` exactly |
| `command_chat_writer.py` | New | Phase 1/2/3: record writers + FTS5 search |
| `command_chat_tools.py` | New | Phase 3/4: the 9 required read-only tools |
| `command_chat_engine.py` | New | Phase 5: system prompt, tool schema, tool-use loop, real (untested-live) Claude API call |
| `openclaw_mission_control.py` | Modified (additive only — confirmed 0 new modified lines beyond prior sessions) | Command Chat screen, POST route, New Chat button, inspector-panel entry point |

## 3. DATABASE SCHEMA

Exactly as specified in the authorization — `decision_records` and `investigation_records` with the given fields, plus `command_chat_log` (session_id/role/content/sources_cited) for cross-session continuity without an ever-growing live context window, plus `memory_search` (FTS5, unified across both records tables).

**Backfilled with 3 real decisions and 2 real investigations from this project's own history** (Top 100 ATP/WTA, ATE-over-Langfuse, LightGBM-as-first-challenger; the fallback-year-leakage bug, the ATE archive-verification findings) — not placeholder data.

## 4. FTS5 IMPLEMENTATION

`search_decisions()`/`search_investigations()` tested against the real backfilled data: `search_decisions("Langfuse")` correctly returns the ATE decision; `search_investigations("archive")` correctly returns the archive-verification investigation. **Also deliberately tested the known limitation, not just the success case**: `search_decisions("why did we pick a boosting model")` — a conceptual query sharing no keywords with the actual record text ("machine learning challenger," not "boosting") — correctly returns nothing. This is the FTS5 keyword-only limitation flagged in the original Memory Architecture Review, now demonstrated in practice, not just predicted in theory.

## 5. TOOL LAYER

All 9 required tools built and individually tested. **One real bug found and fixed**: `get_dataset_b_player()` initially crashed with `sqlite3.OperationalError: no such table: players` when the warehouse file didn't exist yet — because SQLite silently creates an empty file on connect rather than erroring on a missing path, so the missing-file case wasn't actually caught by the code as written. This broke the established fail-safe contract every other Dataset-facing function in this codebase follows (confirmed by reading `openclaw_ops._warehouse_query`'s own docstring: "a locked or missing warehouse file degrades to an empty result, never raises"). Fixed to match that contract exactly, then re-tested against three real cases: no file, file-exists-but-empty, and real data — all three now degrade or succeed correctly, none raise.

Provenance is stated per-tool in the module docstring, not uniformly claimed: ATE-backed and `decision_records`/`investigation_records`-backed tools are fully proven; `search_rules()` is explicitly flagged as searching activation *history*, not rule *definitions* (the actual rule text lives in `.txt` files on the Mac Mini, not any queryable table this session has access to); `get_dataset_b_player()`'s `player_year_stats` columns are queried via `SELECT *` deliberately, since that table's full schema was never independently confirmed.

## 6. CHAT ARCHITECTURE

`command_chat_engine.py`: `SYSTEM_PROMPT` + `TOOL_SCHEMA` (9 tools, matching the real Anthropic tool-use request shape) + `build_request()` (applies `cache_control` automatically — never a user setting, per the authorization) + `run_turn()` (the loop: send request, dispatch any `tool_use` blocks, feed back `tool_result`, repeat until a final text answer or a `max_tool_rounds` safety valve). Read-only by construction — every tool in `TOOL_SCHEMA` maps to a read-only function; there is no tool defined that writes to Dataset A/B or triggers an evaluation, so the loop has no path to attempt either even if asked.

**Tested against a realistic mocked 2-round conversation**: user asks why confidence dropped → mock Claude calls `get_evaluation` → real tool executes against real Dataset A → mock Claude gives a final answer using the real tool result. Verified: correct `cache_control` shape sent, correct tool dispatch, correct `tool_result`/`tool_use_id` wiring, correct final-answer detection, and — separately — the `max_tool_rounds` safety valve actually stops an infinite tool-calling loop rather than hanging.

## 7. MISSION CONTROL INTEGRATION

The hybrid design from the readiness review, built: a dedicated "Command Chat" nav screen (message list, input box, **visible "+ New Chat" control** per the explicit requirement) **and** a contextual entry point — a "💬 Ask Command Chat about this evaluation" button added to the existing enriched inspector panel, appearing only when real ATE data (and therefore a real `eval_id`) is available for that evaluation, consistent with the same known limitation already documented for the `/api/pick` (non-eval_id) path. Clicking it switches to the chat screen with the evaluation's `eval_id` silently attached to the next question, so the operator doesn't have to repeat it.

**Runtime-tested, not just parsed**: extracted and executed the real `renderPickDetail`/`chatCC`/`sendChatMessage`/`askAboutThisEval` functions against realistic data — confirmed the button renders with the correct `eval_id` wired in, confirmed a chat message actually round-trips through a mocked `fetch` to `/api/command_chat` with the correct session ID and message body, confirmed the assistant's answer renders back into the message list, and confirmed starting a New Chat correctly clears both the message list and the eval-context attachment.

## 8. TESTING PLAN — executed

Syntax (Python `ast.parse` + real embedded JS via `node --check`) at every step; each new module tested in isolation against real or realistically-mocked data before integration; the full engine loop tested against a mocked multi-turn conversation; the full UI tested via real JS execution, not just visual inspection. Two real bugs were caught this way, not assumed away: the `get_dataset_b_player` crash (Section 5) and — worth restating — this is the second time in this build that "does it parse" and "does it run correctly" turned out to be different questions worth testing separately.

## 9. ROLLBACK PLAN

Same standard as every ATE/Cost-Intelligence change: every new file is genuinely new (delete to remove), and `openclaw_mission_control.py`'s changes are confirmed purely additive (0 new modified lines beyond what prior sessions already changed) — `git checkout` reverts cleanly with no entangled behavior change to unwind.

## 10. FINAL DEPLOYMENT PACKAGE

All 5 new files plus the updated `openclaw_mission_control.py` and its diff, included. Deploy alongside the existing ATE/Cost Intelligence files from prior sessions. **Before trusting this live**: confirm `oc.ANTHROPIC_API_KEY` is set (real key, not the hardcoded placeholder flagged for rotation earlier this project), then ask one real question through the UI and confirm the mocked-loop assumptions hold against the real API — the one thing this sandbox genuinely could not confirm.
