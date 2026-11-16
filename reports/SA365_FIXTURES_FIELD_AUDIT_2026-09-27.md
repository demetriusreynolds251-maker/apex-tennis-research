# SportsAPI365 Fixtures/Event Field Audit — 2026-09-27

**Scope:** read-only. No production files touched. All findings below come from
live API calls made through the already-imported `apex_price_feed` /
`apex_settle_sa365` helpers, plus `grep`/source-reading of how Apex actually
consumes the responses today. Nothing was invented; where a field could not be
confirmed to exist, that is stated explicitly rather than guessed.

## Endpoints actually reachable this session

| # | Endpoint | Used by Apex today | What it returned live |
|---|---|---|---|
| A | `/extend/api/events/upcoming/{tour}?page=N` | `apex_price_feed._fetch_upcoming` | 50 ATP fixtures, minimal fields |
| B | `/extend/api/events/live` | `apex_price_feed._fetch_live` | 1 live match, 3 extra fields vs. A |
| C | `/extend/api/event/get/{p1}/{p2}/{date}` | `apex_settle_sa365.find_event` | richer single-event record (score, lightweight stats, timeline) |
| D | `/extend/api/event/get/statistics/{event_id}` | `apex_settle_sa365.stat_sheet` / `value_for` | full per-set + match-total stat sheet — **this is what Apex actually settles aces/dfs/breaks/fantasy_score from today** |

Confirmed empirically: endpoint A **ignores** `include=` query parameters
entirely (tested with `include=round,tournament.court,tournament.rank,tournament.country,h2h,odds`
appended — identical response, no new keys). No round / tournament-rank /
tournament-court / tournament-country / h2h field was found on **any** of the
four endpoints above. That data may exist under a route this account/key
doesn't reach, or may not be exposed by this feed at all — I did not find it,
so it is not counted as available below.

## Field-by-field audit

### Endpoint A/B — fixture listings (upcoming, live)

| Field | Apex has it? | Better source exists? | Model value | Impl. cost |
|---|---|---|---|---|
| `id`, `matchId` | Yes (`fixture_context`) | — | — (plumbing) | — |
| `participant1/2`, `player1.name`, `player2.name` | Yes | — | — (plumbing) | — |
| `league`, `tournament.name` | Yes (`fixture_context`) | — | — (plumbing) | — |
| `tourType` (atp/wta) | Yes (drives the upcoming-endpoint `tour` param and WTA-always-Bo3 branch) | — | — (already fully used) | — |
| `startTimestamp` | Yes | — | — (plumbing) | — |
| `status` (NotStarted/InPlay/Ended/Cancelled/Walkover/Retired) | Partially — `apex_settle_sa365.match_flag()` uses it fully for settlement gating; `fixture_context()` only checks `started` | Already Apex's primary settlement-quality mechanism | Already fully exploited where it matters (settlement) | — |
| `score` (live only, e.g. "3-6,3-6") | Yes — this is the **entire basis** of `games_won`/`total_sets`/`total_games`/`tiebreaks`/`goes_3/5_sets` settlement via `parse_sets()` | — | Already fully exploited | — |
| `points` (live game score, e.g. "15-30") | No | N/A — only meaningful in-play, and Apex is not an in-play system today | LOW (out of current scope) | LOW if ever built |
| `indicator` (live server pointer) | No | N/A, same as above | LOW | LOW |

### Endpoint C — single-event lookup (`event/get`)

