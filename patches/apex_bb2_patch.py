#!/usr/bin/env python3
"""APEX-BB-002a -- on-demand Best Bets: board loader + detail renderer (tracker),
CLI command 'bestbets [dfs|fantasy|aces|breaks|games_won|total_games|worst]' (core).
Reads the pick log; never re-evaluates. House protocol."""
import hashlib, shutil, sys, subprocess, os
from datetime import datetime
MARKER = "APEX-BB-002a"
sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()

FUNCS = r'''

# ================================================================ APEX-BB-002a
def load_current_board(today=None, path=None):
    """Most recent evaluated board from the pick log. Rows with match_date >=
    today, deduped on (match_id, player, category) newest ts wins. Returns
    (picks, note) -- note is non-empty when there is nothing to rank.
    Deterministic: reads the log, calls no model, creates no projections."""
    from datetime import date as _d
    today = today or _d.today().isoformat()
    path = path or PICK_LOG
    if not os.path.exists(path):
        return [], "no pick log found (%s) -- the engine has not evaluated a board yet" % path
    best = {}
    for r in _read(path):
        key = (r.get("match_id"), r.get("player"), r.get("category"))
        if key not in best or (r.get("ts") or "") > (best[key].get("ts") or ""):
            best[key] = r
    live = [r for r in best.values() if (r.get("match_date") or "") >= today]
    if not live:
        last = max((r.get("match_date") or "" for r in best.values()), default="")
        return [], "no active board -- most recent evaluated match date is %s" % (last or "unknown")
    out = []
    for r in live:
        try:
            prob = float(r.get("prob") or 0)
        except (TypeError, ValueError):
            prob = 0.0
        out.append({"player": r.get("player") or "", "opponent": r.get("opponent") or "",
                    "category": r.get("category") or "", "line": r.get("line") or "",
                    "direction": r.get("direction") or "", "prob": prob,
                    "bo5": str(r.get("best_of") or "").strip() in ("5", "5.0"),
                    "match_date": r.get("match_date") or ""})
    return out, ""


_BB_CAT_TITLE = {"dfs": "DOUBLE FAULT", "fantasy_score": "FANTASY", "aces": "ACE",
                 "breaks": "BREAK", "games_won": "GAMES WON", "total_games": "TOTAL GAMES"}

def best_bets_detail(picks, category=None, worst=False, rec=None, limit=10):
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
        for p in picks:
            if not p.get("category"):
                continue
            sc, ev, lvl, up, down = apex_score(p.get("prob"), p["category"], bool(p.get("bo5")), rec)
            scored.append({"p": p, "sc": sc, "ev": ev, "lvl": lvl, "up": up, "down": down})
        if not scored:
            return "no rankable picks on the current board"
        scored.sort(key=lambda d: d["sc"] if worst else -d["sc"])
        if worst:
            head = "\u26a0\ufe0f **LOW PRIORITY PICKS -- %s** (weakest first)" % _d.today().isoformat()
        elif category:
            head = "\U0001F3C6 **BEST %s PROPS TODAY -- %s**" % (_BB_CAT_TITLE.get(category, category.upper()), _d.today().isoformat())
        else:
            head = "\U0001F3C6 **APEX BEST BETS TODAY -- %s** (entire evaluated board, %d picks)" % (_d.today().isoformat(), len(scored))
        medals = {1: "\U0001F947", 2: "\U0001F948", 3: "\U0001F949"}
        L = [head]
        for i, d in enumerate(scored[:limit], 1):
            p, cat = d["p"], d["p"]["category"]
            cs = rec["cats"].get(cat) or _stat([])
            name = p["opponent"] if p["player"] == "match" else p["player"]
            vs = "" if p["player"] == "match" else (" vs %s" % p["opponent"] if p["opponent"] else "")
            l10 = "Last 10: %d\u2013%d" % cs["last10"] if cs["n"] else "no settled history"
            why_up = "; ".join(d["up"][:2]) or "highest evidence-weighted score available"
            why_dn = "; ".join(d["down"][:2]) or "outranked on evidence, no specific flags"
            L.append("\u2500" * 30)
            L.append("%s **#%d %s**%s%s" % (medals.get(i, "\u25AB\uFE0F"), i, name, vs,
                                            " \u26a0\ufe0f BO5 SAMPLE" if p["bo5"] else ""))
            L.append("%s `%s %s` \u00b7 %d%% \u00b7 **APEX SCORE %d**" % (
                LABEL.get(cat, cat), p["line"], p["direction"], round(d["p"]["prob"] * 100), d["sc"]))
            L.append("Attention: %s \u00b7 Evidence: %s \u00b7 Category: %s \u00b7 %s" % (
                d["lvl"], d["ev"], _rs(cs), l10))
            L.append(("Why ranked low: %s" % why_dn) if worst else ("Why Apex likes it: %s" % why_up))
            if not worst and d["sc"] < 50:
                L.append("\u26a0\ufe0f below the 50 bar -- best available, not a strong bet")
        if len(scored) > limit:
            L.append("\u2500" * 30)
            L.append("(+%d more on the board -- scores %d and below)" % (len(scored) - limit, scored[limit]["sc"]))
        L.append("_Deterministic read of the current evaluated board -- no re-evaluation._")
        return "\n".join(L)
    except Exception as e:
        return "best bets unavailable (%s)" % type(e).__name__


'''

