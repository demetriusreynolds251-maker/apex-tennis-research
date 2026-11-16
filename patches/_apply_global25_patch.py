import sys

PATH = "apex_edge_tracker.py"
with open(PATH, "r", encoding="utf-8") as f:
    src = f.read()

orig = src

# ---------------------------------------------------------------------------
# PATCH 1: category probability gate -- add constant + helper right after
# _category_has_evidence(), following the exact same pattern/comment style
# already used for UNPROVEN_CATEGORY_MIN_N / UNPROVEN_CATEGORIES.
# ---------------------------------------------------------------------------
anchor1 = '''    if cat not in UNPROVEN_CATEGORIES:
        return True
    n = (rec.get("cats", {}).get(cat) or {}).get("n") or 0
    return n >= UNPROVEN_CATEGORY_MIN_N
'''
assert src.count(anchor1) == 1, "anchor1 not found exactly once"

insertion1 = anchor1 + '''

# APEX-CATGATE-2026-10-07 (owner, approved production configuration):
# per-category minimum stated-probability gate, applied as board-governance
# eligibility -- same category as _category_has_evidence() above. A pick
# below its category's floor never reaches apex_score()/ranking; apex_score
# itself, rank_score(), and Apex-Score-descending order are untouched.
# Approved post-calibration-bug-fix via the Final Post-Fix Championship
# Replay (2026-10-07): Global 25% blend + these floors won Top 3 and
# Elite 6 decisively over Current Production, Global25+Aces62.5%, and
# Prop-Specific on corrected data.
CATEGORY_PROBABILITY_GATE = {
    "dfs":            0.60,
    "games_won":      0.55,
    "fantasy_score":  0.65,
    "aces":           0.65,
    "breaks":         0.65,
    "total_games":    0.65,
    "total_sets":     0.50,
    "tiebreaks":      0.60,
}


def _category_probability_gate(cat, prob):
    """APEX-CATGATE-2026-10-07: True if `prob` clears this category's
    approved floor. A category not listed has no gate (returns True) --
    matches the approved configuration, which only specifies these eight."""
    floor = CATEGORY_PROBABILITY_GATE.get(cat)
    if floor is None:
        return True
    try:
        return float(prob or 0.0) >= floor
    except (TypeError, ValueError):
        return False
'''
src = src.replace(anchor1, insertion1, 1)

# ---------------------------------------------------------------------------
# PATCH 2a: call site #1 (~line 1373) -- uses prob_cal falling back to prob
# ---------------------------------------------------------------------------
anchor2a = '''        scored = []
        for p in picks:
            cat = p.get("category") or ""
            if not cat:
                continue
            if not _category_has_evidence(cat, rec):   # APEX-CAT-GATE-2026-09-27
                continue
            sc, ev, lvl, up, down = apex_score(p.get("prob_cal", p.get("prob")), cat, bool(p.get("bo5")), rec)
'''
assert src.count(anchor2a) == 1, "anchor2a not found exactly once"
insertion2a = '''        scored = []
        for p in picks:
            cat = p.get("category") or ""
            if not cat:
                continue
            if not _category_has_evidence(cat, rec):   # APEX-CAT-GATE-2026-09-27
                continue
            if not _category_probability_gate(cat, p.get("prob_cal", p.get("prob"))):   # APEX-CATGATE-2026-10-07
                continue
            sc, ev, lvl, up, down = apex_score(p.get("prob_cal", p.get("prob")), cat, bool(p.get("bo5")), rec)
'''
src = src.replace(anchor2a, insertion2a, 1)

# ---------------------------------------------------------------------------
# PATCH 2b: call site #2 (~line 2159) and PATCH 2c: call site #3 (~line 2543)
# are textually identical -- replace both occurrences of this exact block.
# ---------------------------------------------------------------------------
anchor2bc = '''        scored = []
        for p in picks:
            if not p.get("category"):
                continue
            if not _category_has_evidence(p["category"], rec):   # APEX-CAT-GATE-2026-09-27
                continue
            sc, ev, lvl, up, down = apex_score(p.get("prob"), p["category"], bool(p.get("bo5")), rec)
'''
anchor2bc_count = src.count(anchor2bc)
# one of the two call sites in this file omits the trailing comment on the
# evidence-gate line; handle both spellings explicitly below instead of
# assuming identical text at both sites.
anchor2b_nocomment = '''        scored = []
        for p in picks:
            if not p.get("category"):
                continue
            if not _category_has_evidence(p["category"], rec):
                continue
            sc, ev, lvl, up, down = apex_score(p.get("prob"), p["category"], bool(p.get("bo5")), rec)
'''

n_commented = src.count(anchor2bc)
n_plain = src.count(anchor2b_nocomment)
print(f"call-site variant counts: commented={n_commented} plain={n_plain}")

