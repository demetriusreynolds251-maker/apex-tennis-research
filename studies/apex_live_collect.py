#!/usr/bin/env python3
"""APEX-LIVECOLLECT-2026-11-04 (owner, "Go live collect"): save PrizePicks' LIVE in-play tennis lines.
PrizePicks keeps lines up during a match (Total Games, Total Games Won, Total Sets, standard + Demon) and the
partner API returns them with in_game=true (status 'in_progress'). Apex never asked for them, so nothing was saved.
Every pass (3 min while something is live, 6 min when nothing is): one PrizePicks request, then for each in-play
line one row -> data/live_lines/YYYY-MM-DD.jsonl with the line, PrizePicks' own live match score (sets + games,
current set), the player's running count, and the latest Bet365 / Pinnacle live prices from SportsAPI365 (per match,
refreshed every 10 min). Writes ONLY data/live_lines/. Boards untouched. One #system line a day (after 9 AM CT).
Honours the shared PrizePicks pause (data/logs/pp_cooldown.json) and lock; a 403/429 here pauses reads like the fetch does.
Run: python3 apex_live_collect.py --loop   (pid in data/live_lines/collector.pid)   | one pass: python3 apex_live_collect.py"""
import os, sys, json, time, fcntl, datetime as dt
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
OUT = os.path.join(HERE, "data", "live_lines")
STATE = os.path.join(OUT, "state.json")
LOGF = os.path.join(OUT, "collector.log")
PIDF = os.path.join(OUT, "collector.pid")
LIVE_EVERY, IDLE_EVERY, ODDS_EVERY = 180, 360, 600

def log(msg):
    line = "[%s] %s" % (dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), msg)
    print(line, flush=True)
    try:
        with open(LOGF, "a") as f: f.write(line + "\n")
    except Exception: pass

def _load(path, default):
    try:
        with open(path) as f: return json.load(f)
    except Exception: return default

