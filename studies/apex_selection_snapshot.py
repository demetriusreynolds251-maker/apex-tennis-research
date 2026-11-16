#!/usr/bin/env python3
"""APEX-SEL-001 -- daily selection-quality snapshot.
Freezes what Apex believed BEFORE outcomes. Read-only against the board.
  --snapshot        write today's board snapshot (idempotent per date+version)
  --slip "a,b,c"    record the props actually played (player|category each)
  --show [DATE]     print a snapshot
"""
import json, os, sys, argparse
from datetime import date

SEL_DIR = "apex_learning_system/selection"
SCORER_VERSION = "002g"

def band(sc):
    for lo in (95, 90, 85, 80, 75, 70, 65, 60, 55, 50):
        if sc >= lo: return "%d-%d" % (lo, lo + 4) if lo < 95 else "95+"
    return "<50"

def snapshot():
    import apex_edge_tracker as a
    board, note = a.load_current_board()
    if not board:
        print("no active board -- nothing to snapshot (%s)" % note); return 1
    rec = a.records()
    rows = []
    for p in board:
        sc, ev, lvl, up, down = a.apex_score(p.get("prob"), p["category"], bool(p.get("bo5")), rec)
        rows.append({"match_id": p.get("match_id", ""), "player": p.get("player"),
                     "opponent": p.get("opponent"), "category": p["category"],
                     "line": p.get("line"), "direction": p.get("direction"),
                     "prob": p.get("prob"), "best_of": 5 if p.get("bo5") else 3,
                     "score": sc, "score_band": band(sc), "evidence_level": ev,
                     "attention": lvl, "warnings": down, "reasons": up})
    rows.sort(key=lambda r: -r["score"])
    for i, r in enumerate(rows, 1): r["rank"] = i
    os.makedirs(SEL_DIR, exist_ok=True)
    today = date.today().isoformat()
    path = os.path.join(SEL_DIR, "board_%s.json" % today)
    prev = json.load(open(path)) if os.path.exists(path) else {}
    doc = {"date": today, "scorer_version": SCORER_VERSION, "written_ts": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
           "board_size": len(rows), "picks": rows, "played_slip": prev.get("played_slip", [])}
    if prev and prev.get("scorer_version") == SCORER_VERSION and prev.get("board_size") == len(rows):
        print("snapshot already current for %s (v%s, %d picks) -- not rewritten" % (today, SCORER_VERSION, len(rows))); return 0
    if prev: doc["superseded"] = prev.get("written_ts")
    json.dump(doc, open(path, "w"), indent=1)
    print("snapshot %s | v%s | %d picks | bands: %s" % (path, SCORER_VERSION, len(rows),
          ", ".join("%s×%d" % (b, sum(1 for r in rows if r["score_band"] == b)) for b in sorted({r["score_band"] for r in rows}, reverse=True))))
    return 0

def slip(spec):
    today = date.today().isoformat()
    path = os.path.join(SEL_DIR, "board_%s.json" % today)
    if not os.path.exists(path): print("no snapshot for %s -- run --snapshot first" % today); return 1
    doc = json.load(open(path))
    legs = [s.strip() for s in spec.split(",") if s.strip()]
    doc["played_slip"] = legs
    matched = []
    for leg in legs:
        pl, _, cat = leg.partition("|")
        hit = next((r for r in doc["picks"] if pl.lower() in (r["player"] or "").lower()
                    and (not cat or cat.strip().lower() == r["category"])), None)
        matched.append({"leg": leg, "rank": hit["rank"] if hit else None, "score": hit["score"] if hit else None})
    doc["played_slip_matched"] = matched
    json.dump(doc, open(path, "w"), indent=1)
    print("slip recorded (%d legs):" % len(legs))
    for m in matched: print("  %-40s rank %s score %s" % (m["leg"], m["rank"] or "NOT ON BOARD", m["score"] or "-"))
    return 0

def show(d=None):
    d = d or date.today().isoformat()
    path = os.path.join(SEL_DIR, "board_%s.json" % d)
    if not os.path.exists(path): print("no snapshot for", d); return 1
    doc = json.load(open(path))
    print("%s | v%s | %d picks | written %s" % (doc["date"], doc["scorer_version"], doc["board_size"], doc["written_ts"]))
    for r in doc["picks"][:15]:
        print(" #%-3d %-22s %-14s %-11s %3d [%s] %s %s" % (r["rank"], (r["player"] or "")[:21], r["category"],
              "%s %s" % (r["line"], r["direction"]), r["score"], r["score_band"], r["evidence_level"],
              "BO5" if r["best_of"] == 5 else ""))
    if doc.get("played_slip"): print("played:", doc["played_slip"])
    return 0

ap = argparse.ArgumentParser()
ap.add_argument("--snapshot", action="store_true")
ap.add_argument("--slip", default=None)
ap.add_argument("--show", nargs="?", const=True, default=None)
a_ = ap.parse_args()
sys.exit(snapshot() if a_.snapshot else slip(a_.slip) if a_.slip else
         show(None if a_.show is True else a_.show) if a_.show else ap.print_help())