| Field | Apex has it? | Better source? | Model value | Impl. cost |
|---|---|---|---|---|
| `stats.aces` / `stats.double_faults` (2-element arrays) | No, but **redundant**: endpoint D's `statistics.ALL.service.aces/doubleFaults` is already what Apex settles from, and is more granular (per-set too) | **Yes — Apex already has a better source (endpoint D)** | LOW (duplicate, lower resolution) | N/A — not worth building |
| `stats.win_1st_serve` (2-element, %) | No | No — nothing currently uses first-serve % at all | **MEDIUM-HIGH** (see endpoint D `firstServeAccuracy`, same data, better source) | superseded by D |
| `stats.break_point_conversions` (2-element, %) | No | Endpoint D has the raw counts (`return.breakPointsScored`) Apex already parses; this is just the derived % | LOW (duplicate) | N/A |
| `timeline` (game-by-game "holds/breaks to X" text log) | No — 100% unused anywhere in the codebase | No equivalent structured source | MEDIUM — could support an independent RET/walkover sanity check (does the log stop mid-set exactly where `score` implies a retirement?) and game-count pacing for match-length modeling | MEDIUM — text parsing of natural-language strings is fragier than the structured JSON in D; would need a small parser + tests |

### Endpoint D — per-event statistics sheet (already integrated, but only partly used)

Apex calls this endpoint for every settlement already. It returns a
per-set breakdown (`"1ST"`, `"2ND"`, …) **and** a match-total bucket
(`"ALL"`) — today's code (`apex_settle_sa365.value_for`) reads **only**
`ALL`, and only four leaves inside it:
`games.gamesWon`, `service.aces`, `service.doubleFaults`,
`return.breakPointsScored`. Everything else in the same already-fetched
payload is currently discarded.

