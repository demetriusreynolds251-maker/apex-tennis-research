#!/usr/bin/env python3
"""APEX-ACESCAL-TRK-2026-09-09 -- use the calibrated probability for scoring, break-even and
ranking; show both numbers on the detail card; log prob_cal. Raw prob is still what goes to
ALIS, so the correction itself stays checkable against the original numbers.
Usage: python3 apex_acescal_tracker_patch.py --check | --apply"""
import hashlib, shutil, sys, py_compile, datetime
F = "apex_edge_tracker.py"; PIN = "cd145049ab028c6e4813966ae0d315269f8443207db3d2b2164360036aa9ee83"
MARK = "APEX-ACESCAL-TRK-2026-09-09"

A1_OLD = r'''                    "direction": r.get("direction") or "", "prob": prob,
'''
A1_NEW = r'''                    "direction": r.get("direction") or "", "prob": prob,
                    "prob_cal": _cal_of(r, prob),          # APEX-ACESCAL-TRK-2026-09-09
'''
A2_OLD = r'''    out = []
    for r in live:
        try:
            prob = float(r.get("prob") or 0)
        except (TypeError, ValueError):
            prob = 0.0
'''
A2_NEW = r'''    # APEX-ACESCAL-TRK-2026-09-09: the calibrated probability written by the engine.
    # Missing or unparsable (every row before 09-09) falls back to the raw value.
    def _cal_of(r, raw):
        try:
            v = float(r.get("prob_cal") or 0)
            return v if 0.0 < v <= raw + 1e-9 else raw
        except (TypeError, ValueError):
            return raw
    out = []
    for r in live:
        try:
            prob = float(r.get("prob") or 0)
        except (TypeError, ValueError):
            prob = 0.0
'''
A3_OLD = r'''            sc, ev, lvl, up, down = apex_score(p.get("prob"), cat, bool(p.get("bo5")), rec)
'''
A3_NEW = r'''            sc, ev, lvl, up, down = apex_score(p.get("prob_cal", p.get("prob")), cat, bool(p.get("bo5")), rec)
            if float(p.get("prob_cal", p.get("prob")) or 0) < float(p.get("prob") or 0) - 1e-9:
                down.append("aces LESS calibrated %d%% from %d%% (measured bias)" % (
                    round(float(p["prob_cal"]) * 100), round(float(p["prob"]) * 100)))
'''
A4_OLD = r'''            L.append("%s `%s %s` \u00b7 %d%% \u00b7 **APEX SCORE %d**" % (
                LABEL.get(cat, cat), p["line"], p["direction"], round(d["p"]["prob"] * 100), d["sc"]))
'''
A4_NEW = r'''            _pr, _pc = float(p.get("prob") or 0), float(p.get("prob_cal", p.get("prob")) or 0)
            L.append("%s `%s %s` \u00b7 %s \u00b7 **APEX SCORE %d**" % (
                LABEL.get(cat, cat), p["line"], p["direction"],
                ("%d%%" % round(_pr * 100)) if _pc >= _pr - 1e-9
                else ("%d%% \u00b7 calibrated %d%%" % (round(_pr * 100), round(_pc * 100))), d["sc"]))
'''
A5_OLD = r'''                   "slip_slot", "slip_reason",   # APEX-SLIP-V1-2026-09-06 (mixed)
'''
A5_NEW = r'''                   "prob_cal",                   # APEX-ACESCAL-TRK-2026-09-09
                   "slip_slot", "slip_reason",   # APEX-SLIP-V1-2026-09-06 (mixed)
'''
A6_OLD = r'''                            "probability": p.get("prob", ""),
'''
A6_NEW = r'''                            "probability": p.get("prob", ""),
                            "prob_cal": p.get("prob_cal", p.get("prob", "")),
'''
ANCHORS = [("A2", A2_OLD, A2_NEW), ("A1", A1_OLD, A1_NEW), ("A3", A3_OLD, A3_NEW),
           ("A4", A4_OLD, A4_NEW), ("A5", A5_OLD, A5_NEW), ("A6", A6_OLD, A6_NEW)]

def sha(p): return hashlib.sha256(open(p, "rb").read()).hexdigest()
def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "--check"
    src = open(F, encoding="utf-8").read(); s = sha(F)
    assert s == PIN, f"SHA mismatch: {s}"; assert MARK not in src, "already applied"
    for n, o, _ in ANCHORS:
        c = src.count(o); assert c == 1, f"anchor {n} matched {c}x"
    print("CHECK OK: SHA pinned, anchors 6/6 unique")
    if mode != "--apply": return
    bak = F + ".bak_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + "_preacescal"; shutil.copy2(F, bak)
    new = src
    for _, o, nw in ANCHORS: new = new.replace(o, nw, 1)
    open(F, "w", encoding="utf-8").write(new)
    try: py_compile.compile(F, doraise=True)
    except Exception as e: shutil.copy2(bak, F); print("py_compile FAILED -> restored:", e); sys.exit(1)
    print("APPLIED. backup:", bak); print("new sha:", sha(F))
if __name__ == "__main__": main()
