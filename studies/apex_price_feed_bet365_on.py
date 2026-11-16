#!/usr/bin/env python3
"""APEX-BET365-ON-2026-09-23 -- switch on Bet365 pre-match pricing, with the measured
lean correction (368-match backfill: Bet365 underrates the favourite by ~0.53 pts vs
Pinnacle on average). Approved after two independent sensitivity-test runs showed
aces/dfs/breaks/total_sets/games_won/total_games hold up under Bet365-sized price
noise; fantasy_score is the one category with a real, repeated cost and stays gated
separately (not yet wired -- see TODO in the file).
Usage: python3 apex_price_feed_bet365_on.py --check | --apply"""
import hashlib, shutil, sys, py_compile, datetime
F = "apex_price_feed.py"; MARK = "APEX-BET365-ON-2026-09-23"
A1_OLD = "BET365_PREMATCH_ENABLED = False  # flips only after the gap study (apex_sa365_gap_collector.py)\n"
A1_NEW = ("BET365_PREMATCH_ENABLED = True   # APEX-BET365-ON-2026-09-23: gap study cleared "
          "aces/dfs/breaks/total_sets/games_won/total_games; fantasy_score gated separately\n"
          "BET365_LEAN_CORRECTION = 0.0053  # measured 09-23 on 368 matches: Bet365 favourite "
          "prob runs ~0.53pt low vs Pinnacle on average; added back before use\n")
A2_OLD = '''        p1, p2, s = devig(r.get("od1"), r.get("od2"))
        if p1 is None:
            log(f"DECLINE: Bet365 price unusable -- {s}")
            return None
        h, a = _names(e)'''
A2_NEW = '''        p1, p2, s = devig(r.get("od1"), r.get("od2"))
        if p1 is None:
            log(f"DECLINE: Bet365 price unusable -- {s}")
            return None
        # APEX-BET365-ON-2026-09-23: correct the measured Bet365 lean before use
        if p1 >= p2:
            p1 = min(max(p1 + BET365_LEAN_CORRECTION, PROB_MIN), PROB_MAX); p2 = 1 - p1
        else:
            p2 = min(max(p2 + BET365_LEAN_CORRECTION, PROB_MIN), PROB_MAX); p1 = 1 - p2
        h, a = _names(e)'''
def sha(p): return hashlib.sha256(open(p, "rb").read()).hexdigest()
def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "--check"
    src = open(F, encoding="utf-8").read(); print("current sha:", sha(F))
    assert MARK not in src, "already applied"
    for n, o in (("A1", A1_OLD), ("A2", A2_OLD)):
        c = src.count(o); assert c == 1, f"anchor {n} matched {c}x"
    print("CHECK OK: anchors 2/2 unique")
    if mode != "--apply": return
    bak = F + ".bak_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + "_prebet365on"; shutil.copy2(F, bak)
    new = src.replace(A1_OLD, A1_NEW, 1).replace(A2_OLD, A2_NEW, 1)
    open(F, "w", encoding="utf-8").write(new)
    try: py_compile.compile(F, doraise=True)
    except Exception as e: shutil.copy2(bak, F); print("FAILED -> restored:", e); sys.exit(1)
    print("APPLIED. backup:", bak); print("new sha:", sha(F))
if __name__ == "__main__": main()
