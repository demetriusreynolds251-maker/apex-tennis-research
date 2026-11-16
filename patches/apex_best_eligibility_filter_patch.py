#!/usr/bin/env python3
"""APEX-BEST-ELIGIBILITY-FILTER-2026-09-28 -- gates BEST GOBLIN / BEST
STANDARD generation (best_bets_block, best_bets_detail when prop_type is
goblin/standard) on the best_goblin_eligible / best_standard_eligible flags
written by openclaw_core.py's apex_floor_to_eligibility_patch.py. Directive
(2026-09-28): the 72.1%/70.0% floors must stop rejecting props from the
system entirely -- every prop still publishes to Picks Channel -- but a
below-floor prop must still be UNABLE to become the "Best Goblin"/"Best
Standard" pick. This is that second half, applied only where prop_type is
explicitly goblin or standard (i.e. the /goblin, /standard commands and
the Best-Bets-by-type block) -- never on the plain/category board, never
on demon, never touching ranking, dedup, slip-cap, or calibration
(records/_stat/apex_score/apex_confidence untouched).

Usage: python3 apex_best_eligibility_filter_patch.py --check | --apply"""
import hashlib, shutil, sys, py_compile, datetime

F = "apex_edge_tracker.py"
PIN = "8c0e9a7d2fadb01053f675829f3b5438d7f13a817ccae0e685c1fc2008657bc5"
MARK = "APEX-BEST-ELIGIBILITY-FILTER-2026-09-28"

_ELIG_HELPER = '''
def _best_eligible(p, prop_type):
    """APEX-BEST-ELIGIBILITY-FILTER-2026-09-28: True unless this prop's own
    type has an eligibility flag written for it and that flag reads False.
    A missing/blank flag (row logged before this existed, or a type with no
    floor at all, e.g. demon) is treated as eligible -- never excludes on
    absence. Reads a plain CSV-string ("True"/"False") or a real bool."""
    t = str(prop_type or "").strip().lower()
    if t not in ("goblin", "standard"):
        return True
    v = p.get("best_goblin_eligible" if t == "goblin" else "best_standard_eligible")
    if v is None or v == "":
        return True
    return str(v).strip().lower() == "true"
'''

A1_OLD = '''def best_bets_block(picks, rec=None, prop_type=None):
    """APEX-BB-001: rendered Best Bets section. picks: dicts with player,
    category, prob, line, direction, bo5. Never raises; '' on any problem."""
    try:
        rec = rec or records()
        # APEX-TYPECMD-TRK-2026-09-09: one prop type only (goblin / standard / demon).
        # Rows evaluated before 09-08 carry no prop_type and are simply not in these views.
        if prop_type:
            picks = [p for p in picks if str(p.get("prop_type") or "").lower() == str(prop_type).lower()]
            if not picks:
                return ("No %s props on the current board yet. (Prop type has been logged since "
                        "2026-09-08 -- boards evaluated before then carry no type.)" % prop_type)
        scored = []
'''
A1_NEW = _ELIG_HELPER + '''

def best_bets_block(picks, rec=None, prop_type=None):
    """APEX-BB-001: rendered Best Bets section. picks: dicts with player,
    category, prob, line, direction, bo5. Never raises; '' on any problem."""
    try:
        rec = rec or records()
        # APEX-TYPECMD-TRK-2026-09-09: one prop type only (goblin / standard / demon).
        # Rows evaluated before 09-08 carry no prop_type and are simply not in these views.
        if prop_type:
            picks = [p for p in picks if str(p.get("prop_type") or "").lower() == str(prop_type).lower()]
            if not picks:
                return ("No %s props on the current board yet. (Prop type has been logged since "
                        "2026-09-08 -- boards evaluated before then carry no type.)" % prop_type)
            # APEX-BEST-ELIGIBILITY-FILTER-2026-09-28: Best Goblin / Best
            # Standard specifically -- a below-floor prop stays on the
            # regular board (Picks Channel) but cannot become THIS.
            _before_elig = len(picks)
            picks = [p for p in picks if _best_eligible(p, prop_type)]
            if not picks:
                return ("No %s props currently clear the Best %s threshold (%d prop%s below floor). "
                        "Still visible in the main Picks Channel." %
                        (prop_type, str(prop_type).capitalize(), _before_elig,
                         "" if _before_elig == 1 else "s"))
        scored = []
'''

A2_OLD = '''        if prop_type:
            picks = [p for p in picks if str(p.get("prop_type") or "").lower() == str(prop_type).lower()]
            if not picks:
                return ("No %s props on the current board yet. (Prop type has been logged since "
                        "2026-09-08 -- boards evaluated before then carry no type.)" % prop_type)
        scored = []
        for p in picks:
            if not p.get("category"):
                continue
            if not _category_has_evidence(p["category"], rec):   # APEX-CAT-GATE-2026-09-27
                continue
'''
A2_NEW = '''        if prop_type:
            picks = [p for p in picks if str(p.get("prop_type") or "").lower() == str(prop_type).lower()]
            if not picks:
                return ("No %s props on the current board yet. (Prop type has been logged since "
                        "2026-09-08 -- boards evaluated before then carry no type.)" % prop_type)
            # APEX-BEST-ELIGIBILITY-FILTER-2026-09-28: Best Goblin / Best
            # Standard specifically -- a below-floor prop stays on the
            # regular board (Picks Channel) but cannot become THIS.
            _before_elig = len(picks)
            picks = [p for p in picks if _best_eligible(p, prop_type)]
            if not picks:
                return ("No %s props currently clear the Best %s threshold (%d prop%s below floor). "
                        "Still visible in the main Picks Channel." %
                        (prop_type, str(prop_type).capitalize(), _before_elig,
                         "" if _before_elig == 1 else "s"))
        scored = []
        for p in picks:
            if not p.get("category"):
                continue
            if not _category_has_evidence(p["category"], rec):   # APEX-CAT-GATE-2026-09-27
                continue
'''

ANCHORS = [("A1", A1_OLD, A1_NEW), ("A2", A2_OLD, A2_NEW)]


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "--check"
    src = open(F, encoding="utf-8").read()
    s = sha(F)
    assert s == PIN, f"SHA mismatch: {s}"
    assert MARK not in src, "already applied"
    for n, o, _ in ANCHORS:
        c = src.count(o)
        assert c == 1, f"anchor {n} matched {c}x"
    print("CHECK OK: SHA pinned, anchors %d/%d unique" % (len(ANCHORS), len(ANCHORS)))
    if mode != "--apply":
        return
    bak = F + ".bak_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + "_prebesteligfilter"
    shutil.copy2(F, bak)
    new = src
    for _, o, nw in ANCHORS:
        new = new.replace(o, nw, 1)
    open(F, "w", encoding="utf-8").write(new)
    try:
        py_compile.compile(F, doraise=True)
    except Exception as e:
        shutil.copy2(bak, F)
        print("py_compile FAILED -> restored:", e)
        sys.exit(1)
    print("APPLIED. backup:", bak)
    print("new sha:", sha(F))


if __name__ == "__main__":
    main()
