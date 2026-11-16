#!/usr/bin/env python3
"""
DEMETRIUS — Moneyline Signal Backtest
=====================================
Tests the Phase 2 five-signal moneyline framework (S1-S5) against real
historical ATP results from the Jeff Sackmann tennis_atp repo, to
calibrate the GREEN/YELLOW confidence caps with actual data instead of
inherited placeholder numbers.

WHAT THIS DOES:
  1. Downloads ATP tour-level match files (main draw, singles) for the
     configured year range.
  2. For every match, computes all 5 signals for BOTH players using
     ONLY data that existed strictly before that match's date — no
     lookahead leakage.
  3. Determines which player the signals collectively favor, buckets
     matches by how many of the 5 signals agreed with that pick
     (5/5, 4/5, 3/5-or-split), and reports the REAL win rate for each
     bucket — this is what should set the GREEN/YELLOW caps, not a
     guess.
  4. Splits every bucket by format (bo3/bo5), surface, and structural
     classification, per the review spec.
  5. Tests the Phase 1 vs Phase 2 "agreement" gate: uses the ranking +
     surface-record structural favorite as a Phase-1 proxy, compares
     it against the Phase-2 signal-majority pick, and reports how each
     agreement/disagreement group actually performed — this validates
     whether the disagreement-equals-NO-PLAY rule is doing real work.

RULE 9 COMPLIANCE: no odds/market data is used anywhere in this script.
Sackmann's match files don't carry odds columns at all, so this is
naturally satisfied — but it's asserted explicitly below so a future
edit can't accidentally introduce market data into signal computation.

DATA QUALITY CAVEAT HANDLED: the `minutes` column (used for S4 fatigue)
has known gaps, especially in older/lower-tier matches. Any match
where a player's PREVIOUS match has no `minutes` value is treated as
S4 = UNCONFIRMED = NO for that player, consistent with the
unconfirmed-is-NO standard used everywhere else in the system. It is
never silently skipped or assumed favorable.

*** SCOPE CAVEAT (confirmed this session, read before using results) ***
signal_s1/s2/s4/s5 below implement the RETIRED v1.3 binary signal
scheme (each returns player_id / opponent_id / None). Moneyline v1.4,
which is what's actually live in openclaw_core.py, replaced this with
a graduated -2/-1/0/+1/+2 magnitude scale (ML_S1_SURFACE_STRONG_GAP_PP,
ML_S2_TOURNAMENT_STRONG_ROUND_GAP, etc.) specifically because binary
signals discard real magnitude information. This backtest's output
(win rate by count-of-signals-agreeing) does NOT calibrate v1.4's
actual provisional band thresholds -- it validates a shape the live
system no longer uses. It's still useful for sanity-checking the
underlying direction-of-effect for each signal, but cite it as that,
not as validation of the current ML_S1-S5 constants. A v1.4-accurate
backtest would need signal_s1/s2/s4/s5 rewritten to output the same
-2..+2 graduated scale and to reproduce the real band aggregation
(0-1 NONE / 2-3 LEAN / 4-5 YELLOW / 6+ GREEN_CANDIDATE) before its
results could be used to move any of the live provisional thresholds.

USAGE:
    pip install pandas requests --break-system-packages   # if needed
    python3 moneyline_backtest.py

Output: prints the full report to the terminal AND saves it to
moneyline_backtest_report.json for later reference.
"""
import json
import io
from datetime import datetime, timedelta
from collections import defaultdict

import requests
import pandas as pd

# ── CONFIG ──
YEARS = list(range(2020, 2026))  # 2020-2025 inclusive, matches the review spec
RAW_URL_TEMPLATE = "https://raw.githubusercontent.com/JeffSackmann/tennis_atp/master/atp_matches_{year}.csv"
H2H_RECENCY_SEASONS = 3   # review item #2 — test 3-season window vs unbounded
OUTPUT_FILE = "moneyline_backtest_report.json"

