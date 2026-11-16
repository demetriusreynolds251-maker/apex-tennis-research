#!/usr/bin/env python3
"""APEX-TYPEDETAIL-FILTER-2026-09-28 -- best_bets_detail() accepts a prop_type
kwarg and uses it to build the header text ("BEST GOBLIN PROPS TODAY" etc.) but
never actually filters `picks` by it -- unlike best_bets_block(), which does
this filter correctly a few hundred lines above. Root cause of the reported
bug: /goblin, /standard and /demon (all three routed through best_bets_detail,
see discord_bot.py _BB_TYPE_COMMANDS) score and rank the SAME unfiltered board
and can therefore return identical top picks under three different headers.

Fix: add the same prop_type filter best_bets_block() already uses, applied
right where the existing category filter is (same place, same pattern).

Also adds a return_scored=False kwarg so a caller (the new overlap-diagnostic
report) can get the structured scored/deduped list back without re-parsing
the rendered text -- purely additive, default behavior/return type unchanged
for every existing caller.

Usage: python3 apex_typedetail_filter_patch.py --check | --apply"""
import hashlib, shutil, sys, py_compile, datetime

F = "apex_edge_tracker.py"
PIN = "0caea58c297422146c50718900114e4c5d467ea65b74f06e670feaa3732441e4"
MARK = "APEX-TYPEDETAIL-FILTER-2026-09-28"

A1_OLD = '''def best_bets_detail(picks, category=None, worst=False, rec=None, limit=15, prop_type=None,
                     slip_rules=False):
    """APEX-BB-002a: on-demand detail view. True score order (Bo5 eligible
    anywhere per spec, always tagged). worst=True ranks ascending."""
    try:
        from datetime import date as _d
        rec = rec or records()
        if category:
            picks = [p for p in picks if p.get("category") == category]
            if not picks:
                return "no active %s props on the current board" % LABEL.get(category, category)
        scored = []
'''
A1_NEW = '''def best_bets_detail(picks, category=None, worst=False, rec=None, limit=15, prop_type=None,
                     slip_rules=False, return_scored=False):
    """APEX-BB-002a: on-demand detail view. True score order (Bo5 eligible
    anywhere per spec, always tagged). worst=True ranks ascending."""
    try:
        from datetime import date as _d
        rec = rec or records()
        if category:
            picks = [p for p in picks if p.get("category") == category]
            if not picks:
                return "no active %s props on the current board" % LABEL.get(category, category)
        # APEX-TYPEDETAIL-FILTER-2026-09-28: this filter existed in
        # best_bets_block() but was missing here, so /goblin, /standard and
        # /demon (all routed through this function) ranked the same
        # unfiltered board and could return identical top picks. Same
        # pattern as best_bets_block(): prop_type has been logged per-row
        # since 2026-09-08; rows evaluated earlier carry none and are
        # simply absent from a type view.
        if prop_type:
            picks = [p for p in picks if str(p.get("prop_type") or "").lower() == str(prop_type).lower()]
            if not picks:
                return ("No %s props on the current board yet. (Prop type has been logged since "
                        "2026-09-08 -- boards evaluated before then carry no type.)" % prop_type)
        scored = []
'''

