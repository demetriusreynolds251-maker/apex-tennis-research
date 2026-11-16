# DEMETRIUS — Calibration Notes & Research Reference

Purpose: this file is separate from `weights.json` (which holds
tunable numbers) and separate from the master prompt (which holds
live evaluation rules the model follows). This file documents WHY a
provisional decision was made, what real outside research says about
it, and what would need to change before revisiting it. Nothing in
here is a live rule the evaluation model reads — it's a reference for
you and future sessions to understand the reasoning behind a call
that isn't backed by our own live data yet.

Every claim below is sourced. No numbers are invented or estimated
without a citation.

================================================================

## HOME-COURT ADVANTAGE (Moneyline Gate 14)

**Current implementation (v7.9.6):** Gate 14 for moneyline applies a
small directional lean toward the home player, only when the match
is classified COMPETITIVE (Step 5), and never overrides a confirmed
HARD dominance call for the away player.

**Why this conservative design was chosen:** at the time this was
built, no per-player home/away split data existed anywhere in the
system. A flat, small, competitive-only lean was chosen specifically
to avoid overweighting a narrative-adjacent factor, consistent with
Rule 9 (market/narrative influence never overrides confirmed
structural facts) — while still acknowledging that home advantage is
a real, researched phenomenon, not something to ignore entirely.

**What real outside research says (checked July 2026):**

- Home advantage in tennis is statistically real but consistently
  smaller than in team sports. Research into the topic has produced
  mixed results overall, but points toward a smaller effect than
  team sports show.
  Source: Tennisnerd.net, "Crowd Influence in Tennis, Is There a
  Home Advantage?", citing a 2011 study by Koning.

- A large-scale analysis of 287,918 ATP tour and Challenger singles
  matches since 2000 found home advantage increases a player's win
  probability by roughly 10% on average, all else being equal. This
  used logistic regression on ATP data only — WTA was not covered.
  Source: Medium, "Quantifying home advantage in tennis" (data
  scientist / PhD candidate analysis, not a peer-reviewed journal —
  treat as a serious independent analysis, not formal academic
  literature).

- The SAME analysis found the effect size varies substantially by
  individual player. Bernard Tomic was found to be over four times
  more likely to win at home than away, all else equal. Alex De
  Minaur showed nearly a 3x effect. Players from Australia and the
  USA showed the biggest home-advantage effects in this analysis.
  Source: same Medium analysis as above.

- A separate, more formally structured study independently confirms
  the underlying effect: the probability of winning an ATP match is
  higher when a player competes in their own country, all else
  being equal, based on ATP-level tournament data from 2000-2022.
  Source: ScienceDirect, "Individual performance and environment:
  Home advantage in ATP tennis."

- The COVID-era crowdless-tournament period offers a natural
  experiment. ATP results during that window showed no drastic
  shift — top seeds continued to dominate much as before — which
  suggests the effect may lean more on travel/familiarity than on
  crowd noise specifically.
  Source: Tennisnerd.net (same article as above).

- Research on home advantage specifically in WOMEN'S tennis is
  described as less conclusive than the men's-tour findings.
  Source: ResearchGate citation of Koning (2011), referenced via
  Tennisnerd.net.

**Status: PROVISIONAL.** The current flat, conservative Gate 14 rule
remains the live behavior. It is a reasonable, research-backed
starting point — "small and real" matches what the outside research
says about the AVERAGE player — but it is known to be leaving real
signal on the table, since research clearly shows some players (like
the Tomic/De Minaur pattern above) have a meaningfully larger home
effect than others, while Gate 14 currently treats every player
identically.

**What would change this:** a per-player home/away split, built from
our OWN live data (see below), reaching a minimum sample size for a
given player. Once available, Gate 14 could move from a flat lean to
a per-player-calibrated lean — bigger for players who show a real,
demonstrated home effect, smaller or none for players who don't.

================================================================

## PER-PLAYER HOME/AWAY WIN RATE (new, accumulating from v7.9.6 on)

Built starting v7.9.6 in `openclaw_v8_api.py`, accumulated
automatically every time `get_recent_matches()` processes a match
with a VERIFIED winner (not counted if W/L is unconfirmed) and both
the player's and tournament's country codes are available.

This sidesteps any third-party dataset licensing question entirely —
it's aggregated from results pulled through your own paid API
subscription over time, the same calls the system already makes for
other purposes, not a bulk download of someone else's compiled or
licensed dataset.

**Minimum sample discipline:** do not act on a player's home/away
split until at least 5 home AND 5 away verified results exist for
that player, matching the minimum-sample discipline already used
elsewhere in this system (MIN_PROPOSAL_SAMPLE). Below that, the
split is real but too thin to trust — same "unconfirmed is not
assumed neutral" standard used everywhere else.

Stored in `data/learning/home_away_splits.json`. Starts empty — no
backfilled or estimated history, only real matches processed by the
system going forward.

================================================================

## DATA GAPS — FULL SYSTEM AUDIT (as of v7.9.6 moneyline build)

Reviewed across the whole system, prop and moneyline, what's
confirmed available versus genuinely missing:

**Confirmed available and already integrated:** hold%, break%, BP
save%, aces, first-serve%, surface record (season + 5yr), recent
match results with verified W/L, ranking, tournament tier/round,
player/tournament country codes. H2H is implemented but pending a
vendor-side endpoint fix as of this writing.

**Missing — no source integrated:**

- Match duration (minutes). Not confirmed present anywhere in the
  real V8 API responses pulled so far. This blocks a precise fatigue
  signal — currently approximated only via "went the distance" and
  turnaround time between matches, not actual match length. Worth a
  direct follow-up question to the API vendor.

- Injury/withdrawal reports. No data source integrated at all. Any
  physical-state signal beyond schedule-based fatigue inference
  would need a new vendor or data source.

- Indoor vs. outdoor hard court distinction. Currently only
  grass/clay/hard is tracked; indoor and outdoor hard courts play
  meaningfully differently in practice, and are currently blended
  together under a single "hard" surface bucket.

- Doubles-same-day fatigue. Not tracked. A real factor for players
  who compete in both singles and doubles at the same event on the
  same day.

**Now being built (this file, this session):** per-player home/away
win rate, accumulated from live data going forward.

================================================================
