#!/usr/bin/env python3
"""APEX-SLIP-V11-2026-09-08 -- Slip Builder v1.1: long-match-risk gate on LESS picks,
three slip types (standard / goblin / mixed), card warning, per-type logging.
Usage: python3 apex_slip_v11_patch.py --check | --apply"""
import hashlib, shutil, sys, py_compile, datetime
F = "apex_edge_tracker.py"; PIN = "4e46210b6e6d252b10ff691fdd60c64db30bc74dd0250b8f878531259a1a616d"
MARK = "APEX-SLIP-V11-2026-09-08"

A1_OLD = r'''SLIP_SLOTS = 5
'''
A1_NEW = r'''SLIP_SLOTS = 5
# APEX-SLIP-V11-2026-09-08: long-match risk from the match price (fit on 48,678 Bo3 / 5,509 Bo5
# Sackmann+Pinnacle matches, holdout band error 0.010). A LESS pick on a rate category is a bet
# that the match stays short; above LONG_MATCH_LESS_MAX it is not slotted.
LONG_MATCH_LESS_MAX = 0.40
_LMR_BO3 = (-0.3623, -0.0832, -0.1378, -0.1081)   # const, lp, lp^2, wta
_LMR_BO5 = (0.4645, -0.0427, -0.1593)             # const, lp, lp^2

def long_match_risk(p):
    """P(3 sets) in Bo3 / P(4+ sets) in Bo5 from pinn_fav. None if no price."""
    try:
        import math
        pf = float(p.get("pinn_fav") or 0)
        if not (0.5 <= pf < 1.0): return None
        lp = math.log(pf / (1 - pf))
        bo5 = bool(p.get("bo5")) or str(p.get("best_of", "")) == "5"
        if bo5:
            c = _LMR_BO5; z = c[0] + c[1] * lp + c[2] * lp * lp
        else:
            c = _LMR_BO3; z = c[0] + c[1] * lp + c[2] * lp * lp   # wta term omitted (not on the row; -0.11 shifts <3 pts)
        return 1.0 / (1.0 + math.exp(-z))
    except Exception:
        return None

SLIP_KINDS = (("mixed", "MIXED SLIP (all prop types)"),
              ("standard", "STANDARD SLIP (standard props only)"),
              ("goblin", "GOBLIN SLIP (goblin props only -- MORE-only lines)"))
'''

A2_OLD = r'''def slip_builder(scored):
'''
A2_NEW = r'''def slip_builder(scored, kind="mixed"):
'''

A3_OLD = r'''        nxt = len(slots) + 1
        why = ""
        if pl in players:
'''
A3_NEW = r'''        nxt = len(slots) + 1
        why = ""
        _pt = str(d["p"].get("prop_type") or "").lower()          # APEX-SLIP-V11: slip type filter
        if kind == "standard" and _pt != "standard":
            out[id(d)] = ("", "", pos); continue
        if kind == "goblin" and _pt != "goblin":
            out[id(d)] = ("", "", pos); continue
        _risk = long_match_risk(d["p"])                             # APEX-SLIP-V11: length gate on LESS
        if dr == "LESS" and cat in ("dfs", "aces", "breaks") and _risk is not None and _risk >= LONG_MATCH_LESS_MAX:
            why = "long-match risk %d%% -- LESS props need a short match" % round(_risk * 100)
        if why:
            out[id(d)] = ("", why, pos); continue
        if pl in players:
'''

A4_OLD = r'''def _slip_block(scored, slip):
    """Render the SLIP CANDIDATES section. Complete transparency: slots, then every
    displaced pick with its reason."""
    L = ["", "\U0001F3AF **SLIP CANDIDATES** (Slip Builder v1 -- construction layer; RANK order above is untouched)"]
    slotted = sorted((v[0], d) for d in scored if (v := slip.get(id(d))) and v[0])
    if not slotted:
        L.append("-- no slip candidates"); return L
'''
A4_NEW = r'''def _slip_block(scored, slip, title="SLIP CANDIDATES", kind="mixed"):
    """Render one slip section. Complete transparency: slots, then every displaced pick with its reason."""
    L = ["", "\U0001F3AF **%s** (Slip Builder v1.1 -- construction layer; RANK order above is untouched)" % title]
    slotted = sorted((v[0], d) for d in scored if (v := slip.get(id(d))) and v[0])
    if not slotted:
        if kind != "mixed" and not any(str(d["p"].get("prop_type") or "") for d in scored):
            L.append("-- prop types not logged for this board yet (populates from the next evaluation)")
        else:
            L.append("-- no eligible picks for this slip type")
        return L
'''

A5_OLD = r'''    L.append("_Slip rules: top 3 max 2 per category, max 2 per category+direction, one per match; top 5 max 2 per category. Logged as slip_slot for ALIS._")
    return L
'''
A5_NEW = r'''    return L

def _slip_sections(scored):
    """All three slips + the shared rules footer. Returns (lines, {kind: slipmap})."""
    L, maps = [], {}
    for kind, title in SLIP_KINDS:
        maps[kind] = slip_builder(scored, kind)
        L.extend(_slip_block(scored, maps[kind], title, kind))
    L.append("_Slip rules: top 3 max 2 per category, max 2 per category+direction, one per match; top 5 max 2 per category; "
             "LESS on dfs/aces/breaks needs long-match risk under %d%%. Logged as slip\\_slot / slip\\_std\\_slot / slip\\_gob\\_slot for ALIS._" % round(LONG_MATCH_LESS_MAX * 100))
    return L, maps
'''

