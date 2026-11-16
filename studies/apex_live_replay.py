#!/usr/bin/env python3
"""APEX-LIVEREPLAY-2026-11-01 (owner, "Fix all"): replays saved official boards through the LIVE code:
apex_edge_tracker.board_hold_reason and _rerank_after_top3. Only inputs that live data can no longer give for an
old day (book total, favorite, signals, 17.5 result) come from each saved row. Writes nothing live, posts nothing.
Usage: apex_live_replay.py [first_day last_day]"""
import collections as C, os, pickle, re, sqlite3, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
sys.path.insert(0, HERE)
import apex_edge_tracker as t, apex_card_signals as cs, apex_set_games as sg
_real_print = print


def _official(h, day, board):
    """The last publish before that board's first match."""
    ps = h.execute("select publish_id,min(published_at) t from history where board_day=? and board=? group by publish_id order by t", (day, board)).fetchall()
    for i, (pid, ts) in enumerate(ps):
        st = [r[0] for r in h.execute("select match_start from history where publish_id=? and board=? and spot_kind='main' and match_start!=''", (pid, board))]
        if not st:
            continue
        f = _utc_as_ct(min(st)[:19])
        if ts[:19] >= f:
            continue
        if i + 1 == len(ps) or ps[i + 1][1][:19] >= f:
            return pid
    return None


def _utc_as_ct(s):
    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo
    d = datetime.fromisoformat(s).replace(tzinfo=timezone.utc).astimezone(ZoneInfo("America/Chicago"))
    return d.isoformat()[:19]


OTHER = ("no book", "room", "blowout", "set win", "17.5", "fantasy less", "double fault", "after a match", "category", "line is")   # saved hold reasons
_OWN = {}


def _own_win(pl, op, day):
    """The player's own win chance on an old day, from the saved odds archive."""
    import datetime as D, glob, json, unicodedata
    def last(s):
        x = re.sub(r"[^a-z ]", " ", unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()).split()
        return x[-1] if x else ""
    def pr(o):
        try:
            o = float(o)
        except (TypeError, ValueError):
            return None
        return 100 / (o + 100) if o > 0 else -o / (-o + 100)
    if not _OWN:
        _OWN["_"] = 1
        for f in glob.glob("data/sgo_archive/tennis/*/2026-1*/*.json") + glob.glob("data/sgo_archive/tennis/*/2026-09*/*.json"):
            e = json.load(open(f))
            o = e.get("odds") or {}
            hh, aa = o.get("points-home-game-ml-home") or {}, o.get("points-away-game-ml-away") or {}
            a, b = pr(hh.get("closeFairOdds") or hh.get("openFairOdds")), pr(aa.get("closeFairOdds") or aa.get("openFairOdds"))
            if a and b:
                x, y = last(e["teams"]["home"]["names"]["long"]), last(e["teams"]["away"]["names"]["long"])
                _OWN.setdefault(frozenset((x, y)), []).append((e["status"]["startsAt"][:10], x, a / (a + b)))
    for d, x, w in _OWN.get(frozenset((last(pl), last(op))), []):
        if abs((D.date.fromisoformat(d) - D.date.fromisoformat(day)).days) <= 2:
            return w if last(pl) == x else 1 - w
    return None


def _line70(x):
    if x["category"] != "fantasy_score" or str(x["direction"]).upper() != "MORE" or str(x["prop_type"]).lower() != "goblin" or (x["line"] or 0) < t.LINE70_MIN_LINE:
        return False
    w = _own_win(x["player"], x["opponent"], x["board_day"])
    return w is not None and w < t.LINE70_MIN_WIN


def _p(x):
    pr = (x["win_prob"] or 0) / 100.0
    p = {"player": x["player"], "opponent": x["opponent"], "category": x["category"], "direction": x["direction"],
         "line": x["line"], "prop_type": x["prop_type"], "prob": pr, "prob_cal": pr, "match_id": "h", "match_date": x["board_day"],
         "slip_start_utc": x["match_start"], "_h": x}
    return p


def _result(x):
    return x["result"] if x else None


