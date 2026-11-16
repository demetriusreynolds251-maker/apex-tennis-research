# SA365 Per-Set Data Pipeline — Architecture, Coverage & Validation
**2026-09-27 — Phases 1-6 of the SA365 field-audit build-out**

Discipline note up front, same as the Ace/DF investigations: MD5 of both
frozen files verified unchanged before and after this work
(`apex_prop_sim_v1.py` = `7b03e521e804862b85804f8ac4db7346`,
`apex_prop_model_v1.py` = `6bf50622a1761156a77ad0d35a2007f6`). No production
model, ranking, or probability code was touched. Everything below is new,
additive infrastructure plus a read-only validation pass.

## 1. Architecture

Three new files, all additive, none touching existing production code:

| File | Role |
|---|---|
| `apex_sa365_perset_capture.py` | Storage layer. Reuses `apex_settle_sa365.find_event`/`stat_sheet` as-is (same rate limiting, same on-disk sheet cache) — never re-implements API logic. Flattens the full `statistics` payload (all set buckets, not just `ALL`) into rows and writes them to SQLite. |
| `apex_sa365_backfill.py` | Backfill driver. Reads every unique `(player, opponent, match_date)` Apex has actually picked, from `apex_engine_picks_log_v1.csv` — which already carries real `surface`/`best_of` ground truth, so no guessing was needed there. |
| `apex_sa365_coverage_report.py` | Read-only reporting layer for Phases 2-5. Fits nothing; computes coverage/missing %, distributions, and the Bo3/Bo5 post-hoc check. |

### Storage location

`data/apex_sa365_stats_v1.db` (new SQLite file):
- **`captures`** — one row per matched event: `event_id, player1, player2, match_date, tour, surface, best_of, league, status, score, picks_log_category, source (cache|api), fetched_at, note`.
- **`perset_stats`** — one row per `(event_id, side, set_label)` with the Phase 1 fields (`games_won, service_games_total, return_games_total, aces, double_faults, break_points_scored`) plus Phase 2/3 fields (`break_points_saved_*, first/second_serve_acc_*, first/second_serve_pts_*, tiebreaks`).

Raw JSON continues to live at `data/sa365_sheets/{event_id}.json` exactly as
`apex_settle_sa365.py` already wrote it before this project started — the
new pipeline reads that cache rather than duplicating it.

## 2. New stored fields (Phase 1 + 2 + 3)

Per `(event_id, side, set_label)` for every set bucket the API returns
(`1ST`, `2ND`, `3RD`, `4TH`, `5TH`, `ALL`) — not just the match total Apex's
settlement code currently reads:

`games_won, service_games_total, return_games_total, aces, double_faults,
break_points_scored, break_points_saved (value/total/%), first_serve_acc
(value/total/%), second_serve_acc (value/total/%), first_serve_pts_won
(value/total/%), second_serve_pts_won (value/total/%), tiebreaks`

## 3. Backfill run

Ran against all 199 unique matches Apex has ever picked on. **199/199
attempted, 515 seconds, zero script errors.**

| Outcome | Count |
|---|---|
| Matched to a distinct SA365 event | 112 |
| — of those, had a usable statistics sheet | **19** |
| — of those, statistics sheet was empty (API returned `{"success":true,"result":{}}`) | 93 |
| No event found by name+date at all | 23 (includes the already-known Fernandez/Andreeva Sep-25 gap) |

**This is the single most important finding of the backfill, and it's new
information beyond the original field audit:** SA365's per-event
statistics endpoint does not appear to retain detailed stats indefinitely.
Every match from Aug 25 through Sep 9 (93 of the 93 empty results) came
back with a genuinely empty `result: {}` — confirmed directly against the
raw API response, not a bug in this pipeline. Every match from Sep 24-25
(the most recent trading days) came back populated. The practical
implication: **this data source has a retention window, likely on the
order of two to three weeks.** Anyone wanting to build a serve-quality or
per-set calibration feature from this endpoint needs to capture it close
to match time (a daily job, not a one-time historical backfill) or accept
that historical depth here will always be thin.

