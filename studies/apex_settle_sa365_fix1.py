#!/usr/bin/env python3
"""APEX-SETTLE-SA365-PREFER-ENDED -- (1) when several records exist for a match, use the
finished one; (2) a match SportsAPI365 marks Cancelled is treated like a walkover (VOID).
Usage: python3 apex_settle_sa365_fix1.py --check | --apply"""
import sys, shutil, py_compile, datetime
F = "apex_settle_sa365.py"; MARK = "APEX-SETTLE-SA365-PREFER-ENDED"
A1_OLD = '''            if not ev.get("id"):
                continue
            if same_player(player, ev.get("participant1")):
                side = 1
            elif same_player(player, ev.get("participant2")):
                side = 2
            else:
                continue
            out = (ev, side, "found %s%s" % (d, "" if n == 0 else " (%+dd)" % n))
            _ev_cache[key] = out; return out
    out = (None, None,'''
A1_NEW = '''            if not ev.get("id") or ev["id"] in seen_ids:
                continue
            if same_player(player, ev.get("participant1")):
                side = 1
            elif same_player(player, ev.get("participant2")):
                side = 2
            else:
                continue
            seen_ids.add(ev["id"])
            note = "found %s%s" % (d, "" if n == 0 else " (%+dd)" % n)
            if str(ev.get("status") or "").strip().lower() == "ended":
                out = (ev, side, note); _ev_cache[key] = out; return out
            hits.append((ev, side, note))
    if hits:   # APEX-SETTLE-SA365-PREFER-ENDED: no finished record -- report a non-cancelled one first
        keep = [h for h in hits if "cancel" not in str(h[0].get("status") or "").lower()]
        out = (keep or hits)[0]; _ev_cache[key] = out; return out
    out = (None, None,'''
A2_OLD = '''    last_err = ""
    for n in (0, -1, 1, -2, 2):'''
A2_NEW = '''    last_err = ""
    hits, seen_ids = [], set()
    for n in (0, -1, 1, -2, 2):'''
A3_OLD = '''    if "ret" in st:
        return "RET"
    if st != "ended":'''
A3_NEW = '''    if "ret" in st:
        return "RET"
    if "cancel" in st:
        return "CANCELLED"
    if st != "ended":'''
A4_OLD = '''    if flag in ("RET", "WO"):
        return None, "VOID needed (%s) score %s" % (flag, ev.get("score"))'''
A4_NEW = '''    if flag in ("RET", "WO", "CANCELLED"):
        return None, "VOID needed (%s) score %s" % (flag, ev.get("score"))'''
ANCHORS = [("A1", A1_OLD, A1_NEW), ("A2", A2_OLD, A2_NEW), ("A3", A3_OLD, A3_NEW), ("A4", A4_OLD, A4_NEW)]
def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "--check"
    src = open(F, encoding="utf-8").read()
    assert MARK not in src, "already applied"
    for n, o, _ in ANCHORS:
        c = src.count(o); assert c == 1, f"anchor {n} matched {c}x"
    print("CHECK OK: anchors 4/4 unique")
    if mode != "--apply": return
    bak = F + ".bak_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + "_prefix1"; shutil.copy2(F, bak)
    new = src
    for _, o, nw in ANCHORS: new = new.replace(o, nw, 1)
    open(F, "w", encoding="utf-8").write(new)
    try: py_compile.compile(F, doraise=True)
    except Exception as e: shutil.copy2(bak, F); print("py_compile FAILED -> restored:", e); sys.exit(1)
    print("APPLIED. backup:", bak)
if __name__ == "__main__": main()
