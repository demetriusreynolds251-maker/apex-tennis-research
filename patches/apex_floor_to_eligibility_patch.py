#!/usr/bin/env python3
"""APEX-FLOOR-TO-ELIGIBILITY-2026-09-28 -- converts the Goblin (72.1%) and
Standard (70.0%) floors from hard rejections into non-blocking eligibility
flags, per explicit directive (2026-09-28): floors were rejecting props
entirely (ENGINE_DECLINED, no log row, never reached Picks Channel), which
was not the intended behavior. New behavior:
  - Every prop still becomes a real pick: logged, ranked, published to
    Picks Channel with probability/confidence/ranking as normal.
  - best_goblin_eligible / best_standard_eligible booleans are computed and
    carried on the pick object and in the picks log (new CSV columns), so
    Best Goblin / Best Standard generation (a separate patch,
    apex_best_eligibility_filter_patch.py, in apex_edge_tracker.py) can
    gate on them without touching Picks Channel, logging, or tracking.
  - A pick below its own type's floor gets a plain-language note attached
    ("⚠️ Below Best Goblin/Standard Threshold (NN.N%) -- still tracked for
    research purposes.") instead of being declined.
No thresholds changed (still 0.721 / 0.70); no classifier logic touched.

Usage: python3 apex_floor_to_eligibility_patch.py --check | --apply"""
import hashlib, shutil, sys, py_compile, datetime

F = "openclaw_core.py"
PIN = "7a4aebb2694325423a94e1a9d141670df0a4ebb3673d78aedb7f8bb43e39c194"
MARK = "APEX-FLOOR-TO-ELIGIBILITY-2026-09-28"

