"""One-time settle of the learning manual-review queue from props_db
(APEX-NAMECOLLISION-2026-10-22).

The learning retry engine looked WTA names up on the men's tour first, so
Ann Li became Alan Li (and 7 other women got a man's name) and every pick
on them was parked in data/learning/manual_review.json as a name collision.
props_db already graded those matches from SA365, so this reads the actual
stat from there and records the outcome in Dataset A.

- Match rule: same player, opponent (props_db may add " 1st Set"), category
  and line, nearest match_date; else same player/opponent/category with
  start_utc within 2 days of the pick's match_date.
- Each pick counts once: rows for the same player/opponent/stat/line/side
  that hit the same props_db match (the pick logged on two dates) are
  collapsed; only the latest row's eval_id gets the outcome, the others
  are removed from the queue without a second outcome.
- Picks with no props_db match stay in manual_review.json.

    python3 apex_manual_review_settle.py            # dry run (default)
    python3 apex_manual_review_settle.py --write
"""
import argparse
import collections
import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).parent
MANUAL_REVIEW_FILE = HERE / "data" / "learning" / "manual_review.json"
PROPS_DB = HERE / "data" / "props_db.sqlite"
SETTLED_LOG = HERE / "data" / "learning" / "manual_review_settled_2026-10-22.json"
# Dataset A only allows a fixed list of outcome_source values (CHECK
# constraint); a hand-run settle is "manual_override". The settled log
# below records that the grade came from props_db.
SOURCE = "manual_override"
CATEGORY = {"total_games_won": "games_won", "break_points_won": "breaks",
            "total_tie_breaks": "tiebreaks"}


def _find(con, p):
    cat = CATEGORY.get(p["stat_type"], p["stat_type"])
    r = con.execute(
        "select actual, score, match_date, start_utc from projections where player=? "
        "and opponent like ? and category=? and line_last=? and actual is not null "
        "order by abs(julianday(match_date)-julianday(?)) limit 1",
        (p["player"], p["opponent"] + "%", cat, p["line"], p["match_date"])).fetchone()
    if r is None:
        r = con.execute(
            "select actual, score, match_date, start_utc from projections where player=? "
            "and opponent like ? and category=? and actual is not null "
            "and abs(julianday(start_utc)-julianday(?))<=2 limit 1",
            (p["player"], p["opponent"] + "%", cat, p["match_date"])).fetchone()
    return r


def _outcome(actual, p):
    line = float(p["line"])
    if p["direction"] == "LESS":
        return "HIT" if actual < line else "BUST"
    return "HIT" if actual > line else "BUST"


def build():
    queue = json.load(open(MANUAL_REVIEW_FILE))
    con = sqlite3.connect(f"file:{PROPS_DB}?mode=ro", uri=True)
    groups = collections.OrderedDict()
    unmatched = []
    for p in queue:
        r = _find(con, p)
        if r is None:
            unmatched.append(p)
            continue
        actual, score, _md, start_utc = r
        key = (p["player"], p["opponent"], p["stat_type"], float(p["line"]),
               p["direction"], start_utc or _md, actual)
        groups.setdefault(key, {"rows": [], "actual": actual, "score": score,
                                "start_utc": start_utc})["rows"].append(p)
    settled = []
    for key, g in groups.items():
        rows = sorted(g["rows"], key=lambda x: x.get("match_date", ""))
        keep = rows[-1]
        dup_ids = sorted({x["eval_id"] for x in rows} - {keep["eval_id"]})
        settled.append({
            "player": keep["player"], "opponent": keep["opponent"],
            "stat_type": keep["stat_type"], "line": keep["line"],
            "direction": keep["direction"], "match_date": keep["match_date"],
            "pick_dates": sorted({x["match_date"] for x in rows}),
            "eval_id": keep["eval_id"], "duplicate_eval_ids": dup_ids,
            "queue_rows": len(rows), "actual": g["actual"], "score": g["score"],
            "start_utc": g["start_utc"], "outcome": _outcome(g["actual"], keep),
        })
    return queue, settled, unmatched


