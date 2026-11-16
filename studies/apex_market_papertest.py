#!/usr/bin/env python3
"""APEX-MARKETPAPER-2026-10-31 (owner, "Go paper market"): paper test of a market second opinion on Goblin Total Games MORE.
Market chance = how often past matches went over a line this far under the book total, with a favorite this strong. Lookup is built
from the saved SportsGameOdds archive, Feb 2026 to TRAIN_END (closes before Feb 2026 are not safe). Each pick uses Apex's own last
row before the match started (bet365 total, favorite, win chance), so it only uses what was known at slip time.
Reads saved data only; touches no board, card, ranking, slip or Discord. Headline counts from TEST_START; earlier rows are labeled.
Undo: MARKET_PAPER_TEST = False. Run: python3 apex_market_papertest.py"""
import collections, glob, json, os, sqlite3
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

MARKET_PAPER_TEST = True
TEST_START = "2026-10-31"
BACKFILL_FROM = "2026-10-10"
TRAIN_END = "2026-10-10"
APEX_GATE, AGREE_AT, DISAGREE_UNDER, MISSED_AT = 70, 75, 70, 78
MIN_SAMPLE = 30
FINISH_GRADED, FINISH_DATE = 60, "2026-11-21"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "data", "logs", "market_papertest.json")
ARCHIVE = os.path.join(HERE, "data", "sgo_archive", "tennis")
CT = ZoneInfo("America/Chicago")


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _p(o):
    o = _f(o)
    return None if o is None else (100 / (o + 100) if o > 0 else -o / (-o + 100))


def _fav_band(f):
    return 0 if f < .6 else 1 if f < .7 else 2 if f < .8 else 3


def lookup():
    q = collections.defaultdict(lambda: [0, 0])
    for path in glob.glob(os.path.join(ARCHIVE, "*", "2026-*", "*.json")):
        with open(path) as fh:
            e = json.load(fh)
        s = e["status"]
        if not "2026-02" <= s["startsAt"][:10] < TRAIN_END or s.get("cancelled") or not s.get("finalized"):
            continue
        g = (e.get("results") or {}).get("game") or {}
        if max((g.get("home") or {}).get("points") or 0, (g.get("away") or {}).get("points") or 0) < 2:
            continue
        o = e.get("odds") or {}
        t = o.get("games-all-game-ou-over") or {}
        tot, act, ml = _f(t.get("closeBookOverUnder")), _f(t.get("score")), _p((o.get("points-home-game-ml-home") or {}).get("closeFairOdds"))
        if tot is None or act is None or ml is None:
            continue
        for ten in range(140, 245, 10):
            line = ten / 10 + .5
            x = q[(round(tot - line), _fav_band(max(ml, 1 - ml)))]
            x[0] += act > line
            x[1] += 1
    return q


def build():
    q = lookup()
    db = sqlite3.connect("file:%s?mode=ro" % os.path.join(HERE, "data", "board_history.sqlite"), uri=True)
    db.row_factory = sqlite3.Row
    last, res = {}, {}
    for r in db.execute("""select h.* from history h join publishes p using(publish_id) where p.platform='prizepicks' and h.board='allprops'
        and h.category='total_games' and lower(h.prop_type)='goblin' and upper(h.direction)='MORE' and h.board_day >= ? order by h.id""", (BACKFILL_FROM,)):
        k = (" v ".join(sorted(str(r["opponent"]).split(" v "))), r["line"])   # the same match can be listed in either name order
        if r["result"]:
            res[k] = r["result"]
        if r["match_start"]:
            t = datetime.fromisoformat(r["published_at"]).replace(tzinfo=CT)
            if t >= datetime.fromisoformat(r["match_start"]):
                continue
        if r["bet365_total"] is not None and r["favorite_pct"] is not None and r["win_prob"] is not None:
            last[k] = r
    db.close()
    picks = []
    for k, r in last.items():
        fav = r["favorite_pct"] / 100 if r["favorite_pct"] > 1 else r["favorite_pct"]
        x = q.get((round(r["bet365_total"] - r["line"]), _fav_band(fav)))
        if not x or x[1] < MIN_SAMPLE:
            continue
        m, a = round(100 * x[0] / x[1], 1), r["win_prob"]
        grp = "agree" if a >= APEX_GATE and m >= AGREE_AT else "disagree" if a >= APEX_GATE and m < DISAGREE_UNDER else "missed" if a < APEX_GATE and m >= MISSED_AT else "other"
        picks.append({"match": k[0], "date": r["board_day"], "line": r["line"], "apex": a, "market": m, "bet365_total": r["bet365_total"],
                      "favorite": round(fav * 100, 1), "group": grp, "result": res.get(k, "pending"), "before_test_start": r["board_day"] < TEST_START})
    return sorted(picks, key=lambda p: (p["date"], p["match"] or ""))


def _rec(L):
    return [sum(p["result"] == "hit" for p in L), sum(p["result"] == "miss" for p in L)]


def _one_per_match(L):
    best = {}
    for p in sorted(L, key=lambda p: p["apex"]):
        best[(p["match"], p["date"])] = p
    return list(best.values())


def summary(picks):
    s = {}
    for lab, L in (("test", [p for p in picks if not p["before_test_start"]]), ("before", [p for p in picks if p["before_test_start"]])):
        s[lab] = {g: _rec([p for p in L if p["group"] == g]) for g in ("agree", "disagree", "missed")}
        s[lab + "_one_per_match"] = {g: _rec(_one_per_match([p for p in L if p["group"] == g])) for g in ("agree", "disagree", "missed")}
    n = sum(sum(v) for v in s["test"].values())
    s["finished"] = n >= FINISH_GRADED or datetime.now(CT).date().isoformat() >= FINISH_DATE
    s["updated"] = datetime.now(timezone.utc).isoformat()
    return s


def run():
    if not MARKET_PAPER_TEST:
        return None
    picks = build()
    s = summary(picks)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT + ".tmp", "w") as fh:
        json.dump({"summary": s, "picks": picks}, fh, indent=1)
    os.replace(OUT + ".tmp", OUT)
    return s, len(picks)


if __name__ == "__main__":
    out = run()
    if out:
        s, n = out
        print("logged", n)
        for lab in ("test", "before"):
            t, o = s[lab], s[lab + "_one_per_match"]
            print(lab, " | ".join("%s %d-%d (one per match %d-%d)" % (g, t[g][0], t[g][1], o[g][0], o[g][1]) for g in t))
