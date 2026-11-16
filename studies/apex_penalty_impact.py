#!/usr/bin/env python3
"""APEX-IMPACT-001 -- what each proposed score adjustment would have done, historically.
Read-only. Applies candidate rules to settled picks and reports winners/losers affected.
No deployment. No writes.
"""
import csv, os, sys
import apex_edge_tracker as A

SIM = "apex_prop_sim_forward_log_v1.csv"

def _f(v):
    try: return float(v)
    except (TypeError, ValueError): return None

def settled_rows():
    """Every settled pick with the fields the rules need."""
    out = []
    if not os.path.exists(SIM): return out
    for r in csv.DictReader(open(SIM, newline="", encoding="utf-8")):
        act, line = _f(r.get("actual")), _f(r.get("line"))
        if act is None or line is None: continue
        po, pu = _f(r.get("p_over")) or 0, _f(r.get("p_under")) or 0
        direction = "MORE" if po >= pu else "LESS"
        prob = (max(po, pu) / (po + pu)) if (po + pu) > 0 else None
        hit = None if act == line else ((act > line) if direction == "MORE" else (act < line))
        out.append({"player": r.get("player"), "opponent": r.get("opponent"),
                    "category": r.get("category"), "line": line, "direction": direction,
                    "prob": prob, "actual": act, "hit": hit,
                    "pinn_fav": _f(r.get("pinn_fav")), "bo5": str(r.get("best_of") or "") == "5",
                    "date": r.get("match_date")})
    return [x for x in out if x["hit"] is not None]

def rule_ace_opponent(p, tiers=(0.70, -15), tier2=(0.80, -25)):
    """Ace MORE where the OPPONENT is a strong favorite. pinn_fav is the favorite's
    price; if this player is not the favorite, the opponent's strength = pinn_fav."""
    if p["category"] != "aces" or p["direction"] != "MORE": return 0, ""
    pf = p["pinn_fav"]
    if pf is None: return 0, ""
    # opponent-favorite proxy: high pinn_fav on a match where this player is the underdog
    if pf >= tier2[0]: return tier2[1], "opponent favored %.2f" % pf
    if pf >= tiers[0]: return tiers[1], "opponent favored %.2f" % pf
    return 0, ""

def rule_dfs_less(p, penalty=-12):
    if p["category"] in ("dfs", "double_faults") and p["direction"] == "LESS":
        return penalty, "dfs LESS dispersion penalty"
    return 0, ""

def report(rule_fn, label, threshold=50):
    rows = settled_rows()
    rec = A.records()
    affected = []
    for p in rows:
        delta, why = rule_fn(p)
        if not delta: continue
        old, _, _, _, _ = A.apex_score(p["prob"], p["category"], p["bo5"], rec)
        new = max(0, min(100, old + delta))
        affected.append({**p, "old": old, "new": new, "delta": delta, "why": why})
    print("\n" + "=" * 70)
    print("RULE: %s" % label)
    print("=" * 70)
    if not affected:
        print("No settled picks would be affected."); return
    w = [a for a in affected if a["hit"]]; l = [a for a in affected if not a["hit"]]
    print("Settled picks affected: %d  (winners %d / losers %d)" % (len(affected), len(w), len(l)))
    print("\n| player | cat | line dir | actual | W/L | old | new | reason |")
    print("|---|---|---|---|---|---|---|---|")
    for a in sorted(affected, key=lambda x: -x["old"])[:20]:
        print("| %s | %s | %s %s | %s | %s | %d | %d | %s |" % (
            str(a["player"])[:16], a["category"], a["line"], a["direction"], a["actual"],
            "W" if a["hit"] else "L", a["old"], a["new"], a["why"]))
    # what crosses the selection threshold
    demoted = [a for a in affected if a["old"] >= threshold > a["new"]]
    dw = [a for a in demoted if a["hit"]]; dl = [a for a in demoted if not a["hit"]]
    print("\nCROSSING THE %d-POINT SELECTION LINE: %d picks" % (threshold, len(demoted)))
    print("  WINNERS removed: %d   <-- cost of the rule" % len(dw))
    print("  LOSERS removed:  %d   <-- benefit of the rule" % len(dl))
    if dw or dl:
        print("  Net: %+d bad picks avoided per %d affected" % (len(dl) - len(dw), len(affected)))
    hit_rate = (100.0 * len(w) / len(affected)) if affected else 0
    base = [p for p in rows if p["hit"] is not None]
    base_rate = 100.0 * sum(1 for p in base if p["hit"]) / max(len(base), 1)
    print("\n  Affected-group hit rate: %.0f%%   vs   board baseline: %.0f%%" % (hit_rate, base_rate))
    print("  VERDICT: %s" % ("penalty targets a genuinely weaker group" if hit_rate < base_rate - 5
          else "affected group performs at or above baseline -- penalty NOT supported" if hit_rate > base_rate
          else "insufficient difference to justify"))

if __name__ == "__main__":
    report(rule_dfs_less, "DFS LESS dispersion penalty (-12)")
    report(rule_ace_opponent, "Ace MORE vs strong opponent (-15 / -25)")
    print("\nNOTE: n is small. These numbers are evidence for a decision, not proof.")
