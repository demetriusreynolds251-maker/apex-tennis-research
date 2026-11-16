#!/usr/bin/env python3
"""APEX-VOIDS-SA365-2026-09-23 -- record VOIDs for open picks the grader flags (retired,
walkover, cancelled). Appends to the hand CSV in the form ALIS reads: empty actual + a note
that says VOID and why. Never touches the forward log. Usage: --check | --apply"""
import csv, re, sys, shutil, datetime as dt
import apex_settle_sa365 as S
WHY = {"RET": "player retired", "WO": "walkover", "CANCELLED": "match cancelled (did not take place)"}

def ln(x):
    return str(float(x)) if x else ""

def main():
    apply = "--apply" in sys.argv
    today = dt.date.today().isoformat()
    sim = [r for r in csv.DictReader(open(S.LOG, newline=""))
           if not str(r.get("actual", "")).strip() and r.get("match_date", "") < today]
    picks = list(csv.DictReader(open(S.PICKS, newline="")))
    hand = list(csv.DictReader(open(S.HAND, newline=""))); hflds = list(hand[0].keys())
    have = {(h["match_date"], h["player"].strip().lower(), h["category"], ln(h["line"])) for h in hand}
    pk = {(p["match_id"], p["player"].strip().lower(), p["category"], ln(p["line"])): p for p in picks}
    new = []
    for s in sim:
        got, msg = S.settle_one(s)
        if got is not None or not str(msg).startswith("VOID needed"):
            continue
        m = re.search(r"\((\w+)\)", msg); flag = m.group(1) if m else "?"
        p = pk.get((s["match_id"], s["player"].strip().lower(), s["category"], ln(s["line"])))
        if not p:
            print("  no pick row for", s["match_date"], S._who(s), s["category"], "-- skipped"); continue
        hk = (p["match_date"], p["player"].strip().lower(), p["category"], ln(p["line"]))
        if hk in have:
            continue
        have.add(hk)
        row = {k: "" for k in hflds}
        row.update({"match_date": p["match_date"], "player": p["player"], "opponent": p["opponent"],
                    "category": p["category"], "tier": p.get("tier", ""), "line": p["line"],
                    "direction": p["direction"], "prob": p["prob"], "actual": "",
                    "best_of": p.get("best_of") or s.get("best_of") or "3", "in_forward_log": "1",
                    "source": S.SOURCE, "note": "VOID: " + WHY.get(flag, flag) + " (SportsAPI365)",
                    "prop_type": p.get("prop_type", "")})
        new.append({k: row.get(k, "") for k in hflds})
    print(f"VOID rows to add: {len(new)}")
    for n in new:
        print(f"  {n['match_date']} {n['player'][:22]:22} {n['category']:13} {n['line']:>5} {n['direction']:5} {n['note']}")
    if not apply or not new:
        print("(check only)" if not apply else "nothing to add"); return
    shutil.copy2(S.HAND, S.HAND + ".bak_" + dt.datetime.now().strftime("%Y%m%d_%H%M%S") + "_prevoids")
    with open(S.HAND, "a", newline="") as f:
        csv.DictWriter(f, fieldnames=hflds).writerows(new)
    print(f"APPENDED {len(new)} VOID rows -> hand CSV now {len(hand) + len(new)} rows")

if __name__ == "__main__":
    main()
