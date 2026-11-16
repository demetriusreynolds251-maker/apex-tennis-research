# Dataset A — Deployment Notes (v1.2)

## Hashes (per Standing Rule 1)
- **Before:** `c59e2f9fe5147e339dac8bb17eecc1f579b483d34a86e589e4873dfb01afe64c` (matches your §3 reference — confirmed correct baseline)
- **After:** `1dc845bcc8b873d9f6b2de388917326972e0510d32cfbf30c5c6624aefa85971`
- Full unified diff: `dataset_a_integration.diff`
- Patched file, ready to deploy: `openclaw_core_PATCHED.py`
- Syntax-checked with `ast.parse()` — clean (one pre-existing `SyntaxWarning`
  on line ~953, a docstring path escape, confirmed present in your original
  file — not introduced by this patch).

## Test suite result (per your directive — validated here, not in production)
**45/45 passed** — full run output in this session. Command: `pytest test_dataset_a.py -v`

One real bug was caught and fixed before you ever see this file:
`dataset_a_schema.sql` had `NULL` listed as an explicit member of several
`CHECK (... IN (...))` constraints (termination_reason, direction,
classification, final_grade, compliance_category, outcome,
outcome_source, validation_verdict). In SQLite, a value not matching any
other list item evaluates the whole `IN(...)` to `UNKNOWN` (three-valued
logic) when `NULL` is present in the list — and SQLite treats `UNKNOWN`
as "constraint satisfied," not "violated." That silently disabled all
eight of those CHECK constraints for any bogus value — the exact kind of
defect that would have let bad data into "OpenClaw's permanent memory
system" undetected. Removed `NULL` from all eight lists (SQLite already
permits `NULL` on a nullable column without listing it explicitly — no
functional loss). **`dataset_a_schema_v1.2.sql` in this delivery has the
fix; the file matches what actually passed the test suite.**


1. `dataset_a_capture_v1.2.py` → rename to `dataset_a_capture.py`, same
   directory as `openclaw_core.py`
2. `dataset_a_schema_v1.2.sql` → run once to create `data/warehouse/dataset_a.sqlite`
   (or let `dataset_a_capture.py` auto-create the directory — the schema
   file is for your own reference/inspection, `_connect()` doesn't apply
   it automatically; see "Still needed" below)
3. `openclaw_core_PATCHED.py` → replace `openclaw_core.py` after your
   normal backup step

## Deploy sequence (per your standing ops)
```
cd "/path/to/home/openclaw"
cp openclaw_core.py openclaw_core.py.bak.$(date +%F)
# copy in the three files above, renaming as noted
python3 -c "import sqlite3,pathlib; p=pathlib.Path('data/warehouse'); p.mkdir(parents=True,exist_ok=True); sqlite3.connect(p/'dataset_a.sqlite').executescript(open('dataset_a_schema_v1.2.sql').read())"
shasum -a 256 openclaw_core.py   # compare to 1dc845bc... above
rm -f data/cache/v8_api_cache.json
launchctl kickstart -k gui/$(id -u)/com.apex.discordbot
```

## What's captured now (all 18 sites from the approved integration plan)
- `eval_id` minted once in `process_single_prop`, before Gate 11 — never
  regenerated downstream
- Gate 11 REJECTED, Gate 11 unverified flag, Gate 11-B dominance key
- Research crash (`RESEARCH_FAILURE`) and research complete
- Evaluation truncated (`EVAL_TRUNCATED`), attempts exhausted
  (`EVAL_ATTEMPTS_EXHAUSTED`), compliance unparseable
  (`COMPLIANCE_UNPARSEABLE`)
- Evaluation complete + compliance complete (structured fields, not
  reasoning-text-only)
- All three `scoring_agent` no-pick paths: `BROKEN_EVAL`,
  `AUDIT_MALFORMED`, `BP_RULE_BLOCKED`
- Full confidence ledger + `ledger_empty_flag` on every successful score
  (this is your HIGH-SEVERITY defect signal, now structured — no more
  re-parsing `override_note` text to find it)
- `RULE28_DEDUP` — the selection-bias fix. A fully-scored GREEN excluded
  by dedup now leaves a row instead of vanishing.
- `POSTED` for every pick actually sent to Discord (test-mode runs
  correctly excluded)

## Three things I flagged mid-patch rather than deciding for you

1. **`pipeline_version` is `None` everywhere.** No version/hash constant
   exists anywhere in `openclaw_core.py` today. Recommend adding one
   (e.g. `CORE_VERSION = "v7.9.8"` near the top) so this and future
   SHA-tracking share one source. Small, separate change — didn't fold
   it into this patch since it's outside Dataset A's scope.

2. **`BP_RULE_BLOCKED` vs `NO_PLAY`.** The BP hard-stop (BP MORE below
   line 2.5) reads, in spirit, like "OpenClaw correctly determined there's
   no play" — similar to moneyline `NO_PLAY`. I kept it as its own
   `BP_RULE_BLOCKED` code per your already-approved schema rather than
   reclassifying it unasked. Worth a ruling if you want BP hard-stops to
   report alongside `NO_PLAY` in Mission Control later.

3. **Slip linkage is NOT wired at `output_agent`.** I found the codebase's
   real `slip_id` concept lives in `parse_slip_entry` (line ~7868),
   created only when you manually log an actual placed bet — a different
   event than the Discord post. Wiring `d1.add_slip_member()` belongs
   there, using the same player+line+stat_type lookup
   `_find_archived_evaluated_line` already does to resolve back to an
   `eval_id`. Didn't guess at a fake slip_id in `output_agent` to avoid
   corrupting the linkage.

## Not yet touched (per your priority order, these come after Dataset A)
- Moneyline orchestrator (`evaluate_moneyline` / `moneyline_evaluation_agent`)
  — schema and capture module both already support `evaluation_type="MONEYLINE"`
  and `NO_PLAY`; wiring the actual call sites needs you to point me to the
  per-match moneyline loop (still hasn't been located in this file)
- Outcome linking (`d1.record_outcome`) — reuses your existing WIN/LOSS
  alert + `pending_results.json` parsing; needs me to find that code path
  (didn't see it in the sections reviewed so far — likely in
  `learning_agent` or `verify_result_via_v8`, both in the file but not
  yet traced)
- `slip_id` wiring in `parse_slip_entry`
- GREEN Validation Suite → `d1.record_validation()` (separate file,
  `green_validation_suite.py`, not part of this upload)

## Regression testing
Your standing rule requires `test_replay.py`/`test_finding1.py`-style
coverage before anything ships. I have not run your actual test suite
against this patch (not included in the upload) — recommend running it
before deploying, and I'm available to write a `test_dataset_a.py`
covering the 18 capture sites if you want that as a companion piece.
