"""APEX-SETTLEKEY-2026-08-31 -- settle_log matched on surname substring +
category + line, first hit wins. No date, no match identity. Two 08-28
matches sharing a 21.5 total_games line had actuals swapped."""
import hashlib, os, shutil, sys, time, py_compile

TARGET = os.path.expanduser("~/openclaw/apex_edge_tracker.py")

OLD3 = '''def settle_log(sim_log=SIM_LOG, hand_log=HAND_LOG, dry=False):'''

HELPERS = '''def _settle_pair(player, opponent):
    """APEX-SETTLEKEY: unordered name set. Match-level rows keep the pair in
    `opponent` ("A v B"); player rows are simply {player, opponent}."""
    p = _norm(player); o = str(opponent or "")
    if p == "match" or " v " in o or " vs " in o:
        for sep in (" vs ", " v. ", " v "):
            if sep in o:
                a, b = o.split(sep, 1)
                return frozenset([_norm(a), _norm(b)])
    return frozenset([p, _norm(o)])


def _pair_eq(pa, pb):
    """Equal, or equal allowing one truncated name (token subset either way)."""
    if pa == pb:
        return True
    if len(pa) != 2 or len(pb) != 2:
        return False
    la, lb = list(pa), list(pb)
    def sub(x, y):
        sx, sy = set(x.split()), set(y.split())
        return bool(sx & sy) and (sx <= sy or sy <= sx)
    return ((sub(la[0], lb[0]) and sub(la[1], lb[1])) or
            (sub(la[0], lb[1]) and sub(la[1], lb[0])))


def settle_log(sim_log=SIM_LOG, hand_log=HAND_LOG, dry=False):'''

OLD = '''    hand = [r for r in _read(hand_log) if str(r.get("in_forward_log", "0")).strip() == "1"]
    n = 0
    for h in hand:
        line = _f(h.get("line")); actual = _f(h.get("actual"))
        if actual is None:
            continue   # APEX-SETTLELOG-001: VOID/no-result rows carry no actual by design
        for r in rows:
            if r.get("actual") or r.get("category") != h["category"] or _f(r.get("line")) != line:
                continue
            names = [_norm(r.get("player"))] + [_norm(x) for x in (r.get("opponent") or "").split(" v ")]
            if not any(_norm(h["player"]).split()[-1] in nm for nm in names):
                continue
            r["actual"] = ("%.1f" if h["category"] == "fantasy_score" else "%.0f") % actual
            r["settled_ts"] = datetime.now().isoformat(timespec="seconds") + "-hand"
            n += 1
            break
    if n and not dry:'''

NEW = '''    hand = [r for r in _read(hand_log) if str(r.get("in_forward_log", "0")).strip() == "1"]
    n = 0; amb = []
    for h in hand:
        line = _f(h.get("line")); actual = _f(h.get("actual"))
        if actual is None:
            continue   # APEX-SETTLELOG-001: VOID/no-result rows carry no actual by design
        hpair = _settle_pair(h.get("player"), h.get("opponent"))
        hdate = (h.get("match_date") or "").strip()
        cands = []
        for r in rows:
            if r.get("actual") or r.get("category") != h["category"] or _f(r.get("line")) != line:
                continue
            if (r.get("match_date") or "").strip() != hdate:
                continue
            if not _pair_eq(hpair, _settle_pair(r.get("player"), r.get("opponent"))):
                continue
            cands.append(r)
        if not cands:
            continue
        exact = [r for r in cands if _norm(r.get("player")) == _norm(h.get("player"))]
        if len(exact) == 1:
            r = exact[0]
        elif len(cands) == 1:
            r = cands[0]
        else:
            amb.append("%s %s %s line=%s -> %d candidates, REFUSED"
                       % (hdate, h.get("player"), h.get("category"), h.get("line"), len(cands)))
            continue
        r["actual"] = ("%.1f" if h["category"] == "fantasy_score" else "%.0f") % actual
        r["settled_ts"] = datetime.now().isoformat(timespec="seconds") + "-hand"
        n += 1
    if n and not dry:'''

OLD2 = '''    return "settled %d row(s) from hand grades%s" % (n, " (dry run)" if dry else "")'''

NEW2 = '''    msg = "settled %d row(s) from hand grades%s" % (n, " (dry run)" if dry else "")
    if amb:
        msg += "\\n%d AMBIGUOUS, nothing written:\\n  " % len(amb) + "\\n  ".join(amb)
    return msg'''


def sha256(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def main():
    src = open(TARGET, encoding="utf-8").read()
    print("current sha : %s" % sha256(TARGET))
    bad = []
    if "APEX-SETTLEKEY" in src:
        bad.append("marker present -- refusing double-apply")
    for nm, s in (("body", OLD), ("return", OLD2), ("def", OLD3)):
        c = src.count(s)
        print("  %-8s anchor %d (need 1)" % (nm, c))
        if c != 1:
            bad.append("%s matched %d times" % (nm, c))
    if bad:
        print("")
        for b in bad: print("BLOCKED: %s" % b)
        sys.exit(1)
    if "--apply" not in sys.argv:
        print("")
        print("ALL CHECKS READY -- rerun with --apply to write")
        return
    stamp = time.strftime("%Y%m%d_%H%M%S")
    backup = "%s.bak_%s_presettlekey" % (TARGET, stamp)
    shutil.copy2(TARGET, backup)
    print("backup      : %s" % os.path.basename(backup))
    out = src.replace(OLD3, HELPERS, 1).replace(OLD, NEW, 1).replace(OLD2, NEW2, 1)
    open(TARGET, "w", encoding="utf-8").write(out)
    try:
        py_compile.compile(TARGET, doraise=True)
    except Exception as e:
        shutil.copy2(backup, TARGET)
        print("COMPILE FAILED -- backup restored"); print(e); sys.exit(1)
    print("py_compile  : OK")
    print("new sha     : %s" % sha256(TARGET))
    print("APPLIED")


main()