if n_commented:
    insertion2bc = '''        scored = []
        for p in picks:
            if not p.get("category"):
                continue
            if not _category_has_evidence(p["category"], rec):   # APEX-CAT-GATE-2026-09-27
                continue
            if not _category_probability_gate(p["category"], p.get("prob")):   # APEX-CATGATE-2026-10-07
                continue
            sc, ev, lvl, up, down = apex_score(p.get("prob"), p["category"], bool(p.get("bo5")), rec)
'''
    src = src.replace(anchor2bc, insertion2bc, n_commented)

if n_plain:
    insertion2b_nocomment = '''        scored = []
        for p in picks:
            if not p.get("category"):
                continue
            if not _category_has_evidence(p["category"], rec):
                continue
            if not _category_probability_gate(p["category"], p.get("prob")):   # APEX-CATGATE-2026-10-07
                continue
            sc, ev, lvl, up, down = apex_score(p.get("prob"), p["category"], bool(p.get("bo5")), rec)
'''
    src = src.replace(anchor2b_nocomment, insertion2b_nocomment, n_plain)

total_gate_sites = 1 + n_commented + n_plain
print(f"total probability-gate call sites patched: {total_gate_sites}")
assert total_gate_sites == 3, f"expected 3 gated call sites total, got {total_gate_sites}"

# ---------------------------------------------------------------------------
# PATCH 3: Global 25% calibration blend inside apex_score() itself --
# replace the fixed-manual-only EV with a 75% calibrated / 25% fixed-manual
# blend, applied across ALL categories (not just the six with a manual
# override -- categories outside that dict get 0.0 as their "B" value,
# so they resolve to 75% of the calibrated EV, consistent with "Global 25%
# calibration blend across all categories").
# ---------------------------------------------------------------------------
anchor3 = '''    _FIXED_CAL_MANUAL = {
        "total_games":   8.1,
        "games_won":     2.1,
        "dfs":          -1.0,
        "fantasy_score": -1.6,
        "breaks":       -3.6,
        "aces":         -11.2,
    }
    if cat in _FIXED_CAL_MANUAL:
        ev = _FIXED_CAL_MANUAL[cat]
        score += ev
        (up if ev >= 0 else down).append("%s fixed manual cal adj %+.2f (n=%d)"
            % (LABEL.get(cat, cat), ev, n))
    elif n < 5:
        down.append("%s barely tested (n=%d)" % (LABEL.get(cat, cat), n))
'''
assert src.count(anchor3) == 1, "anchor3 not found exactly once"

insertion3 = '''    # APEX-GLOBALBLEND25-2026-10-07 (owner, approved production
    # configuration): Global 25% calibration blend, applied across ALL
    # categories. Replaces the fixed-manual-only EV adjustment above with
    # 75% weight on the measured calibration gap (cal_pts-derived, same
    # category as APEX-FIXED-CAL-MANUAL before it) and 25% weight on the
    # fixed manual constants it supersedes. Approved via the Final Post-Fix
    # Championship Replay (2026-10-07) on corrected (post join-bug-fix)
    # settled data: Global 25% beat Current Production, Global25+Aces62.5%,
    # and Prop-Specific decisively on both Top 3 and Elite 6 win rate/ROI.
    _FIXED_CAL_MANUAL = {
        "total_games":   8.1,
        "games_won":     2.1,
        "dfs":          -1.0,
        "fantasy_score": -1.6,
        "breaks":       -3.6,
        "aces":         -11.2,
    }
    GLOBAL_BLEND_FRAC = 0.25   # weight toward the fixed manual table; 0.75 to calibration
    if n >= 5 and cs.get("cal_pts") is not None:
        _cal_scale = cs["cal_pts"] / 0.10
        ev_calibrated = (30.0 if _cal_scale < 0 else 20.0) * w * max(-1.5, min(1.0, _cal_scale))
    else:
        ev_calibrated = 0.0
    ev_fixed_manual = _FIXED_CAL_MANUAL.get(cat, 0.0)
    ev = ev_calibrated + GLOBAL_BLEND_FRAC * (ev_fixed_manual - ev_calibrated)
    score += ev
    if abs(ev) >= 0.5:
        (up if ev >= 0 else down).append("%s global25 cal blend %+.2f (n=%d)"
            % (LABEL.get(cat, cat), ev, n))
    if n < 5:
        down.append("%s barely tested (n=%d)" % (LABEL.get(cat, cat), n))
'''
src = src.replace(anchor3, insertion3, 1)

assert src != orig, "no changes were made"

with open(PATH, "w", encoding="utf-8") as f:
    f.write(src)

print("PATCH APPLIED OK")