## 4. Coverage report (Phase 2)

Full machine output in `apex_sa365_coverage_report.json`. Headline numbers:

- **Coverage: 17.0%** of matched events (19/112) had a usable statistics
  sheet, for the reason above.
- **Within those 19 matches, field-level coverage is 100%** — once a
  statistics sheet exists at all, every field this pipeline stores
  (serve accuracy, break-points-saved, per-set breakdown) is populated.
  There is no partial/missing-field problem inside a populated sheet.
- Sample: 17 Hard-court, 2 Clay. **No WTA/ATP split available yet** — the
  picks log doesn't carry a tour column, and I deliberately did not infer
  gender from player names to fill that gap (would be guessing, not
  evidence). If a tour split is wanted, the fix is upstream: have
  whichever code writes `apex_engine_picks_log_v1.csv` also write the
  `tourType` field SA365 already returns on the fixture lookup, rather
  than reconstructing it after the fact.
- First-serve-accuracy distribution (n=38 player-match rows): mean
  64.5%, std 10.6, range 40-81%. Clay mean 72% vs. Hard 63.6% — directionally
  sensible (clay rallies favor consistent, higher-percentage first
  serves) but n=2 matches on clay, so this is a data point, not a finding.

## 5. Break-points-saved vs. existing breaks settlement (Phase 3)

Question asked: does `breakPointsSaved` carry information not already
captured by Apex's current `breaks` settlement (which uses
`breakPointsScored`)?

**Evidence: yes, they are different signals.** Correlation between a
player's break-points-saved % and their break-points-scored count across
the 19-match sample: **-0.025** — indistinguishable from zero. This is
expected once you separate what each stat measures:
`breakPointsScored` is offensive (break points I converted against my
opponent's serve); `breakPointsSaved` is defensive (break points saved on
my own serve). Apex's `breaks` category settles and is scored on the
offensive side only. The defensive side is a genuinely separate axis Apex
has never looked at. **Caveat: n=19 is a real sample but a small one** —
this is directional evidence, not a settled statistical result.

## 6. Per-set match-length study (Phase 4)

- Set-count distribution across the 19 matches with data: 12 two-setters,
  7 three-setters. **Zero four- or five-setters** — every match in the
  usable window (Sep 24-25) was a best_of=3 event; the real historical
  Bo5 matches in the picks log (the Aug 30/31 and Sep 5 Slam rows) all
  fell inside the empty-statistics window and could not be captured.
  **This means Phase 4/5's match-length and Bo5 analysis currently has
  zero Bo5 examples to work with** — a direct consequence of the
  retention-window finding in Section 3, not a modeling limitation.
- Average total games per set: 9.3 (Hard) vs. 8.75 (Clay), n too small to
  read into.
- Tiebreak frequency: 3.7% of sets on Hard, 0% on Clay (n=2 Clay matches —
  not a real base rate, just what happened to occur).
- **Does per-set information explain remaining games_won/breaks/aces
  calibration issues?** Not answerable yet with n=19 and zero Bo5
  coverage. The pipeline is built and validated; this question needs the
  daily-capture job (Section 8) to run for several weeks before there's
  enough data to say anything defensible.

## 7. Bo3/Bo5 ground-truth investigation (Phase 5)

**Can best-of format be reliably inferred from the match itself?**
Mechanically, yes — for a match with per-set data, the highest set label
present that isn't `ALL` tells you how many sets were actually played,
which is ground truth for a post-hoc check. This pipeline runs that check:
zero of the 19 matches contradicted their `best_of` label (no `best_of=3`
match reached a 4th or 5th set). But this is **not a fix for the
pre-match problem**: per-set data only exists after a match finishes, so
it cannot supply a format field before the match starts, which is when
Apex needs it for pricing.

