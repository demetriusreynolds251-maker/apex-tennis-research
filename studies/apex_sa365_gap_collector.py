#!/usr/bin/env python3
"""APEX-SA365-GAPCOLLECT-2026-09-23 -- collects what the Bet365-vs-Pinnacle gap study needs.
Writes ONLY data/sa365_gap/. Each pass:
  (a) matches starting within 120 min -> save Bet365 pre-match prices (overwritten each pass,
      so the last save before start is kept)                      prematch/<upcomingId>.json
  (b) matches now live, first time seen -> save odds summary (opening / kickoff / latest per
      book, incl. Pinnacle's pre-start prices) + last-10 moves     live/<liveId>.json
Usage: python3 apex_sa365_gap_collector.py [--loop MINUTES]"""
import sys, json, time, datetime as dt
from pathlib import Path
import apex_settle_sa365 as S   # reuses the SportsAPI365 client (key, browser name tag, retries)

OUT = Path(__file__).resolve().parent / "data" / "sa365_gap"
PRE, LIVE = OUT / "prematch", OUT / "live"
WINDOW_MIN = 120

def rows(p):
    if isinstance(p, dict):
        for k in ("results", "result", "data"):
            if isinstance(p.get(k), list):
                return p[k]
    return p if isinstance(p, list) else []

def start_secs(e):
    v = e.get("startTimestamp")
    if isinstance(v, (int, float)):
        return v / 1000 if v > 1e11 else v
    return None

def one_pass():
    PRE.mkdir(parents=True, exist_ok=True); LIVE.mkdir(parents=True, exist_ok=True)
    now = time.time(); n_pre = n_live = 0; errs = []
    for tour in ("atp", "wta"):
        for page in (1, 2, 3):
            p, err = S.api(f"/extend/api/events/upcoming/{tour}?page={page}")
            if err:
                errs.append(f"upcoming {tour} p{page}: {err}"); break
            evs = rows(p)
            if not evs:
                break
            for e in evs:
                s = start_secs(e)
                if not s or not (now < s <= now + WINDOW_MIN * 60):
                    continue
                q, err = S.api(f"/extend/api/odds/pre-match/{e.get('id')}"); time.sleep(0.2)
                if err or not q:
                    continue
                (PRE / f"{e.get('id')}.json").write_text(json.dumps({"event": e, "fetched": now, "prematch": q}))
                n_pre += 1
    p, err = S.api("/extend/api/events/live")
    if err:
        errs.append(f"live: {err}")
    for e in rows(p):
        f = LIVE / f"{e.get('id')}.json"
        if f.exists():
            continue
        s1, _ = S.api(f"/extend/api/odds/summary/{e.get('id')}"); time.sleep(0.2)
        s2, _ = S.api(f"/extend/api/odds/summary/movements/last-10/{e.get('id')}"); time.sleep(0.2)
        if not s1:
            continue
        f.write_text(json.dumps({"event": e, "fetched": now, "summary": s1, "moves": s2}))
        n_live += 1
    stamp = dt.datetime.now().isoformat(timespec="seconds")
    print(f"[{stamp}] prematch saved {n_pre} | new live summaries {n_live} | totals: "
          f"prematch {len(list(PRE.glob('*.json')))}, live {len(list(LIVE.glob('*.json')))}"
          + (f" | errors: {'; '.join(errs)}" if errs else ""), flush=True)

if __name__ == "__main__":
    if "--loop" in sys.argv:
        mins = float(sys.argv[sys.argv.index("--loop") + 1])
        while True:
            try:
                one_pass()
            except Exception as ex:
                print("pass failed:", type(ex).__name__, ex, flush=True)
            time.sleep(mins * 60)
    else:
        one_pass()
