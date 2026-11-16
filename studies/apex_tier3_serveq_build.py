#!/usr/bin/env python3
"""
TIER 3 SERVE-QUALITY SIGNAL INVESTIGATION -- data build.

Real historical data only: same source as BPS_V1
("ATP & WTA, 1968-2026", read-only import of apex_prop_model_v1's
load_sackmann -- frozen file never modified, MD5-verified before/after).

Candidates (5, tested independently -- NOT pre-combined):
  FS%    = first serve in %            = 1stIn / svpt
  FSPW%  = first serve points won %    = 1stWon / 1stIn
  SSPW%  = second serve points won %   = 2ndWon / (svpt - 1stIn)
  SPW%   = service points won %        = (1stWon + 2ndWon) / svpt
  RPW%   = return points won %         = 1 - opponent's SPW% (this
           player's return-side outcome, derived from the OPPONENT's
           serve stats in that same match -- i.e. what this player
           faced and won returning)
  DR     = Dominance Ratio (combined serve/return metric, standard
           tennis-analytics definition) = RPW% / (1 - SPW%)

Feature engineering per candidate (A-D, tested independently per the
mission's "do not combine everything" instruction):
  A. "Raw" trailing rate: pooled (sum-of-counts, not average-of-ratios)
     rate over the player's last 20 matches, ALL SURFACES COMBINED, no
     shrinkage.
  B. Trailing-window sweep: same pooled-rate construction at N =
     10, 20, 30, 50 matches, to show window-size sensitivity.
  C. Shrinkage-blended version: surface-specific pooled rate (last 30
     matches on the match's surface) blended toward the all-surface
     pooled rate (same 30-match recency), shrink=15 -- the IDENTICAL
     match-count-weighted blend formula used by the frozen model's own
     rate_bundle() for hold_rate/break_rate (rate = (n_s*r_s + K*r_a)
     / (n_s + K)).
  D. Surface-specific raw version: SPW% only (the single highest-
     expected-value candidate under standard tennis-analytics priors),
     Hard-court pooled rate, last 30 Hard-court matches, no shrink --
     scope-bounded per the mission's "only if sample size sufficient"
     clause; Clay/Grass history per player is materially thinner (see
     BPS_INVESTIGATION_2026-09-27.md surface-split finding) and is not
     separately modeled here.

All features are trailing / pre-match only: computed from a player's
history strictly BEFORE the match being predicted, then that match's
own stats are appended. No leakage by construction.
"""
import sys, math, time
from collections import deque
import numpy as np
import pandas as pd

sys.path.insert(0, "/path/to/home/openclaw")
import apex_prop_model_v1 as v1  # read-only import; frozen file untouched

SURFACES = v1.SURFACES
WINDOWS = (10, 20, 30, 50)
SHRINK_N, SHRINK_K = 30, 15
SURF_N = 30


# raw-record layout (per player, per match): 8 components
# (svpt, in1, w1, w2, o_svpt, o_in1, o_w1, o_w2)
NCOMP = 8


class PState3:
    __slots__ = ("hist_all", "hist_surf")
    def __init__(self):
        self.hist_all = deque(maxlen=50)
        self.hist_surf = {s: deque(maxlen=50) for s in SURFACES}


def pooled_rate(sums, n):
    svpt, in1, w1, w2, o_svpt, o_in1, o_w1, o_w2 = sums
    out = {}
    out["fs"] = in1 / svpt if svpt > 0 else np.nan
    out["fspw"] = w1 / in1 if in1 > 0 else np.nan
    second_pts = svpt - in1
    out["sspw"] = w2 / second_pts if second_pts > 0 else np.nan
    out["spw"] = (w1 + w2) / svpt if svpt > 0 else np.nan
    out["rpw"] = 1 - (o_w1 + o_w2) / o_svpt if o_svpt > 0 else np.nan
    if not (math.isnan(out["spw"]) or out["spw"] >= 1.0) and not math.isnan(out["rpw"]):
        out["dr"] = out["rpw"] / (1 - out["spw"])
    else:
        out["dr"] = np.nan
    out["n"] = n
    return out


def window_sums(dq, n):
    sums = [0.0] * NCOMP
    cnt = 0
    for rec in list(dq)[-n:]:
        for i in range(NCOMP):
            sums[i] += rec[i]
        cnt += 1
    return sums, cnt


def shrink_blend(ps, surf, n, k):
    """Match-count-weighted shrinkage blend, identical mechanic to the
    frozen model's rate_bundle(): surface-specific pooled rate blended
    toward the same-recency all-surface pooled rate."""
    s_sums, ns = window_sums(ps.hist_surf.get(surf, ps.hist_all), n)
    a_sums, na = window_sums(ps.hist_all, n)
    if na == 0 or a_sums[0] <= 0:
        return None
    rs = pooled_rate(s_sums, ns) if ns > 0 and s_sums[0] > 0 else None
    ra = pooled_rate(a_sums, na)
    out = {}
    for key in ("fs", "fspw", "sspw", "spw", "rpw"):
        rv_a = ra[key] if not math.isnan(ra[key]) else 0.0
        rv_s = rs[key] if (rs is not None and not math.isnan(rs[key])) else rv_a
        out[key] = (ns * rv_s + k * rv_a) / (ns + k)
    if out["spw"] < 1.0:
        out["dr"] = out["rpw"] / (1 - out["spw"])
    else:
        out["dr"] = np.nan
    return out