# --- A1: replace both hard-reject blocks with non-blocking eligibility calc ---
A1_OLD = '''        # APEX-GOBLIN-FLOOR-ENGINE-2026-09-28: the 09-24 Goblin break-even
        # floor lived only in scoring_agent(), which this engine path never
        # calls on success -- so it never ran for engine-produced Goblin
        # picks. Checked here, against the engine's own real win
        # probability, before the pick is logged or returned. Same
        # GOBLIN_BREAKEVEN constant as the original patch; same "no pick
        # produced" intent, now enforced where picks are actually made.
        _GOBLIN_BREAKEVEN_ENGINE = 0.721
        if (str(prop.get("prop_type_classified") or "") == "goblin"
                and prob < _GOBLIN_BREAKEVEN_ENGINE):
            _gb_reason = (f"goblin break-even block: engine prob {prob:.1%} is below the "
                          f"{_GOBLIN_BREAKEVEN_ENGINE:.1%} goblin payout needs to break even "
                          f"-> legacy")
            _apex_decline(prop, _gb_reason)
            log("ApexEngine", f"GOBLIN BREAK-EVEN BLOCK (engine path) — {player} {slug} {line} "
                              f"p={prob:.1%} below {_GOBLIN_BREAKEVEN_ENGINE:.1%}. No pick produced.")
            try:
                send_discord("alerts",
                    f"🛑 **GOBLIN BELOW BREAK-EVEN — NO PICK** — {player} vs {opponent}\\n"
                    f"`{line} {slug}` engine probability {prob:.1%} is below the "
                    f"{_GOBLIN_BREAKEVEN_ENGINE:.1%} goblin payout requires to break even. "
                    f"Blocked in the engine path before posting."
                )
            except Exception:
                pass
            return None

        # APEX-STANDARD-FLOOR-ENGINE-2026-09-28: business/risk-management
        # floor (directive, 2026-09-28) -- NOT calibration-derived (settled
        # Standard sample too small: 62 total, 2 days). Quality-over-quantity
        # decision: Standard must clear 70.0% real engine win probability to
        # qualify for publication. Same placement/idiom as the Goblin check
        # immediately above: before logging, ranking, or posting -- a
        # below-floor Standard prop never becomes a pick.
        _STANDARD_MIN_WIN_PROB = 0.70
        if (str(prop.get("prop_type_classified") or "") == "standard"
                and prob < _STANDARD_MIN_WIN_PROB):
            _sf_reason = (f"standard quality floor: engine prob {prob:.1%} is below the "
                          f"{_STANDARD_MIN_WIN_PROB:.1%} minimum required for Standard "
                          f"publication -> legacy")
            _apex_decline(prop, _sf_reason)
            log("ApexEngine", f"STANDARD FLOOR BLOCK (engine path) — {player} {slug} {line} "
                              f"p={prob:.1%} below {_STANDARD_MIN_WIN_PROB:.1%}. No pick produced.")
            try:
                send_discord("alerts",
                    f"🛑 **STANDARD BELOW FLOOR — NO PICK** — {player} vs {opponent}\\n"
                    f"`{line} {slug}` engine probability {prob:.1%} is below the "
                    f"{_STANDARD_MIN_WIN_PROB:.1%} minimum required for a Standard pick to publish. "
                    f"Blocked in the engine path before posting."
                )
            except Exception:
                pass
            return None

        # ── APEX-FORWARD-LOG-2026-08-24: this pick exists outside Discord now
'''
A1_NEW = '''        # APEX-FLOOR-TO-ELIGIBILITY-2026-09-28: Goblin (72.1%) and Standard
        # (70.0%) floors no longer block the pick from being made, logged,
        # or published -- per directive, that was rejecting props from the
        # whole system, which was not the intended behavior. Every prop
        # still becomes a real, published pick with normal probability /
        # confidence / ranking. These two booleans (also written to the
        # picks log -- see _apex_forward_log_row) are read ONLY by Best
        # Goblin / Best Standard generation and headline recommendations
        # (apex_edge_tracker.py); Picks Channel, logging, historical
        # tracking, calibration tracking, and research monitoring never
        # filter on them and see every prop regardless of eligibility.
        _GOBLIN_BREAKEVEN_ENGINE = 0.721
        _STANDARD_MIN_WIN_PROB   = 0.70
        _ptype_elig = str(prop.get("prop_type_classified") or "")
        best_goblin_eligible   = not (_ptype_elig == "goblin"   and prob < _GOBLIN_BREAKEVEN_ENGINE)
        best_standard_eligible = not (_ptype_elig == "standard" and prob < _STANDARD_MIN_WIN_PROB)
        _eligibility_note = None
        if _ptype_elig == "goblin" and not best_goblin_eligible:
            _eligibility_note = (f"⚠️ Below Best Goblin Threshold ({prob:.1%}) — "
                                  f"still tracked for research purposes.")
            log("ApexEngine", f"GOBLIN below Best-Goblin threshold (still published) — "
                              f"{player} {slug} {line} p={prob:.1%} < {_GOBLIN_BREAKEVEN_ENGINE:.1%}")
        elif _ptype_elig == "standard" and not best_standard_eligible:
            _eligibility_note = (f"⚠️ Below Best Standard Threshold ({prob:.1%}) — "
                                  f"still tracked for research purposes.")
            log("ApexEngine", f"STANDARD below Best-Standard threshold (still published) — "
                              f"{player} {slug} {line} p={prob:.1%} < {_STANDARD_MIN_WIN_PROB:.1%}")

        # ── APEX-FORWARD-LOG-2026-08-24: this pick exists outside Discord now
'''

# --- A2: carry the flags + note onto the in-memory pick dict this same run ---
A2_OLD = '''            "apex_tier":           target["tier"],
            "apex_best_of":        res.get("best_of", ""),
        }
'''
A2_NEW = '''            "apex_tier":           target["tier"],
            "apex_best_of":        res.get("best_of", ""),
            "best_goblin_eligible":   best_goblin_eligible,     # APEX-FLOOR-TO-ELIGIBILITY-2026-09-28
            "best_standard_eligible": best_standard_eligible,   # APEX-FLOOR-TO-ELIGIBILITY-2026-09-28
            "eligibility_note":       _eligibility_note,        # APEX-FLOOR-TO-ELIGIBILITY-2026-09-28
        }
'''