E_TRACKER = [
("A insert functions",
"def bo5_block(rec):",
FUNCS.strip("\n") + "\n\n\ndef bo5_block(rec):"),
("B selftest",
'''    print(MARKER, "selftest", "PASS" if not fails else "FAIL")''',
'''    # ---- APEX-BB-002a checks
    import tempfile as _tf2, csv as _csv2
    _bp = os.path.join(_tf2.mkdtemp(), "picks.csv")
    _bh = ["ts", "match_id", "match_date", "player", "opponent", "category", "line", "direction", "prob", "best_of"]
    with open(_bp, "w", newline="") as fh2:
        w2 = _csv2.DictWriter(fh2, fieldnames=_bh); w2.writeheader()
        w2.writerow({"ts": "T1", "match_id": "m1", "match_date": "2026-08-29", "player": "P_old", "opponent": "O",
                     "category": "dfs", "line": "2.5", "direction": "MORE", "prob": "0.55", "best_of": "3"})
        w2.writerow({"ts": "T2", "match_id": "m1", "match_date": "2026-08-29", "player": "P_old", "opponent": "O",
                     "category": "dfs", "line": "3.5", "direction": "MORE", "prob": "0.62", "best_of": "3"})
        w2.writerow({"ts": "T1", "match_id": "m2", "match_date": "2026-08-29", "player": "P_b5", "opponent": "O2",
                     "category": "aces", "line": "9.5", "direction": "MORE", "prob": "0.70", "best_of": "5"})
        w2.writerow({"ts": "T1", "match_id": "m3", "match_date": "2026-08-01", "player": "P_stale", "opponent": "O3",
                     "category": "aces", "line": "5.5", "direction": "MORE", "prob": "0.60", "best_of": "3"})
    _bd, _bn = load_current_board(today="2026-08-29", path=_bp)
    if _bn or len(_bd) != 2: fails.append("BB2: board load/dedupe/stale-filter wrong (%s, n=%d)" % (_bn, len(_bd)))
    if not any(p["line"] == "3.5" for p in _bd): fails.append("BB2: dedupe kept the older row")
    _dt = best_bets_detail(_bd, rec=r_bb)
    for need in ("APEX BEST BETS", "\U0001F947", "BO5 SAMPLE", "Why Apex likes it", "APEX SCORE"):
        if need not in _dt: fails.append("BB2 render missing %r" % need)
    _dc = best_bets_detail(_bd, category="dfs", rec=r_bb)
    if "P_b5" in _dc or "BEST DOUBLE FAULT" not in _dc: fails.append("BB2: category filter leaked")
    if "no active" not in best_bets_detail(_bd, category="breaks", rec=r_bb): fails.append("BB2: empty category must say so")
    _dw = best_bets_detail(_bd, worst=True, rec=r_bb)
    if "LOW PRIORITY" not in _dw or "Why ranked low" not in _dw: fails.append("BB2: worst mode wrong")
    _bd2, _bn2 = load_current_board(today="2026-09-15", path=_bp)
    if _bd2 or "no active board" not in _bn2: fails.append("BB2: stale board must return a note, not rankings")
    print(MARKER, "selftest", "PASS" if not fails else "FAIL")'''),
]

E_CORE = [
("C cli branch",
'''        elif cmd == "learn":
            run_learning()''',
'''        elif cmd == "learn":
            run_learning()
        elif cmd == "bestbets":
            # APEX-BB-002a: on-demand Best Bets from the current evaluated board.
            import apex_edge_tracker as _aet2
            _arg = (sys.argv[2] if len(sys.argv) > 2 else "").strip().lower()
            _cat = {"dfs": "dfs", "double_faults": "dfs", "fantasy": "fantasy_score",
                    "fantasy_score": "fantasy_score", "aces": "aces", "breaks": "breaks",
                    "games_won": "games_won", "gameswon": "games_won",
                    "tg": "total_games", "total_games": "total_games"}.get(_arg)
            _worst = _arg in ("worst", "avoid")
            _picks, _note = _aet2.load_current_board()
            _txt = _note if _note else _aet2.best_bets_detail(_picks, category=_cat, worst=_worst)
            print(_txt)
            send_discord("general", _txt)'''),
]

def main():
    files = {"apex_edge_tracker.py": E_TRACKER, "openclaw_core.py": E_CORE}
    ok = True; srcs = {}
    for fn, edits in files.items():
        srcs[fn] = open(fn, encoding="utf-8", errors="replace").read()
        if MARKER in srcs[fn]: sys.exit(f"{MARKER} already present in {fn} -- refusing")
        print(f"{MARKER}  {fn}  sha256 {sha(fn)}")
        for name, old, new in edits:
            n = srcs[fn].count(old)
            print("  [%s] %s: %d match(es)" % ("ok" if n == 1 else "FAIL", name, n)); ok = ok and n == 1
    if not ok: sys.exit("ABORT -- nothing written")
    if "--dry-run" in sys.argv: print("dry run: ok"); sys.exit(0)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S"); baks = {}
    for fn, edits in files.items():
        baks[fn] = f"{fn}.bak_{ts}_prebb2"; shutil.copy2(fn, baks[fn])
        s = srcs[fn]
        for name, old, new in edits: s = s.replace(old, new, 1)
        open(fn, "w", encoding="utf-8").write(s)
    import py_compile
    try:
        for fn in files: py_compile.compile(fn, doraise=True)
        r = subprocess.run(["/usr/bin/python3", "-c",
            "import apex_edge_tracker as a;"
            "b,n=a.load_current_board();"
            "print('board:', len(b), 'picks' if not n else n);"
            "print('smoke OK')"], capture_output=True, text=True, cwd=os.getcwd())
        print(r.stdout.strip() or r.stderr.strip())
        if "smoke OK" not in r.stdout: raise RuntimeError(r.stderr[-300:])
    except Exception as e:
        for fn in files: shutil.copy2(baks[fn], fn)
        sys.exit(f"ABORT -- {e}; restored backups")
    for fn in files: print(f"written {fn}  sha256 {sha(fn)}  (backup {baks[fn]})")

if __name__ == "__main__": main()