METRICS = ("fs", "fspw", "sspw", "spw", "rpw", "dr")


def main():
    sackmann_dir = "ATP & WTA, 1968-2026"
    df = v1.load_sackmann(sackmann_dir, year_from=2005, challengers=False)
    print("loaded %d matches (year_from=2005, challengers OUT) %s .. %s" %
          (len(df), df["tourney_date"].min().date(), df["tourney_date"].max().date()))
    cov_cols = ["w_1stIn", "w_1stWon", "w_2ndWon", "w_svpt", "l_1stIn", "l_1stWon", "l_2ndWon", "l_svpt"]
    # load_sackmann's own numeric-coercion pass does not cover these serve
    # columns (only ace/df/svpt/svgms/bpSaved/bpFaced) -- coerce here so a
    # stray non-numeric token in the raw Sackmann CSVs can't corrupt the
    # arithmetic below; NaN after coercion is treated as missing (already
    # excluded by the `ok` gate).
    for c in cov_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    for c in cov_cols:
        print("  coverage %-10s %.4f" % (c, df[c].notna().mean()))

    players = {}
    rows = []
    t0 = time.time()
    for i, r in enumerate(df.itertuples(index=False)):
        if i and i % 20000 == 0:
            print("  ... %d (%.0fs)" % (i, time.time() - t0)); sys.stdout.flush()
        wn, ln = r.winner_name, r.loser_name
        pw = players.get(wn) or players.setdefault(wn, PState3())
        pl = players.get(ln) or players.setdefault(ln, PState3())
        dte = r.tourney_date.date(); surf = r.surface
        ok = all(not (isinstance(x, float) and math.isnan(x)) for x in
                 (r.w_1stIn, r.w_1stWon, r.w_2ndWon, r.w_svpt,
                  r.l_1stIn, r.l_1stWon, r.l_2ndWon, r.l_svpt)) \
            and r.w_svpt > 0 and r.l_svpt > 0
        row = {
            "date": dte.isoformat(), "year": dte.year, "tourney_id": str(r.tourney_id),
            "surface": surf, "is_wta": int(r.is_wta),
            "best_of": int(r.best_of) if not math.isnan(r.best_of) else 3,
            "winner": wn, "loser": ln, "ok": int(ok),
        }

        recw = (r.w_svpt, r.w_1stIn, r.w_1stWon, r.w_2ndWon, r.l_svpt, r.l_1stIn, r.l_1stWon, r.l_2ndWon)
        recl = (r.l_svpt, r.l_1stIn, r.l_1stWon, r.l_2ndWon, r.w_svpt, r.w_1stIn, r.w_1stWon, r.w_2ndWon)
        for side, ps, rec in (("w", pw, recw), ("l", pl, recl)):
            if ok:
                act = pooled_rate(rec, 1)
                for m in METRICS:
                    row["%s_actual_%s" % (side, m)] = act[m]
            else:
                for m in METRICS:
                    row["%s_actual_%s" % (side, m)] = np.nan
            for n in WINDOWS:
                sums, cnt = window_sums(ps.hist_all, n)
                rb = pooled_rate(sums, cnt) if cnt > 0 and sums[0] > 0 else None
                for m in METRICS:
                    row["%s_N%d_%s" % (side, n, m)] = rb[m] if rb else np.nan
            blend = shrink_blend(ps, surf, SHRINK_N, SHRINK_K)
            for m in METRICS:
                row["%s_shrink_%s" % (side, m)] = blend[m] if blend else np.nan
            hard_sums, hard_cnt = window_sums(ps.hist_surf["Hard"], SURF_N)
            hard_rb = pooled_rate(hard_sums, hard_cnt) if hard_cnt > 0 and hard_sums[0] > 0 else None
            row["%s_hardN30_spw" % side] = hard_rb["spw"] if hard_rb else np.nan
            row["%s_hardN30_n" % side] = hard_cnt
        rows.append(row)
        if ok:
            for ps, rec in ((pw, recw), (pl, recl)):
                ps.hist_all.append(rec)
                ps.hist_surf.setdefault(surf, deque(maxlen=50)).append(rec)
    out = pd.DataFrame(rows)
    out.to_csv("apex_tier3_serveq_rows.csv", index=False)
    print("wrote apex_tier3_serveq_rows.csv: %d rows, %d cols (%.0fs total)" %
          (out.shape[0], out.shape[1], time.time() - t0))


if __name__ == "__main__":
    main()