def _save(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w") as f: json.dump(obj, f)
    os.replace(tmp, path)

def pp_live_body():
    """{'data','included'} from partner-api with in_game=true, or None. Same pause/lock/log as the fetch gate."""
    import requests, apex_ops as ops
    with open(ops.PP_LOCK_FILE, "a") as lockf:
        fcntl.flock(lockf, fcntl.LOCK_EX)
        if ops.pp_cooldown_until():
            log("PrizePicks paused -- no request"); return None
        ops._pp_wait_clear()                  # APEX-PPSPACING-2026-11-10: stay 20 s clear of every other Apex PrizePicks call
        r = requests.get(ops._core_const("PARTNER_API"),
                         params={"league_id": 5, "per_page": 1000, "single_stat": True, "in_game": True},
                         headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
                                  "Referer": "https://app.prizepicks.com/", "Origin": "https://app.prizepicks.com"}, timeout=25)
        ops._pp_log_request("live_collect", r.status_code)
        if r.status_code in (403, 429):
            until = time.time() + ops.PP_COOLDOWN_SEC
            ops._pp_write_json(ops.PP_COOLDOWN_FILE, {"until": until, "status": r.status_code, "set_at": time.time(), "caller": "live_collect"})
            log("PrizePicks HTTP %d -- paused all reads %d min" % (r.status_code, ops.PP_COOLDOWN_SEC // 60)); return None
        r.raise_for_status()
        body = r.json()
        return body if isinstance(body, dict) and "data" in body else None

def sa365_live_odds(cache, want):
    """want = set of norm pairs that have PrizePicks live lines; only those get an odds call. {norm pair -> {'ts', 'bet365', 'pinnacle', 'score', 'status'}} for matches in play, refreshed every ODDS_EVERY s."""
    try:
        import apex_settle_sa365 as S
    except Exception as e:
        log("sa365 unavailable: %s" % e); return cache
    now = time.time()
    if now - float(cache.get("_ts") or 0) < ODDS_EVERY:
        return cache
    p, err = S.api("/extend/api/events/live")
    if err:
        log("sa365 live list: %s" % err); return cache
    rows = p.get("results") if isinstance(p, dict) and isinstance(p.get("results"), list) else (p if isinstance(p, list) else [])
    out = {"_ts": now}
    n = 0
    for e in rows:
        a, b = e.get("player1") or e.get("participant1"), e.get("player2") or e.get("participant2")
        a = a.get("name") if isinstance(a, dict) else a; b = b.get("name") if isinstance(b, dict) else b
        if not a or not b or n >= 12: continue
        key = "|".join(sorted((S._norm(a), S._norm(b))))
        if key not in want: continue
        s1, _ = S.api("/extend/api/odds/summary/%s" % e.get("id")); time.sleep(0.2); n += 1
        res = (s1 or {}).get("result") if isinstance(s1, dict) else None
        rec = {"sa_id": e.get("id"), "status": e.get("status"), "score": e.get("score"), "points": e.get("points"), "p1": a, "p2": b}
        for book in ("Bet365", "Pinnacle"):
            v = (res or {}).get(book) if isinstance(res, dict) else None
            if isinstance(v, dict): rec[book.lower()] = {m: (d.get("end") if isinstance(d, dict) else None) for m, d in v.items()}
        out[key] = rec
    return out

def one_pass(state, odds):
    body = pp_live_body()
    if body is None: return 0, 0, odds
    inc = {}
    for i in body.get("included") or []:
        inc[(i.get("type"), str(i.get("id")))] = i
    live = [r for r in body.get("data") or [] if (r.get("attributes") or {}).get("status") == "in_progress"]
    if not live: return 0, 0, odds
    import apex_settle_sa365 as S
    want = set()
    for r in live:
        rel = r.get("relationships") or {}; d = (rel.get("game") or {}).get("data") or {}
        gi = ((inc.get((d.get("type"), str(d.get("id")))) or {}).get("attributes") or {}).get("metadata", {}).get("game_info") or {}
        h, aw = (gi.get("home") or {}).get("name"), (gi.get("away") or {}).get("name")
        if h and aw: want.add("|".join(sorted((S._norm(h), S._norm(aw)))))
    odds = sa365_live_odds(odds, want)
    ts = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    day = dt.datetime.now().strftime("%Y-%m-%d")
    rows, matches = [], set()
    for r in live:
        a = r.get("attributes") or {}; rel = r.get("relationships") or {}
        def _rel(t):
            d = (rel.get(t) or {}).get("data") or {}
            return inc.get((d.get("type"), str(d.get("id")))) or {}
        pl = (_rel("new_player").get("attributes") or {}).get("display_name") or a.get("description")
        g = _rel("game").get("attributes") or {}; gi = (g.get("metadata") or {}).get("game_info") or {}
        home, away = (gi.get("home") or {}).get("name"), (gi.get("away") or {}).get("name")
        opp = away if home == pl else home
        sc = _rel("score").get("attributes") or {}
        key = "|".join(sorted((S._norm(pl), S._norm(opp)))) if opp else None
        o = odds.get(key) if key else None
        rows.append({"ts": ts, "pid": r.get("id"), "game_id": a.get("game_id"), "player": pl, "opponent": opp,
                     "stat": a.get("stat_type"), "line": a.get("line_score"), "odds_type": a.get("odds_type"),
                     "line_updated": a.get("updated_at"), "start": a.get("start_time"),
                     "count": sc.get("score"), "count_updated": sc.get("updated_at"), "final": sc.get("is_final"), "retired": sc.get("is_retired"),
                     "period": gi.get("current_period"), "match_score": gi.get("match_score"), "game_status": g.get("status"),
                     "sa365": o})
        matches.add(a.get("game_id"))
    with open(os.path.join(OUT, day + ".jsonl"), "a") as f:
        for row in rows: f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return len(rows), len(matches), odds

def daily_line(state):
    """one #system line a day after 9 AM CT: what yesterday saved"""
    try:
        import apex_ops as ops
        now = ops.now_ct()
        if now.hour < 9 or state.get("posted") == now.strftime("%Y-%m-%d"): return
        y = (now - dt.timedelta(days=1)).strftime("%Y-%m-%d")
        n, lines, games = 0, set(), set()
        p = os.path.join(OUT, y + ".jsonl")
        if os.path.exists(p):
            for ln in open(p):
                try: d = json.loads(ln)
                except Exception: continue
                n += 1; lines.add(d.get("pid")); games.add(d.get("game_id"))
        ops.send_discord("system", "📡 Live lines %s: saved %d snapshots of %d PrizePicks in-play lines across %d matches (data/live_lines)." % (y, n, len(lines), len(games)))
        state["posted"] = now.strftime("%Y-%m-%d"); _save(STATE, state)
    except Exception as e:
        log("daily line failed: %s" % e)

def main(loop):
    os.makedirs(OUT, exist_ok=True)
    state = _load(STATE, {}); odds = {}
    if loop:
        with open(PIDF, "w") as f: f.write(str(os.getpid()))
    while True:
        try:
            n, m, odds = one_pass(state, odds)
            log("saved %d live lines across %d matches" % (n, m))
            state["last_pass"] = time.time(); state["last_rows"] = n; _save(STATE, state)
            daily_line(state)
        except Exception as e:
            log("pass failed: %s: %s" % (type(e).__name__, str(e)[:120])); n = 0
        if not loop: break
        time.sleep(LIVE_EVERY if n else IDLE_EVERY)

if __name__ == "__main__":
    main("--loop" in sys.argv)
