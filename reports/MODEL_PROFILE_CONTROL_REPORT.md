# COMMAND CHAT MODEL & PROFILE CONTROL — IMPLEMENTATION REPORT

---

## LEAD WITH THE REAL FINDING

Auditing the actual files before building (same discipline as last time) found the model/profile *data* — `MODELS`, `MODEL_LABELS`, `PROFILE_PROMPTS`, `PROFILE_LABELS` — already fully defined in `command_chat_engine.py`, matching your spec closely (correct default of Haiku, correct Opus/Sonnet/Haiku mapping, correct profile behaviors including "Fable").

**But it wasn't wired to anything, and there was a real, live bug underneath it**: `build_request()` referenced a bare `MODEL` name that doesn't exist anywhere in the file anymore — confirmed by actually triggering it: `NameError: name 'MODEL' is not defined`, on every single call. If this exact file were what's deployed, Command Chat could not have sent a single working request, model selection or not. Fixed first, verified the fix, then built the actual selection/switching/persistence logic on top of a working foundation instead of a broken one.

---

## WHAT WAS BUILT THIS SESSION

**Backend (`command_chat_engine.py`):**
- `build_request(conversation_messages, model_key, profile_key)` — now resolves real values from the existing `MODELS`/`PROFILE_PROMPTS` dicts instead of crashing. Unknown/missing keys degrade to the default rather than raising.
- `run_turn(..., model_key, profile_key)` — threads the selection through every tool-use round of a turn, and **returns** `model_used`/`profile_used` (resolved labels) so the frontend can show what was actually used, not just what was requested.
- The key design point for the "no new session" requirement: **model and profile are resolved fresh on every single call, never stored against the session.** That's what makes switching mid-conversation just work — there's no session-level state to reset.

**Backend (`openclaw_mission_control.py`):**
- `command_chat_turn()` and the `/api/command_chat` route now accept and pass through `model_key`/`profile_key` from the request body.
- New `command_chat_options()` / `GET /api/command_chat_options` — returns the model/profile lists **sourced directly from `command_chat_engine`'s own dicts**, so the dropdown contents can never silently drift out of sync with what the backend actually supports.

**Frontend:**
- Two `<select>` dropdowns (Model, Profile) added to the chat panel header.
- `localStorage` persistence (`apex_chat_model_key`, `apex_chat_profile_key`) — survives page refresh and browser restart, per your requirement, no database changes.
- Every assistant message now shows a `Model: X · Profile: Y` line, using what the backend actually reports it used — not just an echo of the selector at send time.

---

## TESTING — every requirement independently verified, not assumed

Same standard as every prior session: real function calls, real mocked multi-turn conversations, real `jsdom`-parsed DOM — not visual inspection.

| Requirement | Verified how |
|---|---|
| Model/profile resolve correctly, unknown keys don't crash | Direct calls to `build_request()` with valid, missing, and garbage keys |
| **Live switching mid-conversation, same session, no reset** | Ran 3 consecutive `run_turn()` calls with the same `session_id`, switching Haiku→Sonnet→Opus and Default→Investigator→Architect between them — confirmed each call used exactly the requested model, confirmed no new session was created |
| Selectors populate from the backend, not hardcoded twice | `chatCC()` fetches `/api/command_chat_options` and builds the `<select>` contents from the response |
| Selection persists across "reload" | Real `jsdom` test: set selectors → save → wipe and rebuild the panel (simulating a reload) → confirmed the saved selection was restored, not reset to default |
| Sending a message uses the *current* selector value | Changed the selector, sent a message, inspected the actual JSON body that would hit the network — confirmed it matched the selector, not a stale default |
| Response shows which model/profile were actually used | Inspected the rendered HTML after a response — confirmed the `Model: ... · Profile: ...` line is present and correct |
| **Mid-conversation switch produces one unbroken transcript** | The test that actually matters most: switched models between two messages in the same live session (no reload, no new chat) and confirmed **both** the pre-switch and post-switch answers are visible together in the same message list |

One test-writing mistake worth being upfront about: an earlier draft of the switching test accidentally ran the switch *after* a simulated page reload, which of course wipes the visible transcript — that's correct browser behavior, not a bug, but it would have produced a misleading "failure." Caught it, reordered the test to isolate the actual live-switch behavior from the unrelated reload behavior, and reran clean.

---

## KNOWN, DELIBERATE LIMITATION

Per "no database changes required": `model_used`/`profile_used` are shown live for the current session but **not persisted** to `command_chat_log` (no new columns were added). Reopening a past session from the history browser will show its messages and sources correctly, but not which model/profile generated each historical answer. This is a direct consequence of the no-schema-change constraint, not an oversight — flagging it rather than let it surface as a surprise.

---

## FILES

| File | Change |
|---|---|
| `command_chat_engine.py` | Critical bug fix (`build_request` crash) + model/profile threading through `build_request`/`run_turn` |
| `openclaw_mission_control.py` | New `command_chat_options()` + route, `command_chat_turn()` threading, selector UI, persistence, response footer |

Additive-only, confirmed: 4 modified lines total in `openclaw_mission_control.py` across every session of changes to this file combined — nothing from this session added to that count beyond what was already there.

---

## ROLLBACK

Standard: `git checkout` either file. The `build_request` bug fix is the one change here that isn't purely additive in the strictest sense (it repairs a broken reference rather than adding new code) — reverting it would restore the crash, so if anything about this session needs to be rolled back, that specific fix should stay regardless of what else reverts.