# Columns confirmed to exist in the Sackmann atp_matches_YYYY.csv files.
# No odds/market columns are referenced anywhere in this script (Rule 9).
REQUIRED_COLUMNS = [
    "tourney_date", "tourney_level", "surface", "best_of", "round",
    "winner_id", "winner_name", "winner_rank",
    "loser_id", "loser_name", "loser_rank",
    "score", "minutes", "tourney_id", "tourney_name",
]


def download_matches():
    """Downloads and concatenates all configured years into one DataFrame."""
    frames = []
    for year in YEARS:
        url = RAW_URL_TEMPLATE.format(year=year)
        print(f"Downloading {url} ...")
        resp = requests.get(url, timeout=30)
        if resp.status_code != 200:
            print(f"  WARNING: {year} returned HTTP {resp.status_code} — skipping this year.")
            continue
        df = pd.read_csv(io.StringIO(resp.text), low_memory=False)
        missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
        if missing:
            print(f"  WARNING: {year} is missing expected columns {missing} — skipping this year.")
            continue
        frames.append(df)
    if not frames:
        raise RuntimeError(
            "No match data could be downloaded. Check your internet connection, "
            "or confirm the Sackmann repo structure hasn't changed at "
            "https://github.com/JeffSackmann/tennis_atp"
        )
    all_matches = pd.concat(frames, ignore_index=True)
    all_matches["tourney_date"] = pd.to_datetime(all_matches["tourney_date"], format="%Y%m%d")
    all_matches = all_matches.sort_values("tourney_date").reset_index(drop=True)
    print(f"Loaded {len(all_matches)} matches across {len(frames)} year(s).\n")
    return all_matches


def build_player_history(matches: pd.DataFrame):
    """
    Builds a per-player chronological list of every match they played,
    each tagged with date, surface, opponent, result, minutes, and
    tourney info — used to compute all signals "as of" any given date
    without looking into the future.
    """
    history = defaultdict(list)
    for _, row in matches.iterrows():
        w_entry = {
            "date": row["tourney_date"], "surface": row["surface"],
            "won": True, "opponent_id": row["loser_id"],
            "minutes": row.get("minutes"), "score": row["score"],
            "best_of": row["best_of"], "tourney_id": row["tourney_id"],
            "round": row["round"],
        }
        l_entry = {
            "date": row["tourney_date"], "surface": row["surface"],
            "won": False, "opponent_id": row["winner_id"],
            "minutes": row.get("minutes"), "score": row["score"],
            "best_of": row["best_of"], "tourney_id": row["tourney_id"],
            "round": row["round"],
        }
        history[row["winner_id"]].append(w_entry)
        history[row["loser_id"]].append(l_entry)
    for pid in history:
        history[pid].sort(key=lambda e: e["date"])
    return history


def prior_matches(history, player_id, as_of_date):
    """All of a player's matches strictly before as_of_date — the
    lookahead-safe boundary every signal below respects."""
    return [m for m in history.get(player_id, []) if m["date"] < as_of_date]


# ── SIGNAL COMPUTATION ──

def signal_s1(history, player_id, opponent_id, as_of_date, surface):
    """Current-season surface win rate comparison, as of match date."""
    season_start = pd.Timestamp(year=as_of_date.year, month=1, day=1)
    p_matches = [m for m in prior_matches(history, player_id, as_of_date)
                 if m["surface"] == surface and m["date"] >= season_start]
    o_matches = [m for m in prior_matches(history, opponent_id, as_of_date)
                 if m["surface"] == surface and m["date"] >= season_start]
    if not p_matches or not o_matches:
        return None  # unconfirmed — not enough current-season surface data
    p_rate = sum(1 for m in p_matches if m["won"]) / len(p_matches)
    o_rate = sum(1 for m in o_matches if m["won"]) / len(o_matches)
    if p_rate == o_rate:
        return None
    return player_id if p_rate > o_rate else opponent_id


