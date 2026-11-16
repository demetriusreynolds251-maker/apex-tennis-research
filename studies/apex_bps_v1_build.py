#!/usr/bin/env python3
"""
BPS_V1 Phase 2 BUILD.

Computes a trailing (leakage-safe, pre-match-only), shrinkage-blended
Break-Points-Saved% feature per player, using the IDENTICAL replay /
history / shrinkage mechanism the frozen apex_prop_model_v1.py already
uses for its hold_rate / break_rate / ace_rate / df_rate rolling
features (PState, REC_FIELDS, WINDOW_GRID, SHRINK_GRID, load_sackmann
are imported read-only from the frozen module -- that file is NEVER
written to by this script).

Also computes a genuine, distinct "break points scored" trailing rate
(bp_conv_rate = break points WON per break point FACED while
returning), separate from break_rate (breaks per return GAME), so the
three baseline predictors named in the task (hold rate, break rate,
break points scored) are each real, independently-computed features,
not synonyms of each other.

Output: apex_bps_v1_rows.csv -- one row per historical match (2005+,
main tour only, challengers excluded, matching production convention),
with join/id columns, ACTUAL post-hoc outcomes (the target variables),
and TRAILING (pre-match) features for every (W,K) in the production
WINDOW_GRID x SHRINK_GRID grid, for both winner and loser sides.
"""
import sys, math, time
from collections import deque
import numpy as np
import pandas as pd

sys.path.insert(0, "/path/to/home/openclaw")
import apex_prop_model_v1 as v1  # read-only import; frozen file untouched

WINDOW_GRID = v1.WINDOW_GRID
SHRINK_GRID = v1.SHRINK_GRID
SURFACES = v1.SURFACES
REC_FIELDS = v1.REC_FIELDS  # ("ace","df","svpt","svgms","bpf","bps","osvgms","obpf","obps")


class PState2:
    """Minimal state clone: only what's needed for trailing-rate math.
    Deliberately independent of v1.PState (no Elo, no production
    mutation) -- this script never writes to any object the frozen
    module owns."""
    __slots__ = ("hist",)
    def __init__(self):
        self.hist = {s: deque(maxlen=max(WINDOW_GRID)) for s in SURFACES + ("All",)}


def rate_bundle2(ps, surface, window, shrink):
    """Same surface-shrunk-toward-all-surface mechanic as the frozen
    rate_bundle(), plus two additions: bps_rate (the BPS_V1 candidate)
    and bp_conv_rate (break points WON per break point FACED while
    returning -- a genuine 'break points scored' rate, distinct from
    break_rate which is breaks per return GAME)."""
    def sums(dq, w):
        out = dict((f, 0.0) for f in REC_FIELDS); cnt = 0
        for rec in list(dq)[-w:]:
            for i, f in enumerate(REC_FIELDS):
                out[f] += rec[i]
            cnt += 1
        out["n"] = cnt
        return out
    a = sums(ps.hist["All"], window)
    s = sums(ps.hist.get(surface, ps.hist["All"]), window)
    if a["n"] == 0 or a["svpt"] <= 0 or a["svgms"] <= 0:
        return None
    def rate(num_s, den_s, num_a, den_a):
        ra = num_a / den_a if den_a > 0 else 0.0
        ns = s["n"]
        rs = num_s / den_s if den_s > 0 else ra
        return (ns * rs + shrink * ra) / (ns + shrink)
    holds_s = s["svgms"] - (s["bpf"] - s["bps"]); holds_a = a["svgms"] - (a["bpf"] - a["bps"])
    brk_s = s["obpf"] - s["obps"]; brk_a = a["obpf"] - a["obps"]
    return {
        "ace_rate":    rate(s["ace"], s["svpt"], a["ace"], a["svpt"]),
        "df_rate":     rate(s["df"], s["svpt"], a["df"], a["svpt"]),
        "hold_rate":   rate(holds_s, s["svgms"], holds_a, a["svgms"]),
        "break_rate":  rate(brk_s, s["osvgms"], brk_a, a["osvgms"]),
        "bps_rate":    rate(s["bps"], s["bpf"], a["bps"], a["bpf"]),
        "bp_conv_rate": rate(s["obpf"] - s["obps"], s["obpf"], a["obpf"] - a["obps"], a["obpf"]),
        "n_surf": s["n"], "n_all": a["n"],
    }


FEATURE_KEYS = ("ace_rate", "df_rate", "hold_rate", "break_rate", "bps_rate", "bp_conv_rate")


