"""APEX-ALIS-CHANNEL-2026-08-31

ALIS posted its cycle summary to the "system" channel, mixing learning
output with infrastructure noise. Routes it to its own channel instead.

  openclaw_core.py  -- adds "alis" to DISCORD_WEBHOOKS, read from
                       apex_alis_webhook.txt (kept out of source). Missing
                       or unreadable file leaves the entry absent, which
                       send_discord already treats as "not configured":
                       logged, returns True, nothing raises.
  apex_learning_engine.py -- line ~763 posts to "alis" instead of "system".

No other channel string is touched, so picks / alerts / general / learning /
system / moneyline routing is unchanged.
"""
import hashlib, os, shutil, sys, time, py_compile

BASE = os.path.expanduser("~/openclaw")
CORE = os.path.join(BASE, "openclaw_core.py")
ALIS = os.path.join(BASE, "apex_learning_engine.py")

CORE_OLD = '''
# Load from config.json if available'''

CORE_NEW = '''
# APEX-ALIS-CHANNEL-2026-08-31: dedicated ALIS reporting channel. The URL
# lives in apex_alis_webhook.txt, not in source. If the file is absent or
# unreadable the entry is simply not added -- send_discord() then logs
# "#alis not configured" and returns True, so ALIS still writes its
# markdown report and never raises.
try:
    _alis_wh = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "apex_alis_webhook.txt")
    if os.path.exists(_alis_wh):
        with open(_alis_wh) as _f:
            _u = _f.read().strip()
        if _u.startswith("https://"):
            DISCORD_WEBHOOKS["alis"] = _u
except Exception:
    pass

# Load from config.json if available'''

ALIS_OLD = '''            core.send_discord("system", msg)'''
ALIS_NEW = '''            core.send_discord("alis", msg)   # APEX-ALIS-CHANNEL-2026-08-31'''

EDITS = [(CORE, "core-webhook", CORE_OLD, CORE_NEW),
         (ALIS, "alis-channel", ALIS_OLD, ALIS_NEW)]


def sha256(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def main():
    srcs, bad = {}, []
    for p in (CORE, ALIS):
        if not os.path.exists(p):
            print("BLOCKED: missing %s" % p); sys.exit(1)
        srcs[p] = open(p, encoding="utf-8").read()
        print("%-26s %s" % (os.path.basename(p), sha256(p)))
        if "APEX-ALIS-CHANNEL" in srcs[p]:
            bad.append("%s already patched" % os.path.basename(p))
    print()
    for p, name, old, _n in EDITS:
        n = srcs[p].count(old)
        print("  %-14s %d (need 1)" % (name, n))
        if n != 1:
            bad.append("%s matched %d times" % (name, n))
    other = ['"picks"', '"alerts"', '"general"', '"learning"', '"moneyline"']
    print("  other channels present:", all(o in srcs[CORE] for o in other))
    if bad:
        print("")
        for b in bad: print("BLOCKED: %s" % b)
        sys.exit(1)
    if "--apply" not in sys.argv:
        print("")
        print("ALL CHECKS READY -- rerun with --apply to write")
        return
    stamp = time.strftime("%Y%m%d_%H%M%S")
    baks = {}
    for p in (CORE, ALIS):
        b = "%s.bak_%s_prealischan" % (p, stamp)
        shutil.copy2(p, b); baks[p] = b
        print("backup: %s" % os.path.basename(b))
    out = dict(srcs)
    for p, _n, old, new in EDITS:
        out[p] = out[p].replace(old, new, 1)
    for p in (CORE, ALIS):
        open(p, "w", encoding="utf-8").write(out[p])
    try:
        for p in (CORE, ALIS):
            py_compile.compile(p, doraise=True)
    except Exception as e:
        for p, b in baks.items(): shutil.copy2(b, p)
        print("COMPILE FAILED -- both restored"); print(e); sys.exit(1)
    print("py_compile  : OK")
    for p in (CORE, ALIS):
        print("%-26s %s" % (os.path.basename(p), sha256(p)))
    print("APPLIED")


main()