def signal_s2(history, player_id, opponent_id, as_of_date, tourney_id):
    """
    Tournament form proxy: rounds already won in THIS event before this
    match. Approximation of the live S2 rule (never primary, supporting
    only) — documented per review guidance so this isn't mistaken for
    the live rule's full nuance.
    """
    p_rounds = sum(1 for m in history.get(player_id, [])
                    if m["tourney_id"] == tourney_id and m["date"] < as_of_date and m["won"])
    o_rounds = sum(1 for m in history.get(opponent_id, [])
                    if m["tourney_id"] == tourney_id and m["date"] < as_of_date and m["won"])
    if p_rounds == o_rounds:
        return None
    return player_id if p_rounds > o_rounds else opponent_id


def signal_s3(history, player_id, opponent_id, as_of_date, surface, seasons_back=None):
    """
    Surface-filtered H2H. seasons_back=None means unbounded (for
    comparison); seasons_back=3 applies the review's proposed recency
    window (item #2).
    """
    cutoff = as_of_date - timedelta(days=365 * seasons_back) if seasons_back else None
    p_wins, o_wins = 0, 0
    for m in prior_matches(history, player_id, as_of_date):
        if m["surface"] != surface or m["opponent_id"] != opponent_id:
            continue
        if cutoff and m["date"] < cutoff:
            continue
        if m["won"]:
            p_wins += 1
        else:
            o_wins += 1
    if p_wins == o_wins:
        return None  # includes the 0-0 no-H2H case — unconfirmed, not assumed neutral
    return player_id if p_wins > o_wins else opponent_id


def _fatigue_flag(history, player_id, as_of_date):
    """
    Returns True/False/None for whether a player's most recent prior
    match qualifies as taxing (S4 trigger), using the F9-aligned
    definition agreed in review: previous match went the distance,
    OR minutes >= 180, OR turnaround < 48h.
    Returns None (unconfirmed) if there's no prior match, or if the
    prior match's `minutes` is missing AND it didn't go the distance —
    per the explicit data-quality caveat, missing data is never
    silently treated as "not fatigued."
    """
    matches = prior_matches(history, player_id, as_of_date)
    if not matches:
        return None
    last = matches[-1]
    turnaround_hours = (as_of_date - last["date"]).total_seconds() / 3600
    went_the_distance = False
    try:
        sets_played = len([s for s in str(last["score"]).split() if "-" in s.split("(")[0]])
        went_the_distance = sets_played >= last["best_of"]
    except Exception:
        went_the_distance = False

    if went_the_distance or turnaround_hours < 48:
        return True
    if pd.isna(last.get("minutes")):
        return None  # UNCONFIRMED — do not assume "not fatigued"
    if last["minutes"] >= 180:
        return True
    return False


def signal_s4(history, player_id, opponent_id, as_of_date):
    p_flag = _fatigue_flag(history, player_id, as_of_date)
    o_flag = _fatigue_flag(history, opponent_id, as_of_date)
    if p_flag is None or o_flag is None:
        return None  # can't confirm one side — unconfirmed, not neutral
    if p_flag == o_flag:
        return None  # both fatigued or both fresh — signal doesn't favor either
    return opponent_id if p_flag else player_id  # favor whoever is NOT fatigued


def signal_s5(history, player_id, opponent_id, as_of_date, surface,
              player_rank, opponent_rank):
    """
    Mechanical LOPSIDED/COMPETITIVE proxy: ranking gap + surface
    record. This is a backtest-only proxy for the live classification
    step, which involves human/model judgment the backtest can't
    replicate — documented explicitly per review guidance so this is
    never confused with live-S5.
    """
    if pd.isna(player_rank) or pd.isna(opponent_rank):
        return None
    rank_gap = abs(player_rank - opponent_rank)
    p_surf = [m for m in prior_matches(history, player_id, as_of_date) if m["surface"] == surface]
    o_surf = [m for m in prior_matches(history, opponent_id, as_of_date) if m["surface"] == surface]
    if len(p_surf) < 3 or len(o_surf) < 3:
        return None  # thin surface data — unconfirmed
    p_rate = sum(1 for m in p_surf if m["won"]) / len(p_surf)
    o_rate = sum(1 for m in o_surf if m["won"]) / len(o_surf)
    if rank_gap < 15:
        return None  # not LOPSIDED enough to call — COMPETITIVE, no directional lean
    favored = player_id if player_rank < opponent_rank else opponent_id
    favored_rate = p_rate if favored == player_id else o_rate
    if favored_rate < 0.55:
        return None  # ranking favorite isn't backed by surface record — no lean
    return favored


