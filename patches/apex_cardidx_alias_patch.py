"""APEX-CARDIDX-ALIAS-2026-08-31

cat_key() checks EXPECTED before its translation dict, so a card whose stat
is already an EXPECTED name returns that name unchanged -- "double_faults"
is indexed as double_faults while the tracker asks for the engine slug
"dfs". The dict line is dead code for those categories.

Fixed at the lookup layer only: the requested category expands into a small
candidate list and each is tried in turn. cat_key() is not modified, the
index is not rebuilt, and every existing card stays valid.
"""
import hashlib, os, shutil, sys, time, py_compile

BASE   = os.path.expanduser("~/openclaw")
TARGET = os.path.join(BASE, "apex_card_index.py")

OLD = '''def lookup(player, category, date=""):
    idx = json.load(open(IDX)) if os.path.exists(IDX) else build(verbose=False)
    p = norm(player)
    for key in ("%s::%s::%s" % (p, category, date),
                "%s::%s::%s" % (p.split()[-1] if p else "", category, date),
                "%s::%s::" % (p, category)):
        if key in idx:
            path = os.path.join(RA.CARDS, idx[key])
            return RA.parse_card(path), path
    # date-agnostic fallback, still category-exact
    for k, v in idx.items():
        kp, kc, _ = k.split("::")
        if kc == category and (kp == p or (p and kp == p.split()[-1])):
            return RA.parse_card(os.path.join(RA.CARDS, v)), os.path.join(RA.CARDS, v)
    return None, None'''

NEW = '''# APEX-CARDIDX-ALIAS-2026-08-31: engine slugs vs card category names.
# cat_key() returns EXPECTED names before reaching its translation dict, so
# a "double_faults" card is never indexed under the engine slug "dfs".
# Aliases are applied here, at lookup, so cat_key() and the index are
# untouched. Reciprocal both ways; harmless when a name already agrees.
_CAT_ALIASES = {
    "dfs":              ["double_faults"],
    "double_faults":    ["dfs"],
    "breaks":           ["break_points_won"],
    "break_points_won": ["breaks"],
    "games_won":        ["total_games_won"],
    "total_games_won":  ["games_won"],
}


def _cat_candidates(category):
    """Requested category first, then any known alias. Order is stable."""
    c = str(category or "")
    out = [c]
    for a in _CAT_ALIASES.get(c, []):
        if a not in out:
            out.append(a)
    return out


def lookup(player, category, date=""):
    idx = json.load(open(IDX)) if os.path.exists(IDX) else build(verbose=False)
    p = norm(player)
    cats = _cat_candidates(category)
    for cat in cats:
        for key in ("%s::%s::%s" % (p, cat, date),
                    "%s::%s::%s" % (p.split()[-1] if p else "", cat, date),
                    "%s::%s::" % (p, cat)):
            if key in idx:
                path = os.path.join(RA.CARDS, idx[key])
                return RA.parse_card(path), path
    # date-agnostic fallback, still category-exact (aliases included)
    for k, v in idx.items():
        kp, kc, _ = k.split("::")
        if kc in cats and (kp == p or (p and kp == p.split()[-1])):
            return RA.parse_card(os.path.join(RA.CARDS, v)), os.path.join(RA.CARDS, v)
    return None, None'''


def sha256(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def main():
    if not os.path.exists(TARGET):
        print("BLOCKED: target not found"); sys.exit(1)
    src = open(TARGET, encoding="utf-8").read()
    print("current sha : %s" % sha256(TARGET))
    bad = []
    if "APEX-CARDIDX-ALIAS" in src:
        bad.append("marker present -- refusing double-apply")
    n = src.count(OLD)
    print("lookup() anchor hits: %d (need 1)" % n)
    if n != 1:
        bad.append("lookup() not matched exactly once")
    if "def cat_key" in src:
        bad.append("cat_key lives in this file -- unexpected, refusing")
    if bad:
        print("")
        for b in bad: print("BLOCKED: %s" % b)
        sys.exit(1)
    if "--apply" not in sys.argv:
        print("")
        print("ALL CHECKS READY -- rerun with --apply to write")
        return
    stamp = time.strftime("%Y%m%d_%H%M%S")
    backup = "%s.bak_%s_prealias" % (TARGET, stamp)
    shutil.copy2(TARGET, backup)
    print("backup      : %s" % backup)
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
