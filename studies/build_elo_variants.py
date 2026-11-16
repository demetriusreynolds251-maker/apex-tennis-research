"""
build_elo_variants.py
2026-08-15 — replays Dataset B once, walk-forward, and writes FIVE ELO
ratings per player as they stood BEFORE each match, so the ingredient
upgrades can be judged on the same scoreboard (build_edge_backtest.py).

Variants (all start at 1500, all reuse elo_calculator.expected_score):
  std        current live ELO: K=32, win/loss only.                     (control)
  welo       Weighted Elo (Angelini et al. 2022): rating move scaled by
             the winner's share of games won -- 6-0 6-0 moves ratings
             more than 7-6 7-6. K=32 * (games_w / games_total) * 2, so
             a 50% games share = standard K, a 100% share = 2x K.
  mov_sets   Kovalchik-style set-margin: K=32 * (1 + 0.5 * (sets_w - sets_l - 1)),
             floored at 0.5K. 2-1 or 3-2 = 1x K, 2-0 = 1.5x, 3-0 = 2x, 3-1 = 1.5x.
  surf       surface-blended: 0.5*overall + 0.5*surface rating (surface
             rating only used once a player has >= 10 matches on it).
  dynk       dynamic K: K=48 for a player's first 30 matches, then 32,
             then 24 after 150; and K=48 again on the first match after
             a layoff of > 180 days (Glicko principle: stale = uncertain).

Reads scores from Dataset B `score` (winner-first "6-4 3-6 7-6(5)" style
is ASSUMED and checked: the share of rows where the winner has >= the
loser's games is printed -- if that is not ~90%+ the orientation
assumption is wrong and welo/mov_sets must not be trusted).

OUTPUT: elo_variants.csv with one row per match (all matches, so it can
be joined to walkforward_rows.csv on match_date+player_a+player_b):
  match_date, player_a, player_b, surface,
  gap_std, gap_welo, gap_mov, gap_surf, gap_dynk,
  matches_a, matches_b, days_since_a, days_since_b, score_ok

USAGE (on the Mini): python3 build_elo_variants.py
"""
import os
import re
import sys
import csv
import sqlite3
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from elo_calculator import expected_score, _normalize_surface, DEFAULT_RATING

WAREHOUSE_PATH = "data/warehouse/tennis_warehouse.sqlite"
OUTPUT_CSV = "elo_variants.csv"
K = 32.0
SURF_MIN_MATCHES = 10
LAYOFF_DAYS = 180

_SET_RE = re.compile(r"^\[?(\d+)-(\d+)(?:\(\d+\))?\]?$")


def parse_score(score):
    """-> (games_w, games_l, sets_w, sets_l, ok). Winner-first assumed.
    Ignores tokens like RET / W/O / DEF; a match tiebreak [10-8] counts as a set."""
    if not score:
        return None, None, None, None, False
    gw = gl = sw = sl = 0
    seen = False
    for tok in str(score).replace(",", " ").split():
        m = _SET_RE.match(tok)
        if not m:
            continue
        a, b = int(m.group(1)), int(m.group(2))
        if tok.startswith("["):
            # match tiebreak: counts as a set, not as games
            sw += a > b; sl += b > a
            seen = True
            continue
        gw += a; gl += b
        sw += a > b; sl += b > a
        seen = True
    if not seen:
        return None, None, None, None, False
    return gw, gl, sw, sl, True


class R:
    __slots__ = ("std", "welo", "mov", "dynk", "surf", "surf_n", "n", "last")
    def __init__(self):
        self.std = self.welo = self.mov = self.dynk = DEFAULT_RATING
        self.surf = {"hard": DEFAULT_RATING, "clay": DEFAULT_RATING, "grass": DEFAULT_RATING}
        self.surf_n = {"hard": 0, "clay": 0, "grass": 0}
        self.n = 0
        self.last = None  # date of last match


def _upd(rw, rl, k):
    e = expected_score(rw, rl)
    return rw + k * (1 - e), rl - k * (1 - e)


def _dyn_k(r: R, today: date):
    if r.last is not None and (today - r.last).days > LAYOFF_DAYS:
        return 48.0
    if r.n < 30:
        return 48.0
    if r.n < 150:
        return 32.0
    return 24.0