def report(queue, settled, unmatched):
    matched_rows = sum(s["queue_rows"] for s in settled)
    w = sum(s["outcome"] == "HIT" for s in settled)
    print(f"Queue rows: {len(queue)} | matched to props_db: {matched_rows} | "
          f"left in queue: {len(unmatched)}")
    print(f"Unique picks to settle (duplicates collapsed): {len(settled)} | "
          f"{w} W - {len(settled) - w} L")
    print("\nPer player (picks settled, W-L | queue rows matched | rows left):")
    left = collections.Counter(p["player"] for p in unmatched)
    by = collections.defaultdict(lambda: [0, 0, 0])
    for s in settled:
        b = by[s["player"]]
        b[0] += s["outcome"] == "HIT"; b[1] += s["outcome"] != "HIT"; b[2] += s["queue_rows"]
    for pl in sorted(set(by) | set(left), key=lambda x: -(by[x][2] + left[x])):
        b = by[pl]
        print(f"  {pl}: {b[0] + b[1]} picks, {b[0]}-{b[1]} | {b[2]} rows | {left[pl]} left")
    print("\nAnn Li v Zeynep Sonmez:")
    for s in settled:
        if s["player"] == "Ann Li" and s["opponent"] == "Zeynep Sonmez":
            print(f"  {s['stat_type']} {s['direction']} {s['line']}: actual {s['actual']} -> "
                  f"{'WIN' if s['outcome'] == 'HIT' else 'LOSS'} "
                  f"(pick dates {', '.join(s['pick_dates'])}, {s['queue_rows']} rows)")
    print("\nLeft in queue (no props_db match):")
    for (pl, opp, md), n in sorted(collections.Counter(
            (p["player"], p["opponent"], p["match_date"]) for p in unmatched).items(),
            key=lambda x: x[0][2]):
        print(f"  {md} {pl} v {opp}: {n}")


def write(queue, settled, unmatched):
    import dataset_a_capture as d1
    con = sqlite3.connect(d1.DB_PATH)
    already = 0
    for s in settled:
        row = con.execute("select lifecycle_state, outcome from evaluations where eval_id=?",
                          (s["eval_id"],)).fetchone()
        if row and row[0] == "OUTCOME_RECORDED":
            s["skipped"] = "outcome already recorded"
            already += 1
            continue
        d1.record_outcome(s["eval_id"], s["outcome"], SOURCE)
        # record_outcome swallows DB errors (@_safe), so read it back
        row = con.execute("select lifecycle_state, outcome from evaluations where eval_id=?",
                          (s["eval_id"],)).fetchone()
        if row and row[0] == "OUTCOME_RECORDED" and row[1] == s["outcome"]:
            s["written_at"] = datetime.now().isoformat()
            s["grade_source"] = "props_db"
        else:
            s["write_failed"] = True
    con.close()
    failed = [s for s in settled if s.get("write_failed")]
    failed_ids = {s["eval_id"] for s in failed} | {i for s in failed for i in s["duplicate_eval_ids"]}
    keep_rows = unmatched + [p for p in queue if p["eval_id"] in failed_ids]
    tmp = str(MANUAL_REVIEW_FILE) + ".tmp"
    with open(tmp, "w") as f:
        json.dump(keep_rows, f, indent=2, default=str)
    os.replace(tmp, MANUAL_REVIEW_FILE)
    with open(SETTLED_LOG, "w") as f:
        json.dump(settled, f, indent=2, default=str)
    ok = len(settled) - already - len(failed)
    print(f"\nWROTE: {ok} outcomes ({already} already had one, {len(failed)} failed and "
          f"stay queued), manual_review.json now {len(keep_rows)} rows, log {SETTLED_LOG.name}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    q, s, u = build()
    report(q, s, u)
    if a.write:
        write(q, s, u)
    else:
        print("\nDRY RUN - nothing written.")