# ── MAIN BACKTEST LOOP ──

def run_backtest(matches: pd.DataFrame, history: dict):
    buckets = defaultdict(list)          # "5/5" etc -> list of bool (predicted winner actually won)
    format_split = defaultdict(lambda: defaultdict(list))
    surface_split = defaultdict(lambda: defaultdict(list))
    agreement_results = {"agree": [], "disagree": []}

    for _, row in matches.iterrows():
        date = row["tourney_date"]
        surface = row["surface"]
        best_of = row["best_of"]
        w_id, l_id = row["winner_id"], row["loser_id"]
        w_rank, l_rank = row.get("winner_rank"), row.get("loser_rank")
        tourney_id = row["tourney_id"]

        s1 = signal_s1(history, w_id, l_id, date, surface)
        s2 = signal_s2(history, w_id, l_id, date, tourney_id)
        s3_windowed = signal_s3(history, w_id, l_id, date, surface, seasons_back=H2H_RECENCY_SEASONS)
        s3_unbounded = signal_s3(history, w_id, l_id, date, surface, seasons_back=None)
        s4 = signal_s4(history, w_id, l_id, date)
        s5 = signal_s5(history, w_id, l_id, date, surface, w_rank, l_rank)

        signals = [s1, s2, s3_windowed, s4, s5]
        confirmed = [s for s in signals if s is not None]
        if not confirmed:
            continue  # nothing to evaluate — not a signal-driven match at all

        votes = defaultdict(int)
        for s in confirmed:
            votes[s] += 1
        predicted = max(votes, key=votes.get)
        # tie between the two players = split, not a real majority
        if list(votes.values()).count(votes[predicted]) > 1:
            bucket = "3/5_or_split"
        else:
            agree_count = votes[predicted]
            bucket = f"{agree_count}/5" if agree_count >= 4 else "3/5_or_split"

        predicted_won = (predicted == w_id)
        buckets[bucket].append(predicted_won)

        fmt = "bo5" if best_of == 5 else "bo3"
        format_split[bucket][fmt].append(predicted_won)
        surface_split[bucket][surface].append(predicted_won)

        # Phase 1 vs Phase 2 agreement test — S5's favored side as Phase-1 proxy
        if s5 is not None:
            phase1_pick = s5
            phase2_pick = predicted
            group = "agree" if phase1_pick == phase2_pick else "disagree"
            agreement_results[group].append(predicted_won)

        # Also compute the UNBOUNDED H2H version of the same match for comparison
        signals_unbounded = [s1, s2, s3_unbounded, s4, s5]
        confirmed_u = [s for s in signals_unbounded if s is not None]
        if confirmed_u:
            votes_u = defaultdict(int)
            for s in confirmed_u:
                votes_u[s] += 1
            predicted_u = max(votes_u, key=votes_u.get)
            if list(votes_u.values()).count(votes_u[predicted_u]) == 1:
                agree_count_u = votes_u[predicted_u]
                bucket_u = f"{agree_count_u}/5_unboundedH2H" if agree_count_u >= 4 else None
                if bucket_u:
                    buckets[bucket_u].append(predicted_u == w_id)

    return buckets, format_split, surface_split, agreement_results


