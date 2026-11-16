#!/usr/bin/env python3
"""APEX-BB-002e -- two-tier dedup: match props compete against both players."""
import hashlib, shutil, sys
from datetime import datetime
FN = "apex_edge_tracker.py"; MARKER = "APEX-BB-002e"
sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()

OLD = '''        # APEX-BB-002c3: one numbered slot per player-side; extras ride the
        # existing "also:" line. Skipped in worst mode -- every weak pick
        # deserves its own warning there.
        if not worst:
            _seen, _prim = {}, []
            for d in scored:
                _pk = (d["p"].get("player") or "") + "|" + (d["p"].get("opponent") or "")
                if _pk in _seen:
                    _seen[_pk].setdefault("more", []).append(d)
                else:
                    _seen[_pk] = d; _prim.append(d)
            scored = _prim'''

NEW = '''        # APEX-BB-002e: two-tier dedup. One prop per player (PrizePicks rule);
        # a match prop competes against BOTH its players and takes a numbered
        # slot only if it outranks each player's best prop. Skipped in worst
        # mode -- every weak pick deserves its own warning there.
        if not worst:
            import unicodedata as _ud
            def _norm(s):
                s = _ud.normalize("NFKD", str(s or ""))
                s = "".join(c for c in s if not _ud.combining(c))
                return s.casefold().replace("'", "").replace(".", "").replace("-", " ")
            _pslots, _prim, _match_rows = {}, [], []
            for d in scored:
                if (d["p"].get("player") or "") == "match":
                    _match_rows.append(d)
                    continue
                _pk = _norm(d["p"].get("player")) + "|" + _norm(d["p"].get("opponent"))
                if _pk in _pslots:
                    _pslots[_pk].setdefault("more", []).append(d)
                else:
                    _pslots[_pk] = d; _prim.append(d)
            for md in _match_rows:
                _sides = [_norm(x) for x in
                          (md["p"].get("opponent") or "").replace(" vs ", " v ").split(" v ")]
                _hits = []
                for _pk, _slot in _pslots.items():
                    _pname = _pk.split("|")[0]
                    for _sd in _sides:
                        if _sd and all(t in _pname.split() for t in _sd.split()):
                            _hits.append(_slot); break
                if not _hits:
                    _prim.append(md)                      # standalone: no player props
                elif all(md["sc"] > h["sc"] for h in _hits):
                    for h in _hits:                        # match prop wins the slot
                        _prim.remove(h)
                        md.setdefault("more", []).append(h)
                        md["more"].extend(h.pop("more", []))
                    _prim.append(md)
                else:
                    for h in _hits:                        # match prop loses
                        h.setdefault("more", []).append(md)
            _prim.sort(key=lambda d: (bool(d["p"].get("bo5")), -d["sc"]))
            scored = _prim'''

src = open(FN, encoding="utf-8").read()
if MARKER in src: sys.exit(f"{MARKER} already applied -- refusing")
n = src.count(OLD)
print(f"{MARKER}  {FN}  sha256 {sha(FN)}\n  [{'ok' if n == 1 else 'FAIL'}] dedup block: {n}")
if n != 1: sys.exit("ABORT -- nothing written")
if "--dry-run" in sys.argv: print("dry run: ok"); sys.exit(0)
bak = f"{FN}.bak_{datetime.now().strftime('%H%M%S')}_prebb2e"; shutil.copy2(FN, bak)
open(FN, "w", encoding="utf-8").write(src.replace(OLD, NEW, 1))
import py_compile, subprocess, os
TEST = r"""
import apex_edge_tracker as a
r = a.records()
def P(pl, op, cat, prob, line):  return {"player": pl, "opponent": op, "category": cat, "prob": prob, "line": line, "direction": "MORE", "bo5": False}
def M(matchup, cat, prob, line): return {"player": "match", "opponent": matchup, "category": cat, "prob": prob, "line": line, "direction": "LESS", "bo5": False}
F = []
# (1) same-player suppression
b = a.best_bets_detail([P("X","O","dfs",0.62,2.5), P("X","O","aces",0.60,7.5)], rec=r)
if "#2" in b or "also:" not in b: F.append("1 same-player suppression")
# Case 1 / (7)+(2): player props outrank the match prop -> two slots, match prop in also:
b = a.best_bets_detail([P("Arthur Rinderknech","Pablo Carreno Busta","dfs",0.66,3.5),
                        P("Pablo Carreno Busta","Arthur Rinderknech","dfs",0.62,2.5),
                        M("Rinderknech v Carreno Busta","total_sets",0.79,3.5)], rec=r)
if not ("#1" in b and "#2" in b and "#3" not in b and b.count("also:") == 2): F.append("7/Case1 player props win: " + repr(b[:200]))
# Case 2 / (6): match prop outranks both -> one slot as the matchup, both players in also:
b = a.best_bets_detail([P("Arthur Rinderknech","Pablo Carreno Busta","total_sets",0.55,20.5),
                        P("Pablo Carreno Busta","Arthur Rinderknech","total_sets",0.53,18.5),
                        M("Rinderknech v Carreno Busta","dfs",0.70,6.5)], rec=r)
if not ("#1 Rinderknech v Carreno Busta" in b and "#2" not in b and "also:" in b): F.append("6/Case2 match prop wins: " + repr(b[:200]))
# (3) two-word surname resolved above; (4) apostrophes
b = a.best_bets_detail([P("Christopher O'Connell","Someone Else","dfs",0.66,3.5),
                        M("O'Connell v Else","total_sets",0.58,3.5)], rec=r)
if "#2" in b: F.append("4 O'Connell resolution")
# (5) diacritics
b = a.best_bets_detail([P("Laslo Djere","Someone Else","dfs",0.66,3.5),
                        M("Djere v Else","total_sets",0.58,3.5)], rec=r)
if "#2" in b: F.append("5 diacritics/token resolution")
# (8) standalone: no player props from that match
b = a.best_bets_detail([P("Unrelated Guy","Other","dfs",0.62,2.5),
                        M("Ghost v Phantom","total_sets",0.58,3.5)], rec=r)
if "#2" not in b: F.append("8 standalone match prop lost")
# AND-condition: match beats one player but not the other -> denied, in both also: lines
b = a.best_bets_detail([P("Arthur Rinderknech","Pablo Carreno Busta","dfs",0.70,3.5),
                        P("Pablo Carreno Busta","Arthur Rinderknech","total_sets",0.52,18.5),
                        M("Rinderknech v Carreno Busta","fantasy_score",0.60,30.0)], rec=r)
if not ("#2" in b and "#3" not in b and b.count("also:") == 2): F.append("AND-condition: " + repr(b[:200]))
print("SELFTEST:", "PASS 9/9" if not F else "FAIL: " + "; ".join(F))
"""
try:
    py_compile.compile(FN, doraise=True)
    rr = subprocess.run(["/usr/bin/python3", "-c", TEST], capture_output=True, text=True, cwd=os.getcwd())
    print(rr.stdout.strip() or rr.stderr.strip()[-500:])
    if "PASS 9/9" not in rr.stdout: raise RuntimeError("selftest failed")
except Exception as e:
    shutil.copy2(bak, FN); sys.exit(f"ABORT -- {e}; restored")
print(f"written {FN}  sha256 {sha(FN)}  (backup {bak})")