def main():
    sackmann_dir = "ATP & WTA, 1968-2026"
    df = v1.load_sackmann(sackmann_dir, year_from=2005, challengers=False)
    print("loaded %d matches (year_from=2005, challengers OUT) %s .. %s" %
          (len(df), df["tourney_date"].min().date(), df["tourney_date"].max().date()))
    grids = [(w, k) for w in WINDOW_GRID for k in SHRINK_GRID]
    players = {}
    rows = []
    t0 = time.time()
    for i, r in enumerate(df.itertuples(index=False)):
        if i and i % 20000 == 0:
            print("  ... %d (%.0fs)" % (i, time.time() - t0)); sys.stdout.flush()
        wn, ln = r.winner_name, r.loser_name
        pw = players.get(wn) or players.setdefault(wn, PState2())
        pl = players.get(ln) or players.setdefault(ln, PState2())
        dte = r.tourney_date.date(); surf = r.surface
        stats_ok = all(not (isinstance(x, float) and math.isnan(x)) for x in
                       (r.w_ace, r.w_df, r.w_svpt, r.w_SvGms, r.w_bpSaved, r.w_bpFaced,
                        r.l_ace, r.l_df, r.l_svpt, r.l_SvGms, r.l_bpSaved, r.l_bpFaced)) \
            and r.w_svpt > 0 and r.l_svpt > 0 and r.w_SvGms > 0 and r.l_SvGms > 0
        row = {
            "date": dte.isoformat(), "year": dte.year, "tourney_id": str(r.tourney_id),
            "tourney_name": str(r.tourney_name), "surface": surf, "is_wta": int(r.is_wta),
            "best_of": int(r.best_of) if not math.isnan(r.best_of) else 3,
            "winner": wn, "loser": ln, "stats_ok": int(stats_ok),
        }

        if stats_ok:
            row["w_bpSaved"] = r.w_bpSaved; row["w_bpFaced"] = r.w_bpFaced
            row["w_bpSaved_pct"] = r.w_bpSaved / r.w_bpFaced if r.w_bpFaced > 0 else np.nan
            row["l_bpSaved"] = r.l_bpSaved; row["l_bpFaced"] = r.l_bpFaced
            row["l_bpSaved_pct"] = r.l_bpSaved / r.l_bpFaced if r.l_bpFaced > 0 else np.nan
            row["w_hold_rate_actual"] = (r.w_SvGms - (r.w_bpFaced - r.w_bpSaved)) / r.w_SvGms
            row["l_hold_rate_actual"] = (r.l_SvGms - (r.l_bpFaced - r.l_bpSaved)) / r.l_SvGms
            row["w_break_rate_actual"] = (r.l_bpFaced - r.l_bpSaved) / r.l_SvGms
            row["l_break_rate_actual"] = (r.w_bpFaced - r.w_bpSaved) / r.w_SvGms
        else:
            for k in ("w_bpSaved", "w_bpFaced", "w_bpSaved_pct", "l_bpSaved", "l_bpFaced",
                      "l_bpSaved_pct", "w_hold_rate_actual", "l_hold_rate_actual",
                      "w_break_rate_actual", "l_break_rate_actual"):
                row[k] = np.nan
        for (w, k) in grids:
            for side, ps in (("w", pw), ("l", pl)):
                rb = rate_bundle2(ps, surf, w, k)
                tag = "%s_W%d_K%d" % (side, w, k)
                if rb:
                    for key in FEATURE_KEYS:
                        row["%s_%s" % (tag, key)] = rb[key]
                    row["%s_nsurf" % tag] = rb["n_surf"]; row["%s_nall" % tag] = rb["n_all"]
                else:
                    for key in FEATURE_KEYS + ("nsurf", "nall"):
                        row["%s_%s" % (tag, key)] = np.nan
        rows.append(row)

        if stats_ok:
            recw = (r.w_ace, r.w_df, r.w_svpt, r.w_SvGms, r.w_bpFaced, r.w_bpSaved,
                    r.l_SvGms, r.l_bpFaced, r.l_bpSaved)
            recl = (r.l_ace, r.l_df, r.l_svpt, r.l_SvGms, r.l_bpFaced, r.l_bpSaved,
                    r.w_SvGms, r.w_bpFaced, r.w_bpSaved)
            for ps, rec in ((pw, recw), (pl, recl)):
                ps.hist["All"].append(rec)
                ps.hist.setdefault(surf, deque(maxlen=max(WINDOW_GRID))).append(rec)
    out = pd.DataFrame(rows)
    out.to_csv("apex_bps_v1_rows.csv", index=False)
    print("wrote apex_bps_v1_rows.csv: %d rows, %d cols (%.0fs total)" %
          (out.shape[0], out.shape[1], time.time() - t0))


if __name__ == "__main__":
    main()
