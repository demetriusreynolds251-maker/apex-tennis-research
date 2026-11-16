#!/usr/bin/env python3
"""APEX-SETTLE-SA365-ARCHIVE -- keep our own copy of every stat sheet the grader fetches
(SportsAPI365 deletes them after some days). Saved copy is read first on later runs.
Usage: python3 apex_settle_sa365_fix2.py --check | --apply"""
import sys, shutil, py_compile, datetime
F = "apex_settle_sa365.py"; MARK = "APEX-SETTLE-SA365-ARCHIVE"
A1_OLD = '''def stat_sheet(ev):
    eid = ev["id"]
    if eid not in _st_cache:
        p, err = api("/extend/api/event/get/statistics/%s" % eid); time.sleep(0.25)
        _st_cache[eid] = (((p or {}).get("result") or {}), err)
    return _st_cache[eid]'''
A1_NEW = '''SHEETS = Path(__file__).resolve().parent / "data" / "sa365_sheets"   # APEX-SETTLE-SA365-ARCHIVE

def stat_sheet(ev):
    eid = ev["id"]
    if eid not in _st_cache:
        f = SHEETS / ("%s.json" % eid)
        if f.exists():
            try:
                _st_cache[eid] = (json.loads(f.read_text()), None)
                return _st_cache[eid]
            except Exception:
                pass
        p, err = api("/extend/api/event/get/statistics/%s" % eid); time.sleep(0.25)
        res = ((p or {}).get("result") or {})
        if (res.get("statistics") or {}).get("ALL"):
            try:
                SHEETS.mkdir(parents=True, exist_ok=True)
                keep = dict(res)
                keep["_event"] = {k: ev.get(k) for k in ("id", "name", "participant1", "participant2", "league", "score", "status")}
                keep["_saved"] = dt.datetime.now().isoformat(timespec="seconds")
                f.write_text(json.dumps(keep))
            except Exception:
                pass
        _st_cache[eid] = (res, err)
    return _st_cache[eid]'''
def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "--check"
    src = open(F, encoding="utf-8").read()
    assert MARK not in src, "already applied"
    c = src.count(A1_OLD); assert c == 1, f"anchor A1 matched {c}x"
    print("CHECK OK: anchor 1/1 unique")
    if mode != "--apply": return
    bak = F + ".bak_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + "_prefix2"; shutil.copy2(F, bak)
    open(F, "w", encoding="utf-8").write(src.replace(A1_OLD, A1_NEW, 1))
    try: py_compile.compile(F, doraise=True)
    except Exception as e: shutil.copy2(bak, F); print("py_compile FAILED -> restored:", e); sys.exit(1)
    print("APPLIED. backup:", bak)
if __name__ == "__main__": main()
