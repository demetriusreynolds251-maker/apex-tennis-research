"""APEX-CONF-BLOCKFIX-2026-08-31

The APEX-CONF-001 patch left one line in the wrong function. In
best_bets_block the dict carries "conf": cf, "ctier": ctier, "cwhy": cwhy,
but cf / ctier / cwhy are never assigned there -- the apex_confidence call
went into best_bets_detail only. First pick raises NameError, the bare
except returns "", and the nightly picks-channel embed silently renders
nothing.

This removes that one line. best_bets_block returns to its 2026-08-29
behaviour: APEX-only ordering, which is all it ever displayed anyway.
Nothing else is touched.
"""
import hashlib, os, shutil, sys, time, py_compile

TARGET = os.path.expanduser("~/openclaw/apex_edge_tracker.py")
PINNED = "402c6d9cb7506050811973f7355d2335a60edfbb09cfad732d074ec2b695795c"
NEEDLE = '"conf": cf, "ctier": ctier, "cwhy": cwhy,'


def sha256(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def span(lines, name):
    start = None
    for i, l in enumerate(lines):
        if l.startswith("def %s(" % name):
            start = i
            break
    if start is None:
        return None, None
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if lines[j].startswith("def "):
            end = j
            break
    return start, end


def checks():
    problems = []
    if not os.path.exists(TARGET):
        return None, None, ["target not found: %s" % TARGET]
    cur = sha256(TARGET)
    print("current sha : %s" % cur)
    print("pinned sha  : %s" % PINNED)
    if cur != PINNED and "--force" not in sys.argv:
        problems.append("file has changed since this patch was written "
                        "(rerun with --force only if you know why)")
    lines = open(TARGET, encoding="utf-8").read().split("\n")
    hits = [i for i, l in enumerate(lines) if l.strip() == NEEDLE]
    print("stray-line hits: %d" % len(hits))
    if len(hits) != 1:
        problems.append("expected exactly 1 stray line, found %d" % len(hits))
        return lines, None, problems
    idx = hits[0]
    bstart, bend = span(lines, "best_bets_block")
    dstart, dend = span(lines, "best_bets_detail")
    print("best_bets_block  lines %s-%s" % (bstart, bend))
    print("best_bets_detail lines %s-%s" % (dstart, dend))
    print("stray line is line %d (1-based %d)" % (idx, idx + 1))
    if bstart is None:
        problems.append("best_bets_block not found")
    elif not (bstart < idx < bend):
        problems.append("stray line is NOT inside best_bets_block -- refusing")
    calls = [l for l in lines[bstart:bend] if "apex_confidence(" in l]
    print("apex_confidence calls inside best_bets_block: %d" % len(calls))
    if calls:
        problems.append("best_bets_block DOES call apex_confidence -- "
                        "the diagnosis does not hold, refusing")
    if dstart is not None:
        dcalls = [l for l in lines[dstart:dend] if "apex_confidence(" in l]
        print("apex_confidence calls inside best_bets_detail: %d" % len(dcalls))
        if not dcalls:
            problems.append("best_bets_detail does NOT call apex_confidence -- "
                            "unexpected state, refusing")
    return lines, idx, problems


def main():
    lines, idx, problems = checks()
    if problems:
        print("")
        for p in problems:
            print("BLOCKED: %s" % p)
        sys.exit(1)
    print("")
    print("removing: %s" % lines[idx].rstrip())
    if "--apply" not in sys.argv:
        print("")
        print("ALL CHECKS READY -- rerun with --apply to write")
        return
    stamp = time.strftime("%Y%m%d_%H%M%S")
    backup = "%s.bak_%s_preblockfix" % (TARGET, stamp)
    shutil.copy2(TARGET, backup)
    print("backup      : %s" % backup)
    print("backup sha  : %s" % sha256(backup))
    out = lines[:idx] + lines[idx + 1:]
    open(TARGET, "w", encoding="utf-8").write("\n".join(out))
    try:
        py_compile.compile(TARGET, doraise=True)
    except Exception as e:
        shutil.copy2(backup, TARGET)
        print("COMPILE FAILED -- backup restored")
        print(e)
        sys.exit(1)
    print("py_compile  : OK")
    print("new sha     : %s" % sha256(TARGET))
    print("APPLIED")


main()