def boards(days):
    h = sqlite3.connect("file:data/board_history.sqlite?mode=ro", uri=True)
    h.row_factory = sqlite3.Row
    fs = C.defaultdict(list)
    for d, a, b, l, m, k in pickle.load(open("_backups/set_games_test_2026-11-01/best.pkl", "rb")):
        fs[d].append((a, b, l, m))
    tmp = tempfile.mktemp()
    t.CUSHION_BLOCK_PATH = tmp
    import apex_cushion_tracker as ct
    ct.log_build = lambda *a, **k: None
    cs.book_total = lambda p: (p.get("_h") or {})["bet365_total"] if p.get("_h") else None
    cs.match_favorite = lambda p: ((p.get("_h")["favorite_pct"] or 0) / 100.0 or None) if p.get("_h") else None
    cs.net_score = lambda p: (0, 0, (p.get("_h")["net_signals"] or 0) if p.get("_h") else 0, 5)
    cs.played_yesterday = lambda p: bool(p.get("_h") and p["_h"]["sig_played"])
    t.line175_skip_reason = lambda p: None
    t.line175_penalty = lambda p: (0.0, None)
    t.line70_hold_reason = lambda p: None
    t.no_book_total_reason = lambda p: None
    t._surface_hold = lambda p: None
    out = {}
    for day in days:
        P = {}
        for b in ("elite6", "top3"):
            pid = _official(h, day, b)
            if not pid:
                continue
            for x in h.execute("select * from history where publish_id=? and board=? and spot_kind in('main','backup','held')", (pid, b)):
                why = (x["reason"] or "").lower()
                if x["win_prob"] is None or x["win_prob"] < 70 or (x["apex_score"] or 0) < 67:
                    continue
                if any(w in why for w in OTHER) or t._is_unplayable(_p(x)) or _line70(x):
                    continue
                P.setdefault(x["prop_key"], x)
        pool = [{"p": _p(x), "sc": x["apex_score"], "score": x["apex_score"], "r": x["result"]} for x in P.values()]
        ent = []
        for a, b, l, m in fs.get(day, []):
            pr = sg.RANK_75 if l < 8 else sg.RANK_85
            ent.append({"p": {"player": "match", "opponent": "%s v %s" % (a, b), "category": "1st_set_total_games", "line": l,
                              "direction": "MORE", "prop_type": "goblin", "prob": pr, "prob_cal": pr}, "sc": int(pr * 100),
                        "score": int(pr * 100), "r": "hit" if m else "miss"})
        sg.board_entries = lambda e=ent: list(e)
        for flag, n in (("top3", 3), ("elite6", 6)):
            res = {"scored": [dict(d) for d in pool][:n]}
            if not res["scored"]:
                continue
            t._rerank_after_top3(res, lambda: {"scored": [dict(d) for d in pool]}, flag=flag)
            out[day, flag] = [(d["p"], d.get("r")) for d in res["scored"]]
    try:
        os.remove(tmp)
    except OSError:
        pass
    return out


def tally(b, days):
    won = lambda L: len(L) >= 2 and all(r in ("hit", "void", "push") for _, r in L)
    T = C.Counter()
    for d in days:
        e6 = b.get((d, "elite6"), [])
        T["Top 3"] += won(b.get((d, "top3"), []))
        T["Elite 5"] += won(e6[:5])
        T["Elite 6"] += won(e6)
        T["won"] += sum(r == "hit" for _, r in e6)
        T["lost"] += sum(r == "miss" for _, r in e6)
        T["open"] += sum(r is None for _, r in e6)
    return dict(T)


if __name__ == "__main__":
    a, z = (sys.argv[1], sys.argv[2]) if len(sys.argv) > 2 else ("2026-10-13", "2026-10-31")
    h = sqlite3.connect("file:data/board_history.sqlite?mode=ro", uri=True)
    days = [r[0] for r in h.execute("select distinct board_day from history where board='top3' and board_day between ? and ? order by 1", (a, z))]
    b = boards(days)
    days = [d for d in days if (d, "top3") in b]
    mid = days[:len(days) // 2 + 1]
    print(len(days), "days", tally(b, days))
    print("first half", tally(b, mid))
    print("second half", tally(b, days[len(mid):]))
    for d in days[-3:]:
        for f in ("top3", "elite6"):
            print(d, f, [((p["opponent"] if p["player"] == "match" else p["player"])[:28], p["category"][:6], p["line"], r) for p, r in b[d, f]])
