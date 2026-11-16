"""APEX-MATCHCARD-2026-08-31

Match-level props (total_games, total_sets, tiebreaks) carry player="match"
with the real pair in opponent ("A v B"). Cards are saved under the pair and
indexed per player, so "match::total_games::DATE" can never resolve.

Adds lookup_match(opponent, category, date) to apex_card_index: splits the
pair and resolves through the existing lookup() (aliases included), so a
match prop finds the card that already exists. Both tracker ranking paths
route player=="match" through it.

Index untouched, cat_key untouched, no reindex, player lookups unchanged.
"""
import hashlib, os, shutil, sys, time, py_compile

BASE = os.path.expanduser("~/openclaw")
IDXF = os.path.join(BASE, "apex_card_index.py")
TRKF = os.path.join(BASE, "apex_edge_tracker.py")

IDX_OLD = '''def lookup(player, category, date=""):'''

IDX_NEW = '''def lookup_match(opponent, category, date=""):
    """APEX-MATCHCARD-2026-08-31: match-level props carry player="match" and
    the real pair in `opponent` ("A v B" / "A vs B"). The index is keyed per
    player, so resolve by either side -- a match card is ONE file indexed
    under both names, so either side returns the same card. Returns the same
    (card, path) shape as lookup(); (None, None) when nothing resolves."""
    s = str(opponent or "")
    for sep in (" vs ", " v. ", " v "):
        if sep in s:
            sides = s.split(sep, 1)
            break
    else:
        sides = [s]
    for side in sides:
        side = side.strip()
        if not side:
            continue
        card, path = lookup(side, category, date)
        if card:
            return card, path
    return None, None


def lookup(player, category, date=""):'''

TRK_OLD = '''            try:
                import apex_card_index as _CI
                _card = _CI.lookup(str(p.get("player") or ""), cat,
                                   str(p.get("match_date") or ""))[0]
            except Exception:
                _card = None'''

TRK_NEW = '''            try:
                import apex_card_index as _CI
                # APEX-MATCHCARD-2026-08-31: match rows key on the pair
                if (p.get("player") or "") == "match":
                    _card = _CI.lookup_match(str(p.get("opponent") or ""), cat,
                                             str(p.get("match_date") or ""))[0]
                else:
                    _card = _CI.lookup(str(p.get("player") or ""), cat,
                                       str(p.get("match_date") or ""))[0]
            except Exception:
                _card = None'''

TRK2_OLD = '''            try:
                import apex_card_index as _CI
                _card = _CI.lookup(str(p.get("player") or ""), p["category"], str(p.get("match_date") or ""))[0]
            except Exception: _card = None'''

TRK2_NEW = '''            try:
                import apex_card_index as _CI
                # APEX-MATCHCARD-2026-08-31: match rows key on the pair
                if (p.get("player") or "") == "match":
                    _card = _CI.lookup_match(str(p.get("opponent") or ""), p["category"], str(p.get("match_date") or ""))[0]
                else:
                    _card = _CI.lookup(str(p.get("player") or ""), p["category"], str(p.get("match_date") or ""))[0]
            except Exception: _card = None'''

EDITS = [(IDXF, "index-helper", IDX_OLD, IDX_NEW),
         (TRKF, "tracker-block", TRK_OLD, TRK_NEW),
         (TRKF, "tracker-detail", TRK2_OLD, TRK2_NEW)]


def sha256(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def main():
    bad, srcs = [], {}
    for path in (IDXF, TRKF):
        if not os.path.exists(path):
            print("BLOCKED: missing %s" % path); sys.exit(1)
        srcs[path] = open(path, encoding="utf-8").read()
        print("%-24s %s" % (os.path.basename(path), sha256(path)))
        if "APEX-MATCHCARD" in srcs[path]:
            bad.append("%s already patched" % os.path.basename(path))
    print()
    for path, name, old, _new in EDITS:
        n = srcs[path].count(old)
        print("  %-16s %d (need 1)" % (name, n))
        if n != 1:
            bad.append("%s matched %d times" % (name, n))
    if bad:
        print("")
        for b in bad: print("BLOCKED: %s" % b)
        sys.exit(1)
    if "--apply" not in sys.argv:
        print("")
        print("ALL CHECKS READY -- rerun with --apply to write")
        return
    stamp = time.strftime("%Y%m%d_%H%M%S")
    backups = {}
    for path in (IDXF, TRKF):
        b = "%s.bak_%s_prematchcard" % (path, stamp)
        shutil.copy2(path, b); backups[path] = b
        print("backup: %s" % os.path.basename(b))
    out = dict(srcs)
    for path, _name, old, new in EDITS:
        out[path] = out[path].replace(old, new, 1)
    for path in (IDXF, TRKF):
        open(path, "w", encoding="utf-8").write(out[path])
    try:
        for path in (IDXF, TRKF):
            py_compile.compile(path, doraise=True)
    except Exception as e:
        for path, b in backups.items():
            shutil.copy2(b, path)
        print("COMPILE FAILED -- both files restored"); print(e); sys.exit(1)
    print("py_compile  : OK")
    for path in (IDXF, TRKF):
        print("%-24s %s" % (os.path.basename(path), sha256(path)))
    print("APPLIED")


main()
