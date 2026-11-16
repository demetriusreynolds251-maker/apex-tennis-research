#!/usr/bin/env python3
"""APEX-PROPTYPE-2026-09-08 -- log prop_type (standard/goblin/demon/red_demon) on every pick row.
Usage: python3 apex_proptype_patch.py --check | --apply"""
import hashlib, shutil, sys, py_compile, datetime, csv, os
F = "openclaw_core.py"; PIN = "850aed9752293b2e08716e6a1ebf2cd2d47a73ccef669d0de8be71f3b0f5e0b5"
MARK = "APEX-PROPTYPE-2026-09-08"; PICKS = "apex_engine_picks_log_v1.csv"
A1_OLD = r'''                     "playable", "slip_start_utc"]   # APEX-PLAYABLE-2026-08-31
'''
A1_NEW = r'''                     "playable", "slip_start_utc",   # APEX-PLAYABLE-2026-08-31
                     "prop_type"]                    # APEX-PROPTYPE-2026-09-08
'''
A2_OLD = r'''    pick_row = {"playable": _playable,
'''
A2_NEW = r'''    pick_row = {"playable": _playable,
                "prop_type": _ptype,                     # APEX-PROPTYPE-2026-09-08
'''
def sha(p): return hashlib.sha256(open(p, "rb").read()).hexdigest()
def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "--check"
    src = open(F, encoding="utf-8").read(); s = sha(F)
    assert s == PIN, f"SHA mismatch: {s}"; assert MARK not in src, "already applied"
    for n, o in (("A1", A1_OLD), ("A2", A2_OLD)):
        c = src.count(o); assert c == 1, f"anchor {n} matched {c}x"
    i = src.index(A2_OLD); assert '_ptype = str(prop.get("prop_type_classified")' in src[i - 1500:i], "_ptype not defined above pick_row"
    hdr = open(PICKS, newline="").readline().strip().split(",")
    print("CHECK OK: SHA pinned, anchors 2/2, _ptype in scope; picks log has prop_type:", "prop_type" in hdr)
    if mode != "--apply": return
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = F + ".bak_" + stamp + "_preproptype"; shutil.copy2(F, bak)
    open(F, "w", encoding="utf-8").write(src.replace(A1_OLD, A1_NEW, 1).replace(A2_OLD, A2_NEW, 1))
    try: py_compile.compile(F, doraise=True)
    except Exception as e: shutil.copy2(bak, F); print("py_compile FAILED -> restored:", e); sys.exit(1)
    if "prop_type" not in hdr:
        shutil.copy2(PICKS, PICKS + ".bak_" + stamp + "_preproptype")
        rows = list(csv.DictReader(open(PICKS, newline="")))
        with open(PICKS, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=hdr + ["prop_type"]); w.writeheader()
            for r in rows: r["prop_type"] = ""; w.writerow(r)
        print(f"picks log migrated: {len(rows)} rows, +prop_type column")
    print("APPLIED. backup:", bak); print("new sha:", sha(F))
if __name__ == "__main__": main()
