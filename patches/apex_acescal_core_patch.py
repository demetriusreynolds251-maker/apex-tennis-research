#!/usr/bin/env python3
"""APEX-ACESCAL-2026-09-09 (core) -- measured calibration correction on ACES LESS.
Holdout study (2010-2026, 11,341 matches, fit<=2021/tune 22-23/holdout 2024+): aces LESS
runs under its stated probability in EVERY band -- favourite -0.020, underdog -0.035.
DFs showed no bias (+/-0.01) and is untouched. This is the FIRST measured correction to enter
the belief channel; APEX had been pure frozen-model output since 08-23. Frozen artifacts are
NOT edited -- the correction is applied downstream of the simulator, both numbers are printed,
and the raw prob stays in the log so the correction itself remains checkable.
Usage: python3 apex_acescal_core_patch.py --check | --apply"""
import hashlib, shutil, sys, py_compile, datetime, csv
F = "openclaw_core.py"; PIN = "850aed9752293b2e08716e6a1ebf2cd2d47a73ccef669d0de8be71f3b0f5e0b5"
MARK = "APEX-ACESCAL-2026-09-09"; PICKS = "apex_engine_picks_log_v1.csv"

A1_OLD = r'''                     "playable", "slip_start_utc",   # APEX-PLAYABLE-2026-08-31
                     "prop_type"]                    # APEX-PROPTYPE-2026-09-08
'''
A1_NEW = r'''                     "playable", "slip_start_utc",   # APEX-PLAYABLE-2026-08-31
                     "prop_type",                    # APEX-PROPTYPE-2026-09-08
                     "prob_cal"]                     # APEX-ACESCAL-2026-09-09
'''
A2_OLD = r'''                "direction": direction, "prob": f(prob, "%.4f"), "tier": str(t.get("tier") or ""),
'''
A2_NEW = r'''                "direction": direction, "prob": f(prob, "%.4f"),
                "prob_cal": f(_apex_prob_cal(prob, cat, direction, is_fav), "%.4f"),   # APEX-ACESCAL-2026-09-09
                "tier": str(t.get("tier") or ""),
'''
A3_OLD = r'''def _apex_decline(prop, msg):
'''
A3_NEW = r'''# APEX-ACESCAL-2026-09-09: measured bias on aces LESS (see patch docstring). Applied
# downstream of the frozen simulator; never changes the simulator's own output.
_ACESCAL = {1: 0.020, 0: 0.035, -1: 0.035}   # is_fav 1 = favourite, 0 = underdog, -1 = match-level

def _apex_prob_cal(prob, cat, direction, is_fav):
    """Calibrated probability: raw, minus the measured aces-LESS bias. Other
    categories and MORE picks return the raw value unchanged. Never raises."""
    try:
        p = float(prob)
        if str(cat) != "aces" or str(direction).upper() != "LESS":
            return p
        return max(0.50, min(p, p - _ACESCAL.get(int(is_fav), 0.035)))
    except Exception:
        return prob


def _apex_decline(prop, msg):
'''
A4_OLD = r'''            f"Probability **{100*prob:.0f}%**   Edge {t['edge']:+.1f}   "
            f"Confidence {t['confidence']}",
'''
A4_NEW = r'''            (f"Probability **{100*prob:.0f}%**   Edge {t['edge']:+.1f}   "
             f"Confidence {t['confidence']}")
            if _pcal >= prob - 1e-9 else
            (f"Probability **{100*prob:.0f}%** \u00b7 calibrated **{100*_pcal:.0f}%**   "
             f"Edge {t['edge']:+.1f}   Confidence {t['confidence']}"),
'''
A5_OLD = r'''        if _push >= 0.02:
'''
A5_NEW = r'''        if _pcal < prob - 1e-9:                      # APEX-ACESCAL-2026-09-09
            L.append(f"\u26a0\ufe0f aces LESS runs {100*(prob-_pcal):.1f} pts under its stated probability "
                     f"(measured on 11,341 holdout matches) -- the calibrated figure is what "
                     f"break-even, APEX and RANK use")
        if _push >= 0.02:
'''

A6_OLD = r'''        L += [
            "**EXPERIMENTAL · FORWARD TEST ACTIVE**",
'''
A6_NEW = r'''        _pcal = _apex_prob_cal(prob, t.get("category"), side, res.get("is_fav", -1))   # APEX-ACESCAL
        L += [
            "**EXPERIMENTAL · FORWARD TEST ACTIVE**",
'''
ANCHORS = [("A1", A1_OLD, A1_NEW), ("A3", A3_OLD, A3_NEW), ("A2", A2_OLD, A2_NEW),
           ("A6", A6_OLD, A6_NEW), ("A4", A4_OLD, A4_NEW), ("A5", A5_OLD, A5_NEW)]

def sha(p): return hashlib.sha256(open(p, "rb").read()).hexdigest()
def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "--check"
    src = open(F, encoding="utf-8").read(); s = sha(F)
    assert s == PIN, f"SHA mismatch: {s}"; assert MARK not in src, "already applied"
    for n, o, _ in ANCHORS:
        c = src.count(o); assert c == 1, f"anchor {n} matched {c}x"
    i = src.index(A2_OLD); assert "is_fav" in src[i-3000:i], "is_fav not in scope at pick_row"
    print("CHECK OK: SHA pinned, anchors 6/6 unique, is_fav in scope")
    if mode != "--apply": return
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = F + ".bak_" + stamp + "_preacescal"; shutil.copy2(F, bak)
    new = src
    for _, o, nw in ANCHORS: new = new.replace(o, nw, 1)
    open(F, "w", encoding="utf-8").write(new)
    try: py_compile.compile(F, doraise=True)
    except Exception as e: shutil.copy2(bak, F); print("py_compile FAILED -> restored:", e); sys.exit(1)
    hdr = open(PICKS, newline="").readline().strip().split(",")
    if "prob_cal" not in hdr:
        shutil.copy2(PICKS, PICKS + ".bak_" + stamp + "_preacescal")
        rows = list(csv.DictReader(open(PICKS, newline="")))
        with open(PICKS, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=hdr + ["prob_cal"]); w.writeheader()
            for r in rows: r["prob_cal"] = r.get("prob", ""); w.writerow(r)
        print(f"picks log migrated: {len(rows)} rows, +prob_cal (backfilled = raw prob)")
    print("APPLIED. backup:", bak); print("new sha:", sha(F))
if __name__ == "__main__": main()
