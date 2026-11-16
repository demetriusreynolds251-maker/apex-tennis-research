"""APEX-PROPCLASS-2026-08-31

classify_prop_type() and filter_props() are fully built -- goblin / red_demon
/ demon detection, MORE-only locking, the GREEN-minimum warnings at 3327-3328,
the demon skip. filter_props is called from exactly ONE place: supervisor_agent
(the batch pipeline). The manual screenshot path never calls it, so
prop_type_classified is never set and every downstream check reads a missing
field and defaults to "standard".

Result: goblins and red demons were evaluated as standard props, so the engine
could return LESS on a MORE-only prop -- unplayable on the slip -- and none of
the goblin/demon rules ever fired. Zero occurrences of prop_type in the bot log
confirm it has never run on this path.

Adds the filter_props call to the screenshot path, after the props list is
built and before the V8 prefetch.
"""
import hashlib, os, shutil, sys, time, py_compile

TARGET = os.path.expanduser("~/openclaw/openclaw_core.py")

OLD = '''    # ── Pre-fetch V8 packet ONCE for all props on this card ──────'''

NEW = '''    # APEX-PROPCLASS-2026-08-31: classify goblin / red demon / standard.
    # filter_props sets prop_type_classified, locks MORE-only props to
    # direction_locked="MORE" and both_directions_available=False, and drops
    # legacy demons. Without this the engine can pick LESS on a prop where
    # only MORE is offered. Fail-open: any error leaves props untouched.
    try:
        _before = len(props)
        props = filter_props(props, dates)
        log("Manual", "prop types: %s" % ", ".join(
            "%s=%s" % (p.get("player"), p.get("prop_type_classified"))
            for p in props))
        if len(props) != _before:
            log("Manual", "filter_props dropped %d prop(s)" % (_before - len(props)))
    except Exception as _e:
        log("Manual", "prop classification skipped (%s) -- props unchanged"
            % type(_e).__name__)

    # ── Pre-fetch V8 packet ONCE for all props on this card ──────'''


def sha256(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def main():
    src = open(TARGET, encoding="utf-8").read()
    print("current sha : %s" % sha256(TARGET))
    bad = []
    if "APEX-PROPCLASS" in src:
        bad.append("marker present -- refusing double-apply")
    n = src.count(OLD)
    print("anchor hits : %d (need 1)" % n)
    if n != 1:
        bad.append("anchor matched %d times" % n)
    for name in ("def filter_props", "def classify_prop_type"):
        print("  %-24s present: %s" % (name, name in src))
        if name not in src:
            bad.append("%s missing" % name)
    if bad:
        print("")
        for b in bad: print("BLOCKED: %s" % b)
        sys.exit(1)
    if "--apply" not in sys.argv:
        print("")
        print("ALL CHECKS READY -- rerun with --apply to write")
        return
    stamp = time.strftime("%Y%m%d_%H%M%S")
    backup = "%s.bak_%s_prepropclass" % (TARGET, stamp)
    shutil.copy2(TARGET, backup)
    print("backup      : %s" % os.path.basename(backup))
    open(TARGET, "w", encoding="utf-8").write(src.replace(OLD, NEW, 1))
    try:
        py_compile.compile(TARGET, doraise=True)
    except Exception as e:
        shutil.copy2(backup, TARGET)
        print("COMPILE FAILED -- backup restored"); print(e); sys.exit(1)
    print("py_compile  : OK")
    print("new sha     : %s" % sha256(TARGET))
    print("APPLIED")


main()