| Field (all under `statistics.ALL.*` unless noted) | Apex has it? | Better source? | Model value | Impl. cost |
|---|---|---|---|---|
| `games.gamesWon` | Yes (cross-check against `score`) | — | already used | — |
| `service.aces`, `service.doubleFaults` | Yes | — | already used | — |
| `return.breakPointsScored` | Yes | — | already used (with a serve-parity sanity check) | — |
| `service.breakPointsSaved` (total/value/%) | **No** — the defensive complement to `breakPointsScored`, never read | No | **HIGH** — direct hold/break calibration signal; a natural second cross-check on the `breaks` category (today's only cross-check is the serve-parity arithmetic check, not an independent stat) | **LOW** — same payload already in hand, same shape as fields already parsed |
| `service.firstServeAccuracy`, `secondServeAccuracy`, `firstServePointsAccuracy`, `secondServePointsAccuracy` | **No** | No | **MEDIUM-HIGH** — serve-quality signal that feeds directly into aces/dfs/games_won calibration, and into a match-length ("how fast do these sets go") estimator via serve dominance — this is the single biggest already-fetched, zero-cost, currently-wasted signal found in this audit | **LOW** — same payload |
| `return.firstReturnPoints`, `secondReturnPoints` (total/value/%) | **No** | No | **MEDIUM** — return-quality complement to the serve stats above; useful for WTA specifically, where return games are proportionally more break-prone than ATP and current models have thinner WTA coverage per the pre-flight audit | LOW |
| `service.serviceGamesTotal`, `return.returnGamesTotal` (per player) | **No** | Partially redundant with `g1,g2` derived from `score`, but per-set split is new | **MEDIUM** — an independent games-count cross-check plus Bo5 set-by-set pacing | LOW |
| **Per-set breakdown itself** (`"1ST"`, `"2ND"`, `"3RD"`… vs. only `"ALL"`) | **No** — Apex discards set-level granularity entirely today | No | **HIGH** — this is the fields above, but split by set instead of collapsed to a match total. Directly enables: (a) calibration — does a category's rate change set-to-set (fatigue, adjustment)? (b) **match-length estimation** — a 3rd/4th/5th set's serve stats predict whether it goes the distance; (c) **Bo5** — the only format where "does this settle in 3, or run to 5" materially changes exposure, and set-by-set trend is the most direct signal for it | **LOW-MEDIUM** — same API call already made per settlement; the change is reading more keys out of a JSON object that's already sitting in memory, not a new fetch |
| `games.maxGamesInRow`, `points.maxPointsInRow`, `points.servicePointsScored`, `points.receiverPointsScored` | No | No | **LOW** — momentum/streakiness features. Explicitly the kind of generic player-strength/form signal the brief said to de-prioritize relative to calibration/settlement/Bo5/WTA/match-length | LOW |
| `miscellaneous.tiebreaks` (per set) | Partially — Apex already gets a tiebreak **count** from `parse_sets(score)`; this field would only add which specific set(s) had one | LOW — the count Apex has today already answers the `tiebreaks`/`any_tiebreak` categories | LOW | LOW |

## Top-10 ranked opportunities (value ÷ cost)

Ranked by expected predictive/settlement value against how cheap the change
is — all of these read fields from **payloads Apex is already fetching**
(endpoint D, once per settlement), so "cost" here is purely about touching
`apex_settle_sa365.py` / a downstream calibration script, not about new API
calls or new API budget.

| Rank | Field / change | Why it ranks here | Cost |
|---|---|---|---|
| 1 | Split existing `ALL`-only parsing into **per-set** (`1ST`/`2ND`/…) reads | Highest value-weighted item for the brief's exact focus list: calibration (set-to-set rate drift), match-length estimation, and Bo5 (does it go 5?) all come from the same unlock | Low |
| 2 | `service.firstServeAccuracy` / `secondServeAccuracy` (+ the points-accuracy variants) | Zero-cost, currently-wasted serve-quality signal feeding aces/dfs/games_won calibration and match-length pacing | Low |
| 3 | `service.breakPointsSaved` | Independent defensive stat to cross-check the `breaks` category, which today only has an arithmetic parity check, not a second data source | Low |
| 4 | Per-set `service.serviceGamesTotal` / `return.returnGamesTotal` | Independent games-count cross-check + Bo5 set-by-set pacing | Low |
| 5 | `return.firstReturnPoints` / `secondReturnPoints` | Return-quality signal, disproportionately useful for **WTA** (thinner model coverage, more return-driven breaks per the pre-flight audit) | Low |
| 6 | `timeline` (endpoint C) as a RET/walkover sanity check | Could catch a `score`-string edge case (mid-set retirement) that `match_flag()` alone might misread; independent verification improves settlement quality | Medium (text parsing) |
| 7 | `timeline` for game-count pacing / match-length modeling | Same field, a research use rather than a settlement-quality use — lower priority than #6 because it's exploratory, not a correctness fix | Medium |
| 8 | `miscellaneous.tiebreaks` per-set location | Minor — Apex already has the tiebreak count; this only adds *which* set | Low |
| 9 | `games.maxGamesInRow` / `points.maxPointsInRow` / point-scored counts | Momentum features — explicitly the generic-strength category the brief said to de-emphasize | Low (but low value too) |
| 10 | Live-only `points` / `indicator` fields | Only relevant if Apex ever adds in-play pricing, which it does not do today | Low cost, but out of current scope |

**Not on the list / explicitly not found:** `round`, `tournament.rank`,
`tournament.court`, `tournament.country`, `h2h` — requested via `include=`
on the upcoming endpoint (ignored) and searched for on the live and
per-event endpoints (absent). No opportunity can be scored for a field that
was not observed to exist.

**One gap this audit does *not* close, worth restating plainly:** none of
the four endpoints checked expose a direct "best of 3 / best of 5" field.
`apex_price_feed.fixture_context()`'s Bo5 detection is still 100% inference
(WTA hardcoded Bo3, non-Slam ATP hardcoded Bo3, Slam matches inferred from
the Bet365 total-games odds line or a hardcoded Slam calendar). Item #1 above
(per-set stat access) improves calibration and match-length estimation
*within* whatever format is already assumed, but it does not give Apex a
ground-truth format field. That remains the single largest structural gap
in the Bo5 pipeline, flagged in the 2026-09-27 pre-flight audit and
unchanged by this endpoint audit.

## Bottom line

Apex's biggest near-term opportunity here isn't a new field to fetch — it's
that the richest payload (`event/get/statistics`) is **already being pulled
for every settlement** and roughly 70% of its keys are read once (`ALL`)
and thrown away, including a full per-set breakdown of exactly the signals
(serve accuracy, break points saved, return points) most relevant to
calibration, Bo5 pacing, and WTA-specific coverage. No new API surface,
no new cost budget — just reading more of what's already in hand.