**No source of ground-truth pre-match Bo3/Bo5 has been found anywhere in
SA365's endpoints** (upcoming, live, event/get, or the statistics
endpoint) across this audit and the earlier field audit. `apex_price_feed
.fixture_context()`'s format inference (WTA/non-Slam-ATP hardcoded Bo3,
Slam matches inferred from the Bet365 total-games odds line or a
hardcoded Slam calendar) remains the only mechanism Apex has, and this
investigation did not surface anything that closes that gap. **If a
ground-truth Bo3/Bo5 field is wanted, the honest next step is checking
whether it exists on a completely different data source** (a tournament
draw sheet, an official ATP/WTA schedule feed, or a provider that
publishes format explicitly) — not further mining SA365, which does not
appear to carry it under any endpoint reached this session.

## 8. Recommended future model opportunities (not built — evidence only)

In priority order, now backed by real (if thin) data rather than just the
field audit's reasoning:

1. **Stand up a daily capture job** (not backfill) that calls
   `apex_sa365_perset_capture.capture_one()` for each day's settled
   matches shortly after they finish, before the retention window closes.
   This is the highest-leverage next step — every other opportunity below
   depends on having more than 19 matches of data.
2. **Serve-quality features for aces/dfs/games_won calibration**
   (`firstServeAccuracy`, `secondServeAccuracy`) — directionally sensible
   in the n=19 sample, needs volume before fitting anything.
3. **`breakPointsSaved` as a second, independent signal for the `breaks`
   category** — confirmed non-redundant with the existing
   `breakPointsScored` signal; worth adding as a cross-check once volume
   allows a real correlation study against settlement outcomes, not just
   against the other stat.
4. **Per-set (not just match-total) breakdown for a fatigue/set-trend
   study** — infrastructure exists, but zero examples currently reach a
   3rd set with a documented decline profile large enough to say
   anything; needs volume.
5. **Bo5 match-length study is currently blocked**, not by anything this
   pipeline could have done differently, but by the retention-window
   finding: no Bo5 match has usable per-set data yet. This will resolve
   itself once the daily capture job (item 1) has run through a Slam or
   another Bo5 tournament while still inside the retention window.

## Bottom line

The pipeline works end-to-end: real backfill, real storage, real
validation, zero production changes. The most valuable output of this
build isn't a model opportunity — it's the discovery that **this data
source has a retention window of roughly two to three weeks**, which
means every future opportunity identified in the field audit depends on
capturing data close to match time rather than backfilling historical
matches. That's the next piece of infrastructure to build, if you want to
keep going: a daily (not one-time) capture job.


## 9. Phase 6 — Daily capture job

Three new files, additive, no production files touched:

| File | Role |
|---|---|
| `apex_sa365_daily_capture.py` | Daily driver. Captures every match Apex picked on for a given settled day (default: yesterday; `--date` overrides for testing/manual runs). Reuses `apex_sa365_perset_capture.capture_one()` unchanged. |
| `openclaw_jobs/apex_sa365_daily_capture.sh` | launchd wrapper (`cd .../openclaw && python3 apex_sa365_daily_capture.py`), already `chmod +x`'d. |
| `apex_sa365_7day_validation.py` | Reads the DB + run log and reports coverage by tour/format/surface for any `--since` window (defaults to trailing 7 days). |

**Scope decision, stated plainly:** "every completed match" is scoped here
to matches Apex actually produced a pick on (via `apex_engine_picks_log_v1.csv`
for the target date) — the same universe Phase 1's backfill used, just a
rolling 24h window. There is no broader "every ATP/WTA match that finished
yesterday" enumeration available from any SA365 endpoint reached this
session (no historical results-list endpoint was found in the field
audit), so scanning beyond Apex's own pick universe would mean guessing at
match names from somewhere else. If a broader scan is wanted later, it
needs a different discovery source first — this is a real limitation,
not an oversight.

