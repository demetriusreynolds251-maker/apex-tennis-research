"""APEX-ALIS-BASEFIX-2026-08-31

ALIS resolved its logs from a hardcoded "~/openclaw" default. The project
now lives at ~/openclaw, so all three log paths pointed at files
that do not exist and every cycle reported "No settled rows found" while
the tracker read 54 settled picks from the same data.

BASE now falls back to the directory the script itself sits in, so a future
move cannot break it again. The APEX_HOME override is preserved and still
wins when set. Selftest's temp-dir reassignment at ~line 785 is untouched.
"""
import hashlib, os, shutil, sys, time, py_compile

TARGET = os.path.expanduser("~/openclaw/apex_learning_engine.py")

OLD = '''BASE = os.path.expanduser(os.environ.get("APEX_HOME", "~/openclaw"))'''

NEW = '''# APEX-ALIS-BASEFIX-2026-08-31: the old hardcoded "~/openclaw" default
# broke when the project moved to the Desktop -- every log path resolved to
# a missing file and ALIS silently reported nothing to learn from. Falling
# back to this script's own directory keeps it correct across moves.
BASE = os.path.expanduser(os.environ["APEX_HOME"]) if os.environ.get("APEX_HOME") \\
       else os.path.dirname(os.path.abspath(__file__))'''


def sha256(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def main():
    if not os.path.exists(TARGET):
        print("BLOCKED: target not found"); sys.exit(1)
    src = open(TARGET, encoding="utf-8").read()
    print("current sha : %s" % sha256(TARGET))
    bad = []
    if "APEX-ALIS-BASEFIX" in src:
        bad.append("marker present -- refusing double-apply")
    n = src.count(OLD)
    print("BASE anchor hits: %d (need 1)" % n)
    if n != 1:
        bad.append("BASE line not matched exactly once")
    if bad:
        print("")
        for b in bad: print("BLOCKED: %s" % b)
        sys.exit(1)
    if "--apply" not in sys.argv:
        print("")
        print("ALL CHECKS READY -- rerun with --apply to write")
        return
    stamp = time.strftime("%Y%m%d_%H%M%S")
    backup = "%s.bak_%s_prebasefix" % (TARGET, stamp)
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
