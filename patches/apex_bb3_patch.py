"""APEX-BB3-2026-08-31 -- Best Bets 3.0

RANK_SCORE = APEX_SCORE x (CONFIDENCE / 100.0), k=1. Ordering only.
APEX SCORE and apex_confidence() are not modified.

  1. rank_score() + _bb_sortkey() + _bb_rank_log() inserted as module helpers
  2. best_bets_block gains the apex_confidence call it never had, plus RANK
  3. both paths sort by RANK, then probability, then edge
  4. confidence tier words removed from display; CONFIDENCE n/70 shown
  5. legacy APEX-only order captured, shown in a footer, stored in the log
  6. load_current_board carries `edge` through for tiebreak 3
  7. apex_bb_rank_log_v1.csv -- append-only, fail-open

Playability rules (break-even, power play, flex, log-only) untouched.
"""
import hashlib, os, shutil, sys, time, py_compile

BASE   = os.path.expanduser("~/openclaw")
TARGET = os.path.join(BASE, "apex_edge_tracker.py")
PINNED = "2f9f4f69cdc0f54245c4608cac978c0e412fe3f05b6d9fa4f345618d343b327e"

E = []

HELPERS = '''def rank_score(apex, conf):
    """APEX-BB3-2026-08-31: ordering only. RANK = APEX x (CONFIDENCE / 100), k=1.
    Not a probability. Never feeds back into APEX SCORE or CONFIDENCE."""
    try:
        return round(float(apex) * (float(conf) / 100.0), 1)
    except (TypeError, ValueError):
        return 0.0


def _bb_sortkey(d, worst=False):
    """Explicit deterministic order: RANK, then probability, then edge.
    worst=True ascends. Edge is stored projection-minus-line and is NOT
    direction-normalised -- known limitation, third tiebreak only."""
    p = d.get("p") or {}
    def _f(v):
        try: return float(v or 0.0)
        except (TypeError, ValueError): return 0.0
    k = (_f(d.get("rank")), _f(p.get("prob")), _f(p.get("edge")))
    return k if worst else tuple(-x for x in k)


BB_RANK_LOG = "apex_bb_rank_log_v1.csv"
_BB_RANK_FIELDS = ["ts", "board_id", "source", "match_id", "player", "category",
                   "line", "direction", "probability", "apex_score", "confidence",
                   "rank_score", "rank_position", "legacy_apex_position"]


def _bb_rank_log(scored, legacy_pos, source, path=None):
    """APEX-BB3: append-only ranking history for ALIS. Fail-open by contract --
    any failure here must never stop a board posting."""
    try:
        import datetime as _dt, hashlib as _hl
        path = path or BB_RANK_LOG
        keys = sorted("%s|%s|%s" % (d["p"].get("match_id"), d["p"].get("player"),
                                    d.get("cat") or d["p"].get("category"))
                      for d in scored)
        board_id = _hl.sha256("|".join(keys).encode("utf-8")).hexdigest()[:12]
        ts = _dt.datetime.now().isoformat(timespec="seconds")
        fresh = not os.path.exists(path)
        with open(path, "a", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=_BB_RANK_FIELDS)
            if fresh:
                w.writeheader()
            for pos, d in enumerate(scored, 1):
                p = d["p"]
                w.writerow({"ts": ts, "board_id": board_id, "source": source,
                            "match_id": p.get("match_id", ""),
                            "player": p.get("player", ""),
                            "category": d.get("cat") or p.get("category", ""),
                            "line": p.get("line", ""),
                            "direction": p.get("direction", ""),
                            "probability": p.get("prob", ""),
                            "apex_score": d.get("score", d.get("sc", "")),
                            "confidence": d.get("conf", ""),
                            "rank_score": d.get("rank", ""),
                            "rank_position": pos,
                            "legacy_apex_position": legacy_pos.get(id(d), "")})
    except Exception:
        pass


'''

E.append(("helpers", "def best_bets_block(picks, rec=None):",
          HELPERS + "def best_bets_block(picks, rec=None):"))