**One capture-quality fix landed alongside this (small, additive, not a
new file):** `apex_sa365_perset_capture.capture_one()` previously left
`tour` blank because the picks log carries no tour column. The event
record SA365 already returns carries `tourType` (atp/wta) directly — this
was sitting unused. `capture_one()` now fills `tour` from `ev.get("tourType")`
whenever the caller doesn't supply one, which finally closes the "no
ATP/WTA split available" gap flagged in Phase 2's coverage report. This
only affects newly-captured or re-captured rows going forward; the 110
rows captured during the original Phase 1 backfill still show `tour` as
unknown unless a match happens to get re-captured by the daily job later
(re-running the full historical backfill just to backfill this one column
was judged not worth another ~110 API round trips for a nice-to-have).

### Logging

Every run appends one line to `apex_sa365_daily_capture_log.jsonl`
(machine-readable: `attempted, new_captures, duplicates, empty, missing,
error, elapsed_sec`) and a human-readable block to
`apex_sa365_daily_capture.log`. "Duplicate" means the match's underlying
event_id already had a captures row before this run (tracked via a new
`was_duplicate` return value on `capture_one()`) — this distinguishes
"the job ran twice over the same day" from "genuinely new data," which
matters once the job is running unattended daily.

**Tested end-to-end, both paths:**
- `python3 apex_sa365_daily_capture.py` (no args, defaults to "yesterday" =
  2026-09-26): correctly reported zero picks-log rows for that date and
  logged a clean empty-day entry — there was no real Apex trading on
  2026-09-26, so this is the correct, honest result, not a bug.
- `python3 apex_sa365_daily_capture.py --date 2026-09-24`: correctly
  re-found all 4 picks-log rows for that date, matched them to 2 underlying
  events (each match appears twice, once per player's row), and logged
  them as duplicates against the existing Phase 1 backfill data —
  `{'attempted': 4, 'new_captures': 0, 'duplicates': 4, 'empty': 0,
  'missing': 0, 'error': 0}`.

### Scheduling — needs your action

Exactly as with the forward-tracking job earlier this session, **I
cannot create or read a new file under `~/Library/LaunchAgents/` from
here** — that's a hard, standing block (Claude Code's own safety
classifier: "Unauthorized Persistence"), not a judgment call, and I'm not
attempting a workaround. The wrapper script above is ready; you need to
save the plist yourself and load it:

1. Save this as `~/Library/LaunchAgents/com.apex.sa365dailycapture.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.apex.sa365dailycapture</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>/path/to/home/openclaw_jobs/apex_sa365_daily_capture.sh</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>6</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>/path/to/home/openclaw_jobs/apex_sa365_daily_capture.stdout.log</string>
    <key>StandardErrorPath</key>
    <string>/path/to/home/openclaw_jobs/apex_sa365_daily_capture.stderr.log</string>
</dict>
</plist>
```

   (6:00 AM local was picked so it runs comfortably after any overnight
   matches settle and well inside the retention window; change the
   `Hour`/`Minute` if you want a different time.)

2. Load it:
```
launchctl load ~/Library/LaunchAgents/com.apex.sa365dailycapture.plist
```

3. Verify it's scheduled:
```
launchctl list | grep sa365dailycapture
```

### Validation, after 7 days

Run `python3 apex_sa365_7day_validation.py` (optionally `--since
YYYY-MM-DD` for a custom window). It reports total matches captured, ATP
coverage, WTA coverage, Bo3 coverage, Bo5 coverage, surface coverage, and
the daily-job run totals — and explicitly flags if fewer than 7 daily
runs are in the log yet, so you know if you're reading it too early. Ran
it now, against the current (pre-daily-job) data, to confirm it works:
correctly reported only 2 runs logged so far and surfaced the caveat.
Real numbers will fill in once the job has been running daily.

## Bottom line, updated

The full pipeline — capture, backfill, coverage, validation, and now a
daily job — is built, tested, and running clean. The two things still
outside my reach from here, both by design (not oversight): the launchd
plist needs you to save and load it (Section 9), and the daily job's
scope is Apex's own pick universe rather than all of tennis (a real,
stated limitation, not a shortcut). Everything else — storage, parsing,
dedup, logging, and reporting — is done and already validated against
real data.
