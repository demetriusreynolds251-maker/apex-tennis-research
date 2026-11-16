#!/usr/bin/env python3
"""APEX-SLIP-V1-2026-09-06 -- Slip Builder v1: separate slip-construction layer.
RANK / APEX / CONFIDENCE / ordering untouched. Adds slip_builder(), a
SLIP CANDIDATES block in both render paths, and slip_slot + slip_reason in the rank log.
Usage: python3 apex_slip_builder_patch.py --check | --apply"""
import hashlib, shutil, sys, py_compile, datetime
F    = "apex_edge_tracker.py"
PIN  = "cb7133b28e726c895f7fe8532610843b2c18d0b60d1cd6492deefdc9cd6ce0bb"
MARK = "APEX-SLIP-V1-2026-09-06"

A1_OLD = r'''                   "rank_score", "rank_position", "legacy_apex_position"]
'''
A1_NEW = r'''                   "rank_score", "rank_position", "legacy_apex_position",
                   "slip_slot", "slip_reason"]   # APEX-SLIP-V1-2026-09-06


# ================================================================ APEX-SLIP-V1-2026-09-06
# Slip Builder v1 -- a CONSTRUCTION layer, not a scoring layer. Walks the RANK-ordered
# board and fills 5 slip slots under diversification rules. Never reorders, never
# re-scores, never hides: displaced picks are named with the rule that displaced them.
SLIP_SLOTS = 5

def _slip_ident(d):
    p = d["p"]
    cat = d.get("cat") or p.get("category", "")
    name = p.get("opponent", "") if p.get("player") == "match" else p.get("player", "")
    return cat, str(p.get("direction", "")).upper(), p.get("match_id", ""), str(name).lower(), name

def slip_builder(scored):
    """Returns {id(d): (slot|"", reason, rank_pos)} for every entry in scored (RANK order).
    Top 3: max 2 per category, max 2 per category+direction, never two from one match.
    Top 5: max 2 per category. One pick per player. Fail-open (caller wraps)."""
    out, slots = {}, []
    cat_n, catdir_n, matches, players = {}, {}, {}, set()
    for pos, d in enumerate(scored, 1):
        if len(slots) >= SLIP_SLOTS:
            out[id(d)] = ("", "", pos); continue
        cat, dr, mid, pl, _ = _slip_ident(d)
        nxt = len(slots) + 1
        why = ""
        if pl in players:
            why = "player already holds a slip slot"
        elif mid and mid in matches:
            why = "same match as slip slot #%d" % matches[mid]
        elif nxt <= 3 and cat_n.get(cat, 0) >= 2:
            why = "category cap: %s already x2 in top 3" % cat
        elif nxt <= 3 and catdir_n.get((cat, dr), 0) >= 2:
            why = "category+direction cap: %s %s already x2 in top 3" % (cat, dr)
        elif nxt > 3 and cat_n.get(cat, 0) >= 2:
            why = "category cap: %s already x2 in top 5" % cat
        if why:
            out[id(d)] = ("", why, pos); continue
        slots.append(d); players.add(pl); matches[mid] = nxt
        cat_n[cat] = cat_n.get(cat, 0) + 1; catdir_n[(cat, dr)] = catdir_n.get((cat, dr), 0) + 1
        out[id(d)] = (nxt, ("promoted from RANK #%d" % pos) if nxt < pos else "", pos)
    return out

def _slip_block(scored, slip):
    """Render the SLIP CANDIDATES section. Complete transparency: slots, then every
    displaced pick with its reason."""
    L = ["", "\U0001F3AF **SLIP CANDIDATES** (Slip Builder v1 -- construction layer; RANK order above is untouched)"]
    slotted = sorted((v[0], d) for d in scored if (v := slip.get(id(d))) and v[0])
    if not slotted:
        L.append("-- no slip candidates"); return L
    for slot, d in slotted:
        cat, dr, _, _, name = _slip_ident(d); p = d["p"]
        _, why, pos = slip[id(d)]
        L.append("Slot %d: %s -- %s %s %s \u00b7 %d%% \u00b7 RANK #%d%s%s" % (
            slot, name, LABEL.get(cat, cat), p.get("line", ""), dr, round(float(p.get("prob", 0)) * 100), pos,
            (" (%s)" % why) if why else "", " \u26a0\ufe0f BO5 SAMPLE" if p.get("bo5") else ""))
    moved = [(slip[id(d)][2], d) for d in scored if slip.get(id(d)) and not slip[id(d)][0] and slip[id(d)][1]]
    if moved:
        L.append("Displaced:")
        for pos, d in moved:
            cat, dr, _, _, name = _slip_ident(d); p = d["p"]
            L.append("\u00b7 %s %s %s %s was RANK #%d -- %s" % (name, LABEL.get(cat, cat), p.get("line", ""), dr, pos, slip[id(d)][1]))
    L.append("_Slip rules: top 3 max 2 per category, max 2 per category+direction, one per match; top 5 max 2 per category. Logged as slip_slot for ALIS._")
    return L
'''