def _blend(r: R, s):
    if s and r.surf_n[s] >= SURF_MIN_MATCHES:
        return 0.5 * r.std + 0.5 * r.surf[s]
    return r.std


def run():
    if not os.path.exists(WAREHOUSE_PATH):
        print(f"ERROR: warehouse not found at {WAREHOUSE_PATH}")
        return
    conn = sqlite3.connect(WAREHOUSE_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT player_a, player_b, winner, surface, match_date, score, best_of "
        "FROM matches WHERE winner IS NOT NULL AND match_date IS NOT NULL "
        "ORDER BY match_date ASC"
    ).fetchall()
    conn.close()

    ratings = {}
    out = open(OUTPUT_CSV, "w", newline="")
    w = csv.writer(out)
    w.writerow(["match_date", "player_a", "player_b", "surface",
                "gap_std", "gap_welo", "gap_mov", "gap_surf", "gap_dynk",
                "matches_a", "matches_b", "days_since_a", "days_since_b", "score_ok"])
    n_written = n_score_ok = n_orient_ok = 0
    for row in rows:
        pa, pb, winner, surface, d = row["player_a"], row["player_b"], row["winner"], row["surface"], row["match_date"]
        if winner not in (pa, pb):
            continue
        try:
            today = date.fromisoformat(str(d)[:10])
        except ValueError:
            continue
        s = _normalize_surface(surface)
        ra, rb = ratings.get(pa), ratings.get(pb)

        # ---- pre-match snapshot (state BEFORE this match) ----
        if ra is not None and rb is not None and ra.n > 0 and rb.n > 0:
            w.writerow([d, pa, pb, surface,
                        f"{ra.std - rb.std:.4f}", f"{ra.welo - rb.welo:.4f}", f"{ra.mov - rb.mov:.4f}",
                        f"{_blend(ra, s) - _blend(rb, s):.4f}", f"{ra.dynk - rb.dynk:.4f}",
                        ra.n, rb.n,
                        (today - ra.last).days if ra.last else "", (today - rb.last).days if rb.last else "",
                        1])
            n_written += 1

        # ---- update AFTER using it ----
        loser = pb if winner == pa else pa
        rw = ratings.setdefault(winner, R()); rl = ratings.setdefault(loser, R())
        gw, gl, sw, sl, ok = parse_score(row["score"])
        if ok:
            n_score_ok += 1
            if gw >= gl:
                n_orient_ok += 1
        # std
        rw.std, rl.std = _upd(rw.std, rl.std, K)
        # welo: K scaled by winner's games share (0.5 share = K, 1.0 share = 2K)
        share = (gw / (gw + gl)) if (ok and (gw + gl) > 0) else 0.5
        rw.welo, rl.welo = _upd(rw.welo, rl.welo, K * 2.0 * share)
        # mov_sets: K * (1 + 0.5*(sets_w - sets_l - 1)), floored at 0.5K
        kmov = K * max(0.5, 1.0 + 0.5 * ((sw - sl) - 1)) if ok else K
        rw.mov, rl.mov = _upd(rw.mov, rl.mov, kmov)
        # dynk
        kw, kl = _dyn_k(rw, today), _dyn_k(rl, today)
        # asymmetric K: each side moves by its own K against the shared expectation
        e = expected_score(rw.dynk, rl.dynk)
        rw.dynk, rl.dynk = rw.dynk + kw * (1 - e), rl.dynk - kl * (1 - e)
        # surface
        if s:
            rw.surf[s], rl.surf[s] = _upd(rw.surf[s], rl.surf[s], K)
            rw.surf_n[s] += 1; rl.surf_n[s] += 1
        rw.n += 1; rl.n += 1
        rw.last = rl.last = today

    out.close()
    print(f"\n{n_written:,} rows written to {OUTPUT_CSV}")
    print(f"Scores parsed on {n_score_ok:,} matches; winner had >= loser's games on "
          f"{(n_orient_ok / n_score_ok * 100) if n_score_ok else 0:.1f}% of them "
          f"(should be ~90%+; if far lower, the winner-first score assumption is WRONG and welo/mov are invalid).")


if __name__ == "__main__":
    run()
