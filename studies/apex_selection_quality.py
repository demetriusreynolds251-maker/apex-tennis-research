#!/usr/bin/env python3
"""APEX-SEL-002 -- selection-quality measurement.
Joins frozen snapshots to settled outcomes; measures score-band and rank-band
performance, separation, monotonicity. Version-scoped: never compares across
scorer versions. Read-only except SELECTION_QUALITY_REGISTRY.md.
  --measure [--write]   compute (and optionally append the registry entry)
"""
import json, os, csv, glob, sys, argparse
from datetime import datetime

SEL_DIR = "apex_learning_system/selection"
REG = "apex_learning_system/SELECTION_QUALITY_REGISTRY.md"
BANDS = ["95+","90-94","85-89","80-84","75-79","70-74","65-69","60-64","55-59","50-54","<50"]
RANK_BANDS = [("Top 3",1,3),("Top 5",1,5),("Top 10",1,10),("Top 15",1,15),("Rest",16,10**6)]

def _ev(n):
    return "Very Low" if n < 5 else "Low" if n < 10 else "Moderate" if n < 25 else "Strong" if n < 100 else "Proven"

def _outcomes():
    """Settled results keyed (match_id, player_lower, category) -> True/False/None(push)."""
    out = {}
    for path in ("apex_prop_sim_forward_log_v1.csv", "apex_engine_picks_log_v1.csv"):
        if not os.path.exists(path): continue
        for r in csv.DictReader(open(path, newline="", encoding="utf-8")):
            act, line = (r.get("actual") or "").strip(), (r.get("line") or "").strip()
            if not act or not line: continue
            try: a_, l_ = float(act), float(line)
            except ValueError: continue
            d = (r.get("direction") or "").upper()
            if not d:
                po, pu = float(r.get("p_over") or 0), float(r.get("p_under") or 0)
                d = "MORE" if po >= pu else "LESS"
            hit = None if a_ == l_ else ((a_ > l_) if d == "MORE" else (a_ < l_))
            out[(r.get("match_id"), (r.get("player") or "").lower(), r.get("category"))] = hit
    return out

def _stat(rows):
    dec = [r for r in rows if r["hit"] is not None]
    w = sum(1 for r in dec if r["hit"])
    exp = sum(float(r["prob"] or 0) for r in dec)
    return {"n": len(dec), "w": w, "l": len(dec)-w,
            "rate": (w/len(dec)) if dec else None,
            "exp": round(exp,2) if dec else None,
            "cal": round(w-exp,2) if dec else None, "ev": _ev(len(dec))}

def measure(write=False):
    oc = _outcomes()
    by_ver = {}
    for f in sorted(glob.glob(os.path.join(SEL_DIR, "board_*.json"))):
        doc = json.load(open(f))
        v = doc.get("scorer_version","?")
        for p in doc["picks"]:
            key = (p.get("match_id"), (p.get("player") or "").lower(), p.get("category"))
            if key in oc:
                by_ver.setdefault(v, []).append({**p, "hit": oc[key], "date": doc["date"]})
    if not by_ver:
        print("No settled picks match any snapshot yet.")
        print("Selection Quality: UNMEASURED -- snapshots exist, outcomes pending.")
        return 0
    lines = []
    for v, rows in sorted(by_ver.items()):
        overall = _stat(rows)
        lines.append("\n## Scorer version %s  (settled n=%d)" % (v, overall["n"]))
        lines.append("Board average: %s  rate %s  exp %s  cal %s  [%s]" % (
            "%d-%d" % (overall["w"], overall["l"]), "%.1f%%" % (100*overall["rate"]) if overall["rate"] is not None else "—",
            overall["exp"], overall["cal"], overall["ev"]))
        lines.append("\n### Score bands (PRIMARY)")
        lines.append("| band | rec | hit% | exp | cal | n | evidence |")
        lines.append("|---|---|---|---|---|---|---|")
        seq = []
        for b in BANDS:
            s = _stat([r for r in rows if r.get("score_band") == b])
            if s["n"] == 0: continue
            seq.append((b, s["rate"]))
            lines.append("| %s | %d-%d | %.1f%% | %s | %s | %d | %s |" % (b, s["w"], s["l"], 100*s["rate"], s["exp"], s["cal"], s["n"], s["ev"]))
        sep = mono = None
        if len(seq) >= 2:
            sep = 100*(seq[0][1] - seq[-1][1])
            mono = all(seq[i][1] >= seq[i+1][1] for i in range(len(seq)-1))
        lines.append("\n### Rank bands (secondary)")
        lines.append("| band | rec | hit% | cal | n | evidence |")
        lines.append("|---|---|---|---|---|---|")
        for nm, lo, hi in RANK_BANDS:
            s = _stat([r for r in rows if lo <= r.get("rank", 10**6) <= hi])
            if s["n"] == 0: continue
            lines.append("| %s | %d-%d | %.1f%% | %s | %d | %s |" % (nm, s["w"], s["l"], 100*s["rate"], s["cal"], s["n"], s["ev"]))
        top_n = sum(1 for r in rows if r.get("score_band") in ("95+","90-94") and r["hit"] is not None)
        gate = overall["n"] >= 100 and top_n >= 20 and mono
        lines.append("\n**Separation (top band - bottom band):** %s" % ("%+.1f pts" % sep if sep is not None else "—"))
        lines.append("**Monotonic ordering:** %s" % ("YES" if mono else "NO" if mono is not None else "—"))
        lines.append("**Elite gate:** %s (needs n>=100 [have %d], top-band n>=20 [have %d], monotonic [%s])" % (
            "PASSED" if gate else "NOT MET", overall["n"], top_n, "yes" if mono else "no"))
        lines.append("**Verdict:** %s" % (
            "Ranking identifies stronger opportunities." if gate and sep and sep > 0 else
            "INSUFFICIENT EVIDENCE -- numbers shown are not yet conclusive."))
    txt = "\n".join(lines)
    print(txt)
    if write:
        os.makedirs(os.path.dirname(REG), exist_ok=True)
        hdr = "" if os.path.exists(REG) else "# SELECTION QUALITY REGISTRY\nAppend-only. Version-scoped: never compare across scorer versions.\n"
        with open(REG, "a", encoding="utf-8") as f:
            f.write(hdr + "\n---\n# Entry %s\n%s\n" % (datetime.now().strftime("%Y-%m-%d %H:%M"), txt))
        print("\nappended -> %s" % REG)
    return 0

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--measure", action="store_true")
    ap.add_argument("--write", action="store_true")
    a_ = ap.parse_args()
    sys.exit(measure(write=a_.write) if a_.measure else ap.print_help())