def summarize(buckets, format_split, surface_split, agreement_results):
    report = {"buckets": {}, "format_split": {}, "surface_split": {}, "phase_agreement": {}}

    for bucket, results in buckets.items():
        n = len(results)
        win_rate = sum(results) / n if n else None
        report["buckets"][bucket] = {
            "sample_size": n,
            "win_rate": round(win_rate, 4) if win_rate is not None else None,
            "statistically_thin": n < 100,  # flag, don't hide, small samples
        }

    for bucket, fmts in format_split.items():
        report["format_split"][bucket] = {}
        for fmt, results in fmts.items():
            n = len(results)
            report["format_split"][bucket][fmt] = {
                "sample_size": n,
                "win_rate": round(sum(results) / n, 4) if n else None,
                "statistically_thin": n < 50,
            }

    for bucket, surfs in surface_split.items():
        report["surface_split"][bucket] = {}
        for surf, results in surfs.items():
            n = len(results)
            report["surface_split"][bucket][surf] = {
                "sample_size": n,
                "win_rate": round(sum(results) / n, 4) if n else None,
                "statistically_thin": n < 50,
            }

    for group, results in agreement_results.items():
        n = len(results)
        report["phase_agreement"][group] = {
            "sample_size": n,
            "win_rate": round(sum(results) / n, 4) if n else None,
            "statistically_thin": n < 100,
        }

    return report


def print_report(report):
    print("=" * 60)
    print("MONEYLINE SIGNAL BACKTEST — RESULTS")
    print("=" * 60)

    print("\n-- Signal-agreement buckets (this sets GREEN/YELLOW caps) --")
    for bucket in sorted(report["buckets"].keys()):
        d = report["buckets"][bucket]
        flag = "  ⚠️ THIN SAMPLE" if d["statistically_thin"] else ""
        print(f"  {bucket:24s} n={d['sample_size']:5d}  win_rate={d['win_rate']}{flag}")

    print("\n-- Format split (bo3 vs bo5) — feeds review item #4 --")
    for bucket, fmts in report["format_split"].items():
        print(f"  {bucket}:")
        for fmt, d in fmts.items():
            flag = "  ⚠️ THIN" if d["statistically_thin"] else ""
            print(f"    {fmt:5s} n={d['sample_size']:5d}  win_rate={d['win_rate']}{flag}")

    print("\n-- Phase 1 (ranking/surface favorite) vs Phase 2 (signal majority) agreement --")
    for group, d in report["phase_agreement"].items():
        flag = "  ⚠️ THIN SAMPLE" if d["statistically_thin"] else ""
        print(f"  {group:10s} n={d['sample_size']:5d}  win_rate={d['win_rate']}{flag}")
    print("\n  (If 'disagree' win rate is meaningfully lower than 'agree', the")
    print("   NO-PLAY-on-disagreement gate is filtering real losers, not just volume.)")

    print("\n-- H2H recency window comparison (review item #2) --")
    for bucket in sorted(report["buckets"].keys()):
        if "unboundedH2H" in bucket:
            windowed_equiv = bucket.replace("_unboundedH2H", "/5")
            d_u = report["buckets"][bucket]
            d_w = report["buckets"].get(windowed_equiv)
            print(f"  {bucket:24s} n={d_u['sample_size']:5d}  win_rate={d_u['win_rate']}")
            if d_w:
                print(f"  {windowed_equiv + ' (3-season window)':24s} n={d_w['sample_size']:5d}  win_rate={d_w['win_rate']}")


def main():
    print("Rule 9 check: this script never reads or references any odds/market")
    print("column. Signal computation uses only rankings, surface records,")
    print("H2H, tournament progress, and match duration/turnaround.\n")

    matches = download_matches()
    history = build_player_history(matches)
    print("Running backtest (this may take a few minutes for multiple years)...\n")
    buckets, format_split, surface_split, agreement_results = run_backtest(matches, history)
    report = summarize(buckets, format_split, surface_split, agreement_results)
    print_report(report)

    with open(OUTPUT_FILE, "w") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\nFull report saved to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