# --- A3: compute + persist the same two flags into the picks-log row ---
A3_OLD = '''    if _playable == "0":
        log("ApexEngine", f"UNPLAYABLE: {row_player} {cat} {f(line, '%.1f')} -- "
                          f"{_ptype} is {_lock}-only, engine says {direction}. "
                          f"Honest pick kept, excluded from bettable ranking.")
    pick_row = {"playable": _playable,
                "prop_type": _ptype,                     # APEX-PROPTYPE-2026-09-08
'''
A3_NEW = '''    if _playable == "0":
        log("ApexEngine", f"UNPLAYABLE: {row_player} {cat} {f(line, '%.1f')} -- "
                          f"{_ptype} is {_lock}-only, engine says {direction}. "
                          f"Honest pick kept, excluded from bettable ranking.")
    # APEX-FLOOR-TO-ELIGIBILITY-2026-09-28: recorded for Best Goblin / Best
    # Standard generation to read later -- never used to filter this log,
    # historical tracking, or calibration, all of which see every row.
    _pf = None
    try:
        _pf = float(prob)
    except (TypeError, ValueError):
        pass
    _best_goblin_eligible   = not (_ptype == "goblin"   and _pf is not None and _pf < 0.721)
    _best_standard_eligible = not (_ptype == "standard" and _pf is not None and _pf < 0.70)
    pick_row = {"playable": _playable,
                "prop_type": _ptype,                     # APEX-PROPTYPE-2026-09-08
                "best_goblin_eligible":   _best_goblin_eligible,     # APEX-FLOOR-TO-ELIGIBILITY-2026-09-28
                "best_standard_eligible": _best_standard_eligible,   # APEX-FLOOR-TO-ELIGIBILITY-2026-09-28
'''

# --- A4: add the two new columns to the picks-log schema ---
A4_OLD = '''_APEX_PICK_FIELDS = ["ts", "match_id", "match_date", "player", "opponent", "category", "stat_type", "line",
                     "direction", "prob", "tier", "label", "edge", "confidence", "surface", "best_of",
                     "tournament", "price_source", "main_total", "format_label", "pinn_fav", "sim_sha", "v1_sha",
                     "playable", "slip_start_utc",   # APEX-PLAYABLE-2026-08-31
                     "prop_type",                    # APEX-PROPTYPE-2026-09-08
                     "prob_cal"]                     # APEX-ACESCAL-2026-09-09
'''
A4_NEW = '''_APEX_PICK_FIELDS = ["ts", "match_id", "match_date", "player", "opponent", "category", "stat_type", "line",
                     "direction", "prob", "tier", "label", "edge", "confidence", "surface", "best_of",
                     "tournament", "price_source", "main_total", "format_label", "pinn_fav", "sim_sha", "v1_sha",
                     "playable", "slip_start_utc",   # APEX-PLAYABLE-2026-08-31
                     "prop_type",                    # APEX-PROPTYPE-2026-09-08
                     "prob_cal",                      # APEX-ACESCAL-2026-09-09
                     "best_goblin_eligible", "best_standard_eligible"]  # APEX-FLOOR-TO-ELIGIBILITY-2026-09-28
'''

ANCHORS = [("A1", A1_OLD, A1_NEW), ("A2", A2_OLD, A2_NEW), ("A3", A3_OLD, A3_NEW), ("A4", A4_OLD, A4_NEW)]


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "--check"
    src = open(F, encoding="utf-8").read()
    s = sha(F)
    assert s == PIN, f"SHA mismatch: {s}"
    assert MARK not in src, "already applied"
    for n, o, _ in ANCHORS:
        c = src.count(o)
        assert c == 1, f"anchor {n} matched {c}x"
    print("CHECK OK: SHA pinned, anchors %d/%d unique" % (len(ANCHORS), len(ANCHORS)))
    if mode != "--apply":
        return
    bak = F + ".bak_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + "_prefloortoelig"
    shutil.copy2(F, bak)
    new = src
    for _, o, nw in ANCHORS:
        new = new.replace(o, nw, 1)
    open(F, "w", encoding="utf-8").write(new)
    try:
        py_compile.compile(F, doraise=True)
    except Exception as e:
        shutil.copy2(bak, F)
        print("py_compile FAILED -> restored:", e)
        sys.exit(1)
    print("APPLIED. backup:", bak)
    print("new sha:", sha(F))


if __name__ == "__main__":
    main()