A2_OLD = r'''def _bb_rank_log(scored, legacy_pos, source, path=None):
'''
A2_NEW = r'''def _bb_rank_log(scored, legacy_pos, source, path=None, slip=None):
'''
A3_OLD = r'''        fresh = not os.path.exists(path)
        with open(path, "a", newline="", encoding="utf-8") as fh:
'''
A3_NEW = r'''        fresh = not os.path.exists(path)
        # APEX-SLIP-V1: one-time header migration (old rows keep blank slip columns; backup kept)
        if not fresh:
            with open(path, newline="", encoding="utf-8") as fh:
                _hdr = fh.readline().strip().split(",")
            if "slip_slot" not in _hdr:
                import shutil as _sh
                _sh.copy2(path, path + ".bak_" + _dt.datetime.now().strftime("%Y%m%d_%H%M%S") + "_preslipcols")
                _old = list(csv.DictReader(open(path, newline="", encoding="utf-8")))
                with open(path, "w", newline="", encoding="utf-8") as fh:
                    _w = csv.DictWriter(fh, fieldnames=_BB_RANK_FIELDS); _w.writeheader()
                    for _r in _old:
                        _r.setdefault("slip_slot", ""); _r.setdefault("slip_reason", ""); _w.writerow(_r)
        slip = slip or {}
        with open(path, "a", newline="", encoding="utf-8") as fh:
'''
A4_OLD = r'''                            "legacy_apex_position": legacy_pos.get(id(d), "")})
'''
A4_NEW = r'''                            "legacy_apex_position": legacy_pos.get(id(d), ""),
                            "slip_slot": (slip.get(id(d)) or ("", "", 0))[0],
                            "slip_reason": (slip.get(id(d)) or ("", "", 0))[1]})
'''

A5_OLD = r'''        L.append("_Scores re-derive from the settled ledger at every post -- they sharpen as evidence settles._")
        _bb_rank_log(scored, _legacy_pos, "block")
'''
A5_NEW = r'''        L.append("_Scores re-derive from the settled ledger at every post -- they sharpen as evidence settles._")
        try:                                   # APEX-SLIP-V1: construction layer, fail-open
            _slip = slip_builder(scored)
            L.extend(_slip_block(scored, _slip))
        except Exception:
            _slip = {}
        _bb_rank_log(scored, _legacy_pos, "block", slip=_slip)
'''
A6_OLD = r'''        L.append("_Deterministic read of the current evaluated board -- no re-evaluation._")
        _bb_rank_log(scored, _legacy_pos, "detail")
'''
A6_NEW = r'''        L.append("_Deterministic read of the current evaluated board -- no re-evaluation._")
        try:                                   # APEX-SLIP-V1: construction layer, fail-open
            _slip = slip_builder(scored)
            L.extend(_slip_block(scored, _slip))
        except Exception:
            _slip = {}
        _bb_rank_log(scored, _legacy_pos, "detail", slip=_slip)
'''
ANCHORS = [("A1", A1_OLD, A1_NEW), ("A2", A2_OLD, A2_NEW), ("A3", A3_OLD, A3_NEW),
           ("A4", A4_OLD, A4_NEW), ("A5", A5_OLD, A5_NEW), ("A6", A6_OLD, A6_NEW)]

def sha(p): return hashlib.sha256(open(p, "rb").read()).hexdigest()

def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "--check"
    src = open(F, encoding="utf-8").read(); s = sha(F)
    assert s == PIN, f"SHA mismatch: {s}"
    assert MARK not in src, "already applied"
    for name, old, _ in ANCHORS:
        n = src.count(old); assert n == 1, f"anchor {name} matched {n}x"
    i5, i6 = src.index(A5_OLD), src.index(A6_OLD)
    assert "def best_bets_block" in src[:i5] and "def best_bets_detail" in src[i5:i6], "A5/A6 not in expected functions"
    print("CHECK OK: SHA pinned, anchors 6/6 unique, A5 in block / A6 in detail")
    if mode != "--apply": return
    bak = F + ".bak_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + "_preslipv1"
    shutil.copy2(F, bak)
    new = src
    for _, old, nw in ANCHORS: new = new.replace(old, nw, 1)
    open(F, "w", encoding="utf-8").write(new)
    try: py_compile.compile(F, doraise=True)
    except Exception as e:
        shutil.copy2(bak, F); print("py_compile FAILED -> restored:", e); sys.exit(1)
    print("APPLIED. backup:", bak); print("new sha:", sha(F))

if __name__ == "__main__":
    main()