A2_OLD = '''        _bb_rank_log(scored, _legacy_pos, "detail", slip=_maps.get("mixed"), slip_std=_maps.get("standard"), slip_gob=_maps.get("goblin"))
        return "\\n".join(L)
    except Exception as e:
        return "best bets unavailable (%s)" % type(e).__name__


def bo5_block(rec):
'''
A2_NEW = '''        _bb_rank_log(scored, _legacy_pos, "detail", slip=_maps.get("mixed"), slip_std=_maps.get("standard"), slip_gob=_maps.get("goblin"))
        if return_scored:
            return {"text": "\\n".join(L), "scored": scored}
        return "\\n".join(L)
    except Exception as e:
        if return_scored:
            return {"text": "best bets unavailable (%s)" % type(e).__name__, "scored": []}
        return "best bets unavailable (%s)" % type(e).__name__


# APEX-TYPEDETAIL-FILTER-2026-09-28: overlap diagnostic. Compares the actual
# top-N picks /goblin, /standard and /demon would each hand back post-fix, so
# a regression that reintroduces cross-type duplication is caught by running
# this rather than by eyeballing three Discord messages side by side.
_OVERLAP_TYPES = ("goblin", "standard", "demon")


def _prop_key(p):
    return (str(p.get("player") or "").strip().casefold(),
            str(p.get("opponent") or "").strip().casefold(),
            str(p.get("category") or "").strip().casefold(),
            str(p.get("line") or ""),
            str(p.get("direction") or "").strip().upper())


def prop_type_overlap_report(picks, rec=None, limit=6):
    """Runs best_bets_detail() once per real prop type (goblin/standard/demon
    -- the market-availability types PrizePicks actually offers; there is no
    platform "bot/safe" type to check because that isn't a biddable market,
    it's a confidence label -- see best_bets_detail's own Confidence/Rank
    Score fields for that) and reports whether their top-`limit` picks
    overlap. Returns a dict, never raises."""
    rec = rec or records()
    total_typed = sum(1 for p in picks if p.get("prop_type"))
    per_type, top_keys = {}, {}
    for t in _OVERLAP_TYPES:
        res = best_bets_detail(picks, prop_type=t, limit=limit, rec=rec,
                               slip_rules=True, return_scored=True)
        scored = res["scored"] if isinstance(res, dict) else []
        board_count = sum(1 for p in picks if str(p.get("prop_type") or "").lower() == t)
        top = [_prop_key(d["p"]) for d in scored[:limit]]
        per_type[t] = {"on_board": board_count, "ranked": len(scored), "top": top}
        top_keys[t] = set(top)

    overlaps = {}
    warnings = []
    type_pairs = [(a, b) for i, a in enumerate(_OVERLAP_TYPES) for b in _OVERLAP_TYPES[i + 1:]]
    for a, b in type_pairs:
        shared = top_keys[a] & top_keys[b]
        overlaps[f"{a}_vs_{b}"] = len(shared)
        denom = min(len(top_keys[a]), len(top_keys[b])) or 1
        pct = len(shared) / denom
        if pct > 0.20:
            warnings.append(
                f"{a.upper()} and {b.upper()} top-{limit} overlap {pct:.0%} "
                f"({len(shared)}/{denom}) -- above the 20% flag threshold.")
        if per_type[a]["top"] and per_type[a]["top"] == per_type[b]["top"]:
            warnings.append(
                f"{a.upper()} and {b.upper()} top selections are IDENTICAL, in the same order.")

    lines = ["\U0001F50E **PROP TIER OVERLAP DIAGNOSTIC**",
             "Total props analyzed (typed): %d" % total_typed]
    for t in _OVERLAP_TYPES:
        lines.append("  %s: %d on board, %d ranked, top-%d shown" %
                      (t.upper(), per_type[t]["on_board"], per_type[t]["ranked"], limit))
    lines.append("Overlap counts (shared picks in each pair's top-%d):" % limit)
    for k, v in overlaps.items():
        lines.append("  %s: %d" % (k, v))
    if warnings:
        lines.append("⚠️ WARNINGS:")
        lines.extend("  - %s" % w for w in warnings)
    else:
        lines.append("No overlap warnings -- each type's top picks are distinct.")

    return {"text": "\\n".join(lines), "per_type": per_type, "overlaps": overlaps,
            "warnings": warnings, "total_typed": total_typed}


def bo5_block(rec):
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
    print("CHECK OK: SHA pinned, anchors 2/2 unique")
    if mode != "--apply":
        return
    bak = F + ".bak_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + "_pretypedetailfilter"
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