A6_OLD = r'''                   "slip_slot", "slip_reason"]   # APEX-SLIP-V1-2026-09-06
'''
A6_NEW = r'''                   "slip_slot", "slip_reason",   # APEX-SLIP-V1-2026-09-06 (mixed)
                   "slip_std_slot", "slip_std_reason", "slip_gob_slot", "slip_gob_reason"]   # APEX-SLIP-V11
'''
A7_OLD = r'''def _bb_rank_log(scored, legacy_pos, source, path=None, slip=None):
'''
A7_NEW = r'''def _bb_rank_log(scored, legacy_pos, source, path=None, slip=None, slip_std=None, slip_gob=None):
'''
A8_OLD = r'''            if "slip_slot" not in _hdr:
'''
A8_NEW = r'''            if _hdr != _BB_RANK_FIELDS:
'''
A9_OLD = r'''        slip = slip or {}
        with open(path, "a", newline="", encoding="utf-8") as fh:
'''
A9_NEW = r'''        slip = slip or {}; slip_std = slip_std or {}; slip_gob = slip_gob or {}
        with open(path, "a", newline="", encoding="utf-8") as fh:
'''
A10_OLD = r'''                            "slip_reason": (slip.get(id(d)) or ("", "", 0))[1]})
'''
A10_NEW = r'''                            "slip_reason": (slip.get(id(d)) or ("", "", 0))[1],
                            "slip_std_slot": (slip_std.get(id(d)) or ("", "", 0))[0],
                            "slip_std_reason": (slip_std.get(id(d)) or ("", "", 0))[1],
                            "slip_gob_slot": (slip_gob.get(id(d)) or ("", "", 0))[0],
                            "slip_gob_reason": (slip_gob.get(id(d)) or ("", "", 0))[1]})
'''
A11_OLD = r'''        try:                                   # APEX-SLIP-V1: construction layer, fail-open
            _slip = slip_builder(scored)
            L.extend(_slip_block(scored, _slip))
        except Exception:
            _slip = {}
        _bb_rank_log(scored, _legacy_pos, "block", slip=_slip)
'''
A11_NEW = r'''        try:                                   # APEX-SLIP-V11: three slips, fail-open
            _sl, _maps = _slip_sections(scored); L.extend(_sl)
        except Exception:
            _maps = {}
        _bb_rank_log(scored, _legacy_pos, "block", slip=_maps.get("mixed"), slip_std=_maps.get("standard"), slip_gob=_maps.get("goblin"))
'''
A12_OLD = r'''        try:                                   # APEX-SLIP-V1: construction layer, fail-open
            _slip = slip_builder(scored)
            L.extend(_slip_block(scored, _slip))
        except Exception:
            _slip = {}
        _bb_rank_log(scored, _legacy_pos, "detail", slip=_slip)
'''
A12_NEW = r'''        try:                                   # APEX-SLIP-V11: three slips, fail-open
            _sl, _maps = _slip_sections(scored); L.extend(_sl)
        except Exception:
            _maps = {}
        _bb_rank_log(scored, _legacy_pos, "detail", slip=_maps.get("mixed"), slip_std=_maps.get("standard"), slip_gob=_maps.get("goblin"))
'''
A13_OLD = r'''            if not worst and d["sc"] < 50:
'''
A13_NEW = r'''            _lmr = long_match_risk(p)                          # APEX-SLIP-V11: length warning on LESS cards
            if str(p.get("direction", "")).upper() == "LESS" and cat in ("dfs", "aces", "breaks") and _lmr is not None:
                L.append("%s long-match risk %d%% -- a LESS prop here is a bet the match stays short%s" % (
                    "\u26a0\ufe0f" if _lmr >= LONG_MATCH_LESS_MAX else "\u2139\ufe0f", round(_lmr * 100),
                    " (kept off the slip)" if _lmr >= LONG_MATCH_LESS_MAX else ""))
            if not worst and d["sc"] < 50:
'''
ANCHORS = [(f"A{i}", o, n) for i, (o, n) in enumerate([(A1_OLD, A1_NEW), (A2_OLD, A2_NEW), (A3_OLD, A3_NEW), (A4_OLD, A4_NEW),
            (A5_OLD, A5_NEW), (A6_OLD, A6_NEW), (A7_OLD, A7_NEW), (A8_OLD, A8_NEW), (A9_OLD, A9_NEW), (A10_OLD, A10_NEW),
            (A11_OLD, A11_NEW), (A12_OLD, A12_NEW), (A13_OLD, A13_NEW)], 1)]

def sha(p): return hashlib.sha256(open(p, "rb").read()).hexdigest()
def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "--check"
    src = open(F, encoding="utf-8").read(); s = sha(F)
    assert s == PIN, f"SHA mismatch: {s}"; assert MARK not in src, "already applied"
    for n, o, _ in ANCHORS:
        c = src.count(o); assert c == 1, f"anchor {n} matched {c}x"
    assert src.index(A11_OLD) < src.index(A12_OLD), "A11 (block) must precede A12 (detail)"
    print("CHECK OK: SHA pinned, anchors 13/13 unique")
    if mode != "--apply": return
    bak = F + ".bak_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + "_preslipv11"; shutil.copy2(F, bak)
    new = src
    for _, o, n in ANCHORS: new = new.replace(o, n, 1)
    open(F, "w", encoding="utf-8").write(new)
    try: py_compile.compile(F, doraise=True)
    except Exception as e: shutil.copy2(bak, F); print("py_compile FAILED -> restored:", e); sys.exit(1)
    print("APPLIED. backup:", bak); print("new sha:", sha(F))
if __name__ == "__main__": main()