E.append(("block-dict", '''            scored.append({"p": p, "cat": cat, "score": sc, "ev": ev, "lvl": lvl,
                           "up": up, "down": down, "rs": _rs(cs), "bo5": bool(p.get("bo5"))})''',
'''            try:
                import apex_card_index as _CI
                _card = _CI.lookup(str(p.get("player") or ""), cat,
                                   str(p.get("match_date") or ""))[0]
            except Exception:
                _card = None
            cf, _ctier, cwhy = apex_confidence(cat, bool(p.get("bo5")), rec,
                                               warnings=down, card_present=bool(_card))
            scored.append({"p": p, "cat": cat, "score": sc, "ev": ev, "lvl": lvl,
                           "conf": cf, "cwhy": cwhy, "rank": rank_score(sc, cf),
                           "up": up, "down": down, "rs": _rs(cs), "bo5": bool(p.get("bo5"))})'''))

E.append(("block-sort", '''        scored.sort(key=lambda d: -d["score"])  # APEX-BB-002g: true score order''',
'''        # APEX-BB3: legacy APEX-only order captured for the shadow footer + log
        _legacy_all = sorted(scored, key=lambda d: -d["score"])
        _legacy_pos, _legacy_prim, _lseen = {}, [], set()
        for _ld in _legacy_all:
            _lk = (_ld["p"].get("player") or "") + "|" + (_ld["p"].get("opponent") or "")
            if _lk in _lseen:
                continue
            _lseen.add(_lk)
            _legacy_prim.append(_ld)
            _legacy_pos[id(_ld)] = len(_legacy_prim)
        scored.sort(key=lambda d: _bb_sortkey(d))   # APEX-BB3: RANK, prob, edge'''))

E.append(("block-render",
'''            return ("**#%d %s** -- %s `%s %s` \\u00b7 %d%% \\u00b7 %s %s \\u00b7 cat %s \\u00b7 **APEX SCORE %d** (Evidence: %s)%s"
                    % (i, p.get("player", ""), LABEL.get(d["cat"], d["cat"]),
                       p.get("line", ""), p.get("direction", ""), round(float(p.get("prob") or 0) * 100),
                       icon[d["lvl"]], d["lvl"], d["rs"], d["score"], d["ev"],
                       " \\u26a0\\ufe0f BO5 SAMPLE" if d["bo5"] else ""))''',
'''            return ("**#%d %s** -- %s `%s %s` \\u00b7 %d%% \\u00b7 %s %s \\u00b7 cat %s \\u00b7 **APEX SCORE %d** \\u00b7 **CONFIDENCE %d/70** \\u00b7 **RANK SCORE %.1f** (Evidence: %s)%s"
                    % (i, p.get("player", ""), LABEL.get(d["cat"], d["cat"]),
                       p.get("line", ""), p.get("direction", ""), round(float(p.get("prob") or 0) * 100),
                       icon[d["lvl"]], d["lvl"], d["rs"], d["score"],
                       d.get("conf", 0), d.get("rank", 0.0), d["ev"],
                       " \\u26a0\\ufe0f BO5 SAMPLE" if d["bo5"] else ""))'''))

E.append(("block-footer",
'''        L.append("_Scores re-derive from the settled ledger at every post -- they sharpen as evidence settles._")
        return "\\n".join(L)''',
'''        L.append("")
        L.append("_RANK SCORE = APEX \\u00d7 (CONFIDENCE / 100) -- an ordering metric, not a probability._")
        L.append("_SHADOW \\u2014 legacy APEX-only order: %s_"
                 % " \\u00b7 ".join("%d. %s" % (_i, _d["p"].get("player", ""))
                                    for _i, _d in enumerate(_legacy_prim[:8], 1)))
        L.append("_Scores re-derive from the settled ledger at every post -- they sharpen as evidence settles._")
        _bb_rank_log(scored, _legacy_pos, "block")
        return "\\n".join(L)'''))

E.append(("detail-dict",
'''            scored.append({"p": p, "sc": sc, "ev": ev, "lvl": lvl, "up": up, "down": down,
                           "conf": cf, "ctier": ctier, "cwhy": cwhy})''',
'''            scored.append({"p": p, "sc": sc, "score": sc, "ev": ev, "lvl": lvl,
                           "up": up, "down": down, "conf": cf, "cwhy": cwhy,
                           "rank": rank_score(sc, cf)})'''))

