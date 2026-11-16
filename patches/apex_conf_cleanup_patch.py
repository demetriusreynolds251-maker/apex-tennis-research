"""APEX-CONF-CLEANUP-2026-08-31

Two changes to apex_confidence(), both ordered by the operator to remove
double-counting before RANK SCORE multiplies by it.

  A. Component 5 warning filter drops "artifact" and "untested".
     "artifact" fires at prob >= 0.95, so belief was leaking into trust.
     "untested" is already scored by component 1 (category sample size).
     "narrow" and "overconfident" stay -- genuine model-quality signals.

  B. Component 6 (selection-quality, 0-15) removed entirely. It claimed to
     be per-category but counted global outcomes; making it per-category
     would pay a second time for the sample size component 1 already
     scores. Max points therefore drop 100 -> 85 before penalties.

APEX SCORE is not touched. Nothing outside apex_confidence is touched.
"""
import hashlib, os, shutil, sys, time, py_compile

BASE   = os.path.expanduser("~/openclaw")
TARGET = os.path.join(BASE, "apex_edge_tracker.py")
PINNED = "557b4faf5c142fd5fcc71055f178232f82156e8c2dacc1cc15991d0cea6d8481"

OLD_FILTER = '''    w = [x for x in (warnings or []) if "narrow" in str(x).lower() or "artifact" in str(x).lower()
         or "untested" in str(x).lower() or "overconfident" in str(x).lower()]'''

NEW_FILTER = '''    # APEX-CONF-CLEANUP-2026-08-31: "artifact" (fires at prob >= 0.95) let
    # belief into trust; "untested" duplicates component 1. Both removed.
    w = [x for x in (warnings or []) if "narrow" in str(x).lower()
         or "overconfident" in str(x).lower()]'''

OLD_C6 = '''    # 6. selection-quality evidence for this category (0-15)
    try:
        import apex_selection_quality as _SQ
        if len(_SQ._outcomes()) >= 25: pts += 15
        elif len(_SQ._outcomes()) >= 10: pts += 8
        else: why.append("selection quality unmeasured")
    except Exception: why.append("selection quality unavailable")
'''

NEW_C6 = '''    # 6. REMOVED APEX-CONF-CLEANUP-2026-08-31: selection-quality scored a
    #    global outcome count while claiming to be per-category, and a
    #    per-category version would double-pay for component 1's evidence.
'''


def sha256(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def snapshot(tag):
    """Per-pick CONFIDENCE from the live deduped board. Returns list of rows."""
    sys.path.insert(0, BASE)
    for m in ("apex_edge_tracker", "apex_selection_quality"):
        sys.modules.pop(m, None)
    import apex_edge_tracker as t
    picks, note = t.load_current_board()
    if note:
        print("%s: board note: %s" % (tag, note))
        return []
    rec = t.records()
    rows = []
    for p in picks:
        cat = p.get("category")
        if not cat:
            continue
        sc, ev, lvl, up, down = t.apex_score(p.get("prob"), cat, bool(p.get("bo5")), rec)
        try:
            import apex_card_index as _CI
            card = _CI.lookup(str(p.get("player") or ""), cat, str(p.get("match_date") or ""))[0]
        except Exception:
            card = None
        cf, ctier, cwhy = t.apex_confidence(cat, bool(p.get("bo5")), rec,
                                            warnings=down, card_present=bool(card))
        rows.append({"key": "%s|%s|%s" % (p.get("player"), cat, p.get("line")),
                     "apex": sc, "conf": cf, "tier": ctier})
    return rows


def main():
    if not os.path.exists(TARGET):
        print("BLOCKED: target not found")
        sys.exit(1)
    cur = sha256(TARGET)
    print("current sha : %s" % cur)
    print("pinned sha  : %s" % PINNED)
    src = open(TARGET, encoding="utf-8").read()
    problems = []
    if cur != PINNED and "--force" not in sys.argv:
        problems.append("file changed since this patch was written")
    nf = src.count(OLD_FILTER)
    nc = src.count(OLD_C6)
    print("warning-filter block hits : %d (need 1)" % nf)
    print("component-6 block hits    : %d (need 1)" % nc)
    if nf != 1:
        problems.append("warning filter not matched exactly once")
    if nc != 1:
        problems.append("component 6 not matched exactly once")
    if problems:
        print("")
        for p in problems:
            print("BLOCKED: %s" % p)
        sys.exit(1)

    print("")
    print("capturing CONFIDENCE before ...")
    before = snapshot("before")
    print("captured %d picks" % len(before))

    if "--apply" not in sys.argv:
        print("")
        print("ALL CHECKS READY -- rerun with --apply to write")
        return

    stamp = time.strftime("%Y%m%d_%H%M%S")
    backup = "%s.bak_%s_preconfcleanup" % (TARGET, stamp)
    shutil.copy2(TARGET, backup)
    print("backup      : %s" % backup)
    out = src.replace(OLD_FILTER, NEW_FILTER).replace(OLD_C6, NEW_C6)
    open(TARGET, "w", encoding="utf-8").write(out)
    try:
        py_compile.compile(TARGET, doraise=True)
    except Exception as e:
        shutil.copy2(backup, TARGET)
        print("COMPILE FAILED -- backup restored")
        print(e)
        sys.exit(1)
    print("py_compile  : OK")
    print("new sha     : %s" % sha256(TARGET))

    print("")
    print("capturing CONFIDENCE after ...")
    after = {r["key"]: r for r in snapshot("after")}
    print("")
    print("%-46s %5s  %-22s %-22s" % ("PICK", "APEX", "CONF BEFORE", "CONF AFTER"))
    print("-" * 100)
    deltas = []
    for b in before:
        a = after.get(b["key"])
        if not a:
            continue
        d = a["conf"] - b["conf"]
        deltas.append(d)
        print("%-46s %5d  %3d (%-10s)      %3d (%-10s) %+d"
              % (b["key"][:46], b["apex"], b["conf"], b["tier"], a["conf"], a["tier"], d))
    if deltas:
        print("-" * 100)
        print("picks compared %d | mean change %+.1f | min %+d | max %+d"
              % (len(deltas), sum(deltas) / float(len(deltas)), min(deltas), max(deltas)))
        print("APEX SCORE column must be identical to before -- it is not an input here.")
    print("APPLIED")


main()
