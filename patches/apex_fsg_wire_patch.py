#!/usr/bin/env python3
"""APEX-FSG-COLLECT-WIRE-2026-09-04
Route 1st_set_* props to apex_firstset_collect BEFORE the price feed, decline
with the research reason, never map them into the engine.
Usage: python3 apex_fsg_wire_patch.py --check | --apply"""
import hashlib, os, shutil, sys, py_compile, datetime
F    = "openclaw_core.py"
PIN  = "6caa08708d088e839bcd35f11b5997a56df9daf2d14c50d76cdb90ed7c5d6b2b"
MARK = "APEX-FSG-COLLECT-WIRE-2026-09-04"

A1_OLD = r'''_APEX_MATCH_LEVEL = {"total_games", "total_sets", "tiebreaks", "first_set_games",
'''
A1_NEW = r'''# APEX-FSG-COLLECT-WIRE-2026-09-04: first-set slugs are RESEARCH COLLECTION.
# Intercepted in _apex_engine_pick before the price feed; never mapped into the
# engine (no validated projection method). Collector: apex_firstset_collect.py
_APEX_FIRSTSET_SLUGS = {"1st_set_total_games", "1st_set_total_games_won",
                        "1st_set_games_won", "1st_set_aces", "1st_set_double_faults",
                        "1st_set_breaks", "1st_set_winner"}
_APEX_MATCH_LEVEL = {"total_games", "total_sets", "tiebreaks", "first_set_games",
'''

A2_OLD = r'''    try:
        # --- APEX-PRICE-AUTO-2026-08-24: names first -- the price feed needs the pair,
'''
A2_NEW = r'''    try:
        # --- APEX-FSG-COLLECT-WIRE-2026-09-04: first-set research collection.
        # Runs BEFORE the price feed so unpriced matches are still collected.
        try:
            _fs = str(prop.get("stat_type", "")).strip().lower().replace(" ", "_")
            if _fs in _APEX_FIRSTSET_SLUGS:
                import apex_firstset_collect as _afc
                _fr = _afc.record(
                    prop,
                    match_date=prop.get("match_date") or prop.get("date") or "",
                    tournament=prop.get("tournament", ""),
                    best_of=5 if str(prop.get("match_format", "")).lower() == "bo5" else 3,
                    wta=1 if str(prop.get("tour", "")).lower() == "wta" else 0,
                    surface=prop.get("surface", ""))
                _apex_decline(prop, f"declined ({prop.get('player', '?')}): "
                              f"first-set research collection (no projection method yet) [{_fr}]")
                return None
        except Exception as _fe:
            log("ApexEngine", f"first-set collect error ({type(_fe).__name__}: {_fe}) -> falling through")
        # --- APEX-PRICE-AUTO-2026-08-24: names first -- the price feed needs the pair,
'''

def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()

def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "--check"
    src = open(F).read()
    s = sha(F)
    assert s == PIN, f"SHA mismatch: {s}"
    assert MARK not in src, "already applied"
    for name, old in (("A1", A1_OLD), ("A2", A2_OLD)):
        n = src.count(old)
        assert n == 1, f"anchor {name} matched {n}x (need exactly 1)"
    assert os.path.exists("apex_firstset_collect.py"), "apex_firstset_collect.py missing"
    print("CHECK OK: SHA pinned, anchors 2/2 unique, collector present")
    if mode != "--apply":
        return
    bak = F + ".bak_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + "_prefsgwire"
    shutil.copy2(F, bak)
    new = src.replace(A1_OLD, A1_NEW, 1).replace(A2_OLD, A2_NEW, 1)
    with open(F, "w") as fh:
        fh.write(new)
    try:
        py_compile.compile(F, doraise=True)
    except Exception as e:
        shutil.copy2(bak, F)
        print("py_compile FAILED -> restored from backup:", e)
        sys.exit(1)
    print("APPLIED. backup:", bak)
    print("new sha:", sha(F))

if __name__ == "__main__":
    main()