E.append(("detail-sort",
'''        scored.sort(key=lambda d: d["sc"] if worst else -d["sc"])''',
'''        _legacy_d = sorted(scored, key=lambda d: d["sc"] if worst else -d["sc"])
        _legacy_pos = {}
        for _i, _ld in enumerate(_legacy_d, 1):
            _legacy_pos[id(_ld)] = _i
        scored.sort(key=lambda d: _bb_sortkey(d, worst))   # APEX-BB3'''))

E.append(("detail-slot",
'''                elif all(md["sc"] > h["sc"] for h in _hits):''',
'''                elif all(md.get("rank", 0) > h.get("rank", 0) for h in _hits):'''))

E.append(("detail-prim",
'''            # APEX-CONF-001: true score order, but within 8 points prefer higher confidence
            _prim.sort(key=lambda d: (-(d["sc"] // 8), -d.get("conf", 0), -d["sc"]))''',
'''            # APEX-BB3: RANK SCORE order -- supersedes the CONF-001 8-point banding
            _prim.sort(key=lambda d: _bb_sortkey(d, worst))'''))

E.append(("detail-display",
'''            L.append("**CONFIDENCE %d (%s)**%s" % (d.get("conf", 0), d.get("ctier", "?"),
                     (" -- " + "; ".join(d.get("cwhy", [])[:3])) if d.get("cwhy") else ""))''',
'''            L.append("**CONFIDENCE %d/70** \\u00b7 **RANK SCORE %.1f**%s" % (
                     d.get("conf", 0), d.get("rank", 0.0),
                     (" -- " + "; ".join(d.get("cwhy", [])[:3])) if d.get("cwhy") else ""))'''))

E.append(("detail-footer",
'''        L.append("_Deterministic read of the current evaluated board -- no re-evaluation._")''',
'''        L.append("_RANK SCORE = APEX \\u00d7 (CONFIDENCE / 100) -- ordering metric, not a probability._")
        L.append("_Deterministic read of the current evaluated board -- no re-evaluation._")
        _bb_rank_log(scored, _legacy_pos, "detail")'''))

E.append(("loader-edge",
'''                    "bo5": str(r.get("best_of") or "").strip() in ("5", "5.0"),
                    "match_date": r.get("match_date") or ""})''',
'''                    "bo5": str(r.get("best_of") or "").strip() in ("5", "5.0"),
                    "edge": r.get("edge") or "",
                    "match_date": r.get("match_date") or ""})'''))


def sha256(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def main():
    if not os.path.exists(TARGET):
        print("BLOCKED: target not found"); sys.exit(1)
    cur = sha256(TARGET)
    print("current sha : %s" % cur)
    print("pinned sha  : %s" % PINNED)
    src = open(TARGET, encoding="utf-8").read()
    bad = []
    if cur != PINNED and "--force" not in sys.argv:
        bad.append("file changed since this patch was written")
    if "APEX-BB3-2026-08-31" in src:
        bad.append("marker already present -- refusing double-apply")
    for name, old, _new in E:
        n = src.count(old)
        print("  %-16s %d (need 1)" % (name, n))
        if n != 1:
            bad.append("anchor %s matched %d times" % (name, n))
    if bad:
        print("")
        for b in bad:
            print("BLOCKED: %s" % b)
        sys.exit(1)
    if "--apply" not in sys.argv:
        print("")
        print("ALL CHECKS READY -- rerun with --apply to write")
        return
    stamp = time.strftime("%Y%m%d_%H%M%S")
    backup = "%s.bak_%s_prebb3" % (TARGET, stamp)
    shutil.copy2(TARGET, backup)
    print("backup      : %s" % backup)
    out = src
    for _name, old, new in E:
        out = out.replace(old, new, 1)
    open(TARGET, "w", encoding="utf-8").write(out)
    try:
        py_compile.compile(TARGET, doraise=True)
    except Exception as e:
        shutil.copy2(backup, TARGET)
        print("COMPILE FAILED -- backup restored"); print(e); sys.exit(1)
    print("py_compile  : OK")
    print("new sha     : %s" % sha256(TARGET))
    print("APPLIED")


main()
