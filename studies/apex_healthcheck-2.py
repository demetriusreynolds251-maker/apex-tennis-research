#!/usr/bin/env python3
"""
APEX-HEALTHCHECK-2026-08-23
Project Apex Intelligence / OpenClaw (DEMETRIUS)

Daily operational healthcheck + heartbeat. Written because of the failure of
2026-08-21: the Discord bot had been silently dead since Jul 23 and Mission
Control since Aug 18, and nothing said a word. A monitor that only speaks when
something breaks is indistinguishable from a monitor that is itself dead — so
this posts EVERY day, pass or fail. The absence of the heartbeat is the alarm.

TWO HARD RULES
  1. REPORTS, NEVER REMEDIATES. It does not start, stop, kill or restart any
     process. It does not touch a frozen model. It does not edit any file
     except its own state file. Refresh/rebuild only run with --run-refresh.
  2. FAIL-OPEN. Every check is wrapped; a crash in one check can never stop the
     others or take down what it is checking. If the whole run dies, it still
     tries to post that it died.

CHECKS (the ten dependencies)
  1 data refresh freshness      6 prop engine health
  2 player state freshness      7 forward log health
  3 fragility state             8 settlement health
  4 fragility validation gate   9 mission control health
  5 discord bot health         10 credential/config hygiene

USAGE (from the project folder)
    python3 apex_healthcheck.py                 # check + print, no Discord post
    python3 apex_healthcheck.py --post          # check + post heartbeat to Discord
    python3 apex_healthcheck.py --run-refresh --post
                                                # ALSO run the refresh + rebuild
                                                # chain first, in the enforced order
    python3 apex_healthcheck.py --selftest      # no side effects, no network
    python3 apex_healthcheck.py --install-plist # print a launchd plist, install nothing

EXIT CODES: 0 all OK · 1 warnings only · 2 one or more failures
"""
import argparse, json, os, re, subprocess, sys, time, urllib.request
from datetime import datetime, timedelta

MARKER = "APEX-HEALTHCHECK-2026-08-23"
HERE = os.path.dirname(os.path.abspath(__file__)) or "."
STATE_FILE = os.path.join(HERE, "apex_healthcheck_state.json")

DATA_DIR = "ATP & WTA, 1968-2026"
CORE = "openclaw_core.py"
ACM_SHA_PREFIX = "8d90fb5c"
FRAG_MODEL_SHA_PREFIX = "8bf6937a"

OK, WARN, FAIL = "OK", "WARN", "FAIL"


class Report:
    def __init__(self):
        self.rows = []

    def add(self, name, status, detail):
        self.rows.append((name, status, detail))

    def worst(self):
        if any(s == FAIL for _, s, _ in self.rows): return FAIL
        if any(s == WARN for _, s, _ in self.rows): return WARN
        return OK

    def text(self):
        icon = {OK: "🟢", WARN: "🟡", FAIL: "🔴"}
        head = "%s %s — %s" % (icon[self.worst()],
                               "APEX HEALTHCHECK",
                               datetime.now().strftime("%a %b %d, %-I:%M %p"))
        lines = [head, ""]
        for n, s, d in self.rows:
            lines.append("%s %-22s %s" % (icon[s], n, d))
        bad = [r for r in self.rows if r[1] == FAIL]
        if bad:
            lines.append("")
            lines.append("ACTION REQUIRED: " + "; ".join(r[0] for r in bad))
        return "\n".join(lines)


def guarded(rep, name):
    """Decorator-ish: run a check, never let it raise."""
    def wrap(fn):
        try:
            status, detail = fn()
        except Exception as e:
            status, detail = FAIL, "check itself failed: %s: %s" % (type(e).__name__, e)
        rep.add(name, status, detail)
        return status
    return wrap


# ---------------------------------------------------------------- helpers
def _run(cmd, timeout=900):
    p = subprocess.run(cmd, shell=True, cwd=HERE, capture_output=True, text=True, timeout=timeout)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def _file_age_hours(path):
    return (time.time() - os.path.getmtime(path)) / 3600.0


def _latest_tourney_date(path):
    import csv
    m = ""
    with open(path, newline="", encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f):
            d = (row.get("tourney_date") or "").strip()
            if d > m: m = d
    return m


def _sha_prefix(path, n=8):
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""): h.update(c)
    return h.hexdigest()[:n]


def _webhook(channel):
    """Find a webhook WITHOUT importing openclaw_core (12k lines, side effects)."""
    cfg = os.path.join(HERE, "config.json")
    if os.path.exists(cfg):
        try:
            with open(cfg) as f:
                u = json.load(f).get("discord", {}).get(channel)
            if u: return u
        except Exception:
            pass
    core = os.path.join(HERE, CORE)
    if os.path.exists(core):
        src = open(core, encoding="utf-8", errors="replace").read()
        m = re.search(r'"%s"\s*:\s*"(https://discord\.com/api/webhooks/[^"]+)"' % re.escape(channel), src)
        if m: return m.group(1)
    return None


def post_discord(channel, message):
    """Post via webhook. Returns True/False; never raises."""
    try:
        url = _webhook(channel)
        if not url: return False
        body = json.dumps({"content": message[:1900]}).encode()
        # A User-Agent is REQUIRED. Discord sits behind Cloudflare, which rejects
        # urllib's default "Python-urllib/3.x" with 403 error 1010 before the
        # request ever reaches Discord. Confirmed live 2026-08-23: without this
        # header 403/1010, with it 204. The bot's own send_discord() never hits
        # this because requests sets a User-Agent by default.
        req = urllib.request.Request(url, data=body, headers={
            "Content-Type": "application/json",
            "User-Agent": "ApexHealthcheck/1.0 (+openclaw)"})
        with urllib.request.urlopen(req, timeout=20) as r:
            return 200 <= r.status < 300
    except Exception:
        return False


def load_state():
    try:
        with open(STATE_FILE) as f: return json.load(f)
    except Exception:
        return {}


def save_state(st):
    try:
        with open(STATE_FILE, "w") as f: json.dump(st, f, indent=1)
    except Exception:
        pass


REPORT_FILE = os.path.join(HERE, "apex_healthcheck_report.json")


def write_report_json(rep):
    """Machine-readable report for Mission Control. Never raises."""
    try:
        payload = {
            "marker": MARKER,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "generated_epoch": int(time.time()),
            "overall": rep.worst(),
            "checks": [{"name": n, "status": s, "detail": d} for n, s, d in rep.rows],
            "failures": [n for n, s, _ in rep.rows if s == FAIL],
            "warnings": [n for n, s, _ in rep.rows if s == WARN],
            "text": rep.text(),
        }
        tmp = REPORT_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(payload, f, indent=1)
        os.replace(tmp, REPORT_FILE)      # atomic: MC never reads a half-written file
    except Exception:
        pass


# ---------------------------------------------------------------- refresh chain
def run_refresh_chain(rep):
    """The ONLY mutating path, and only with --run-refresh. Order is enforced
    here in code so the chain can never be run backwards (which happened three
    times by hand on 2026-08-22, silently rebuilding on stale data)."""
    steps = [
        ("data refresh",     "bash apex_data_refresh.sh"),
        ("player state",     "python3 apex_prop_model_v1.py --refresh-state"),
        ("fragility build",  "python3 fragility_state.py --build --no-challengers --year-from 2005"),
        ("fragility validate", "python3 fragility_state.py --validate"),
    ]
    for name, cmd in steps:
        try:
            rc, out = _run(cmd)
        except Exception as e:
            rep.add("chain: " + name, FAIL, "did not run: %s" % e)
            return False
        if rc != 0:
            rep.add("chain: " + name, FAIL, "exit %d — chain stopped, later steps skipped" % rc)
            return False
        if name == "data refresh" and ("FAIL" in out or "SKIP" in out):
            rep.add("chain: " + name, WARN, "completed with FAIL/SKIP lines — old files kept")
            continue
        if name == "fragility validate" and "VALIDATION PASS" not in out:
            rep.add("chain: " + name, FAIL, "validate did not report PASS")
            return False
        rep.add("chain: " + name, OK, "completed")
    return True


# ---------------------------------------------------------------- the ten checks
def run_checks(rep, tournament_active):
    st = load_state()

    @guarded(rep, "1 data refresh")
    def _c1():
        p = os.path.join(HERE, DATA_DIR, "%d.csv" % datetime.now().year)
        if not os.path.exists(p): return FAIL, "%s missing" % os.path.basename(p)
        latest = _latest_tourney_date(p)
        st["data_latest"] = latest
        prev = load_state().get("data_latest")
        d = datetime.strptime(latest, "%Y%m%d") if len(latest) == 8 else None
        age = (datetime.now() - d).days if d else 999
        if age > 14:
            return FAIL, "latest finished event %s — %d days, refresh is stalled" % (latest, age)
        if age > 9:
            return WARN, "latest finished event %s — %d days" % (latest, age)
        return OK, "latest finished event %s (%d days)" % (latest, age)

    @guarded(rep, "2 player state")
    def _c2():
        p = os.path.join(HERE, "apex_prop_state_v1.pkl")
        if not os.path.exists(p): return FAIL, "apex_prop_state_v1.pkl missing"
        import pickle
        with open(p, "rb") as f: s = pickle.load(f)
        sd = str(s.get("latest_date", "")).replace("-", "")
        dd = st.get("data_latest", "")
        if dd and sd and sd != dd:
            return FAIL, "state %s vs data %s — REBUILD RAN ON STALE DATA" % (s.get("latest_date"), dd)
        return OK, "%s, %d players" % (s.get("latest_date"), len(s.get("players", {})))

    @guarded(rep, "3 fragility state")
    def _c3():
        p = os.path.join(HERE, "fragility_state.pkl")
        if not os.path.exists(p): return FAIL, "fragility_state.pkl missing"
        acm = os.path.join(HERE, "apex_combined_model.py")
        if os.path.exists(acm):
            got = _sha_prefix(acm)
            if got != ACM_SHA_PREFIX:
                return FAIL, "apex_combined_model.py sha %s != %s — feature machinery changed" % (got, ACM_SHA_PREFIX)
        return OK, "built, acm sha %s, age %.0fh" % (ACM_SHA_PREFIX, _file_age_hours(p))

    @guarded(rep, "4 fragility gate")
    def _c4():
        ok = os.path.join(HERE, "fragility_features.ok")
        if not os.path.exists(ok):
            return FAIL, "fragility_features.ok MISSING — live features untrusted; run --validate"
        fm = os.path.join(HERE, "fragility_v3_model.json")
        if os.path.exists(fm):
            got = _sha_prefix(fm)
            if got != FRAG_MODEL_SHA_PREFIX:
                return FAIL, "frozen fragility model sha %s != %s — TAMPERED" % (got, FRAG_MODEL_SHA_PREFIX)
        state_p = os.path.join(HERE, "fragility_state.pkl")
        if os.path.exists(state_p) and os.path.getmtime(ok) < os.path.getmtime(state_p):
            return FAIL, "ok-file older than the state — validate did not follow the last build"
        return OK, "validated, frozen model intact"

    @guarded(rep, "5 discord bot")
    def _c5():
        rc, out = _run("pgrep -fl discord_bot.py || true", timeout=30)
        procs = [l for l in out.splitlines() if "discord_bot.py" in l and "pgrep" not in l]
        log = os.path.join(HERE, "data", "logs", "discord_bot_manual.log")
        age = "%.0fh" % _file_age_hours(log) if os.path.exists(log) else "no log"
        if len(procs) == 0:
            return FAIL, "BOT DOWN — 0 processes (log %s). Start it by hand." % age
        if len(procs) > 1:
            return FAIL, "DOUBLE BOT — %d processes. Stop all but one by hand." % len(procs)
        if os.path.exists(log) and _file_age_hours(log) > 24 and tournament_active:
            return WARN, "1 process, but log silent %s during a tournament" % age
        return OK, "1 process, log %s" % age

    @guarded(rep, "6 prop engine")
    def _c6():
        rc, out = _run("python3 apex_prop_engine.py --status", timeout=180)
        if "READY" in out and rc == 0:
            sim = re.search(r"frozen sim\s+(\w+)", out)
            return OK, "READY (sim %s)" % (sim.group(1)[:12] if sim else "?")
        return FAIL, (out.strip().splitlines() or ["no output"])[-1][:120]

    @guarded(rep, "7 forward log")
    def _c7():
        import csv
        p = os.path.join(HERE, "apex_prop_sim_forward_log_v1.csv")
        if not os.path.exists(p):
            return (WARN if tournament_active else OK), "no rows yet"
        with open(p) as f: rows = list(csv.DictReader(f))
        shas = set(r.get("sim_sha", "") for r in rows)
        if len(shas) > 1:
            return FAIL, "%d different sim SHAs in the log — FREEZE INTEGRITY BROKEN" % len(shas)
        seen = set()
        for r in rows:
            k = (r["match_id"], r["player"], r["category"])
            if k in seen: return FAIL, "duplicate rows present — dedupe guard failed"
            seen.add(k)
        settled = sum(1 for r in rows if r.get("actual"))
        if tournament_active and rows and _file_age_hours(p) > 48:
            return WARN, "%d rows (%d settled) — no new rows in %.0fh during a tournament" % (len(rows), settled, _file_age_hours(p))
        return OK, "%d rows, %d settled, 1 sim SHA" % (len(rows), settled)

    @guarded(rep, "8 settlement")
    def _c8():
        import csv
        p = os.path.join(HERE, "apex_prop_sim_forward_log_v1.csv")
        if not os.path.exists(p): return OK, "nothing to settle"
        with open(p) as f: rows = list(csv.DictReader(f))
        stale = []
        cut = (datetime.now() - timedelta(days=21)).date().isoformat()
        for r in rows:
            if not r.get("actual") and r.get("match_date", "9999") < cut:
                stale.append("%s %s" % (r.get("match_date"), r.get("player")))
        if stale:
            return WARN, "%d rows unsettled >21 days (e.g. %s)" % (len(stale), stale[0])
        return OK, "no rows overdue for settlement"

    @guarded(rep, "9 mission control")
    def _c9():
        rc, out = _run("pgrep -fl mission_control || true", timeout=30)
        procs = [l for l in out.splitlines() if "mission_control" in l and "pgrep" not in l]
        alive = False
        try:
            with urllib.request.urlopen("http://127.0.0.1:8788/", timeout=6) as r:
                alive = 200 <= r.status < 500
        except Exception:
            alive = False
        if not procs and not alive: return FAIL, "DOWN — no process, port 8788 not answering"
        if procs and not alive:     return WARN, "%d process(es) but port 8788 not answering" % len(procs)
        if len(procs) > 1:          return WARN, "%d processes — expected 1" % len(procs)
        return OK, "1 process, port 8788 answering"

    @guarded(rep, "10 credentials")
    def _c10():
        issues = []
        bot = os.path.join(HERE, "discord_bot.py")
        if os.path.exists(bot):
            src = open(bot, encoding="utf-8", errors="replace").read()
            if re.search(r'DISCORD_BOT_TOKEN\s*=\s*"[A-Za-z0-9._\-]{30,}"', src):
                issues.append("bot token hardcoded in discord_bot.py")
        core = os.path.join(HERE, CORE)
        if os.path.exists(core):
            src = open(core, encoding="utf-8", errors="replace").read()
            if src.count("https://discord.com/api/webhooks/") >= 3:
                issues.append("webhook URLs hardcoded in openclaw_core.py")
        st2 = load_state()
        if st2.get("credentials_rotated_on"):
            issues.append("last rotation %s" % st2["credentials_rotated_on"])
        if issues:
            return WARN, "; ".join(issues) + " — rotate and move to env/config"
        return OK, "no hardcoded credentials found"

    st["last_run"] = datetime.now().isoformat(timespec="seconds")
    st["last_status"] = rep.worst()
    save_state(st)
    write_report_json(rep)


# ---------------------------------------------------------------- selftest
def cmd_selftest():
    print(MARKER, "-- SELFTEST (no side effects, no network)")
    fails = []
    r = Report()
    r.add("x", OK, "fine"); r.add("y", WARN, "hmm"); r.add("z", FAIL, "broken")
    t = r.text()
    if r.worst() != FAIL: fails.append("worst() should be FAIL")
    if "ACTION REQUIRED" not in t: fails.append("failures must name an action")
    if "🔴" not in t: fails.append("header should show worst status")
    r2 = Report(); r2.add("a", OK, "fine")
    if r2.worst() != OK: fails.append("all-OK should be OK")
    if "ACTION REQUIRED" in r2.text(): fails.append("clean run must not claim action required")
    # a check that raises must be caught and reported, not propagate
    r3 = Report()
    @guarded(r3, "boom")
    def _b(): raise RuntimeError("intentional")
    if r3.rows[0][1] != FAIL or "intentional" not in r3.rows[0][2]:
        fails.append("raising check was not caught into a FAIL row")
    if len(r3.rows) != 1: fails.append("guarded added wrong number of rows")
    # webhook lookup must not raise when nothing is present
    try:
        _webhook("nope")
    except Exception as e:
        fails.append("webhook lookup raised: %s" % e)
    # post must return False, never raise, with no webhook
    if post_discord("definitely-not-a-channel", "x") is not False:
        fails.append("post_discord should return False for an unknown channel")
    # report json round-trip, in a temp dir so nothing real is touched
    import tempfile, shutil
    _hold = globals()["REPORT_FILE"]
    _d = tempfile.mkdtemp()
    globals()["REPORT_FILE"] = os.path.join(_d, "r.json")
    try:
        write_report_json(r)
        with open(globals()["REPORT_FILE"]) as f:
            j = json.load(f)
        if j["overall"] != FAIL: fails.append("report json overall wrong")
        if len(j["checks"]) != 3: fails.append("report json lost checks")
        if j["failures"] != ["z"]: fails.append("report json failures wrong")
        if "text" not in j: fails.append("report json missing text")
    except Exception as e:
        fails.append("report json failed: %s" % e)
    finally:
        globals()["REPORT_FILE"] = _hold
        shutil.rmtree(_d, ignore_errors=True)
    print(t)
    print("\nSELFTEST", "PASS" if not fails else "FAIL: " + "; ".join(fails))
    if fails: sys.exit(1)


PLIST = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>ai.openclaw.healthcheck</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/python3</string>
    <string>{here}/apex_healthcheck.py</string>
    <string>--run-refresh</string>
    <string>--post</string>
  </array>
  <key>WorkingDirectory</key><string>{here}</string>
  <key>StartCalendarInterval</key>
  <dict><key>Hour</key><integer>6</integer><key>Minute</key><integer>30</integer></dict>
  <key>StandardOutPath</key><string>{here}/data/logs/healthcheck.log</string>
  <key>StandardErrorPath</key><string>{here}/data/logs/healthcheck_error.log</string>
  <key>RunAtLoad</key><false/>
</dict>
</plist>
"""


def main():
    ap = argparse.ArgumentParser(description=MARKER)
    ap.add_argument("--post", action="store_true", help="post the heartbeat to Discord")
    ap.add_argument("--run-refresh", action="store_true", help="also run the refresh + rebuild chain first")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--install-plist", action="store_true", help="print a launchd plist; installs nothing")
    ap.add_argument("--tournament", action="store_true", help="treat today as inside a tournament (stricter gaps)")
    a = ap.parse_args()
    if a.selftest: cmd_selftest(); return
    if a.install_plist:
        print(PLIST.format(here=HERE))
        print("# Save as ~/Library/LaunchAgents/ai.openclaw.healthcheck.plist, then:")
        print("#   launchctl bootstrap gui/$UID ~/Library/LaunchAgents/ai.openclaw.healthcheck.plist")
        print("# This script installs nothing and loads nothing.")
        return
    rep = Report()
    try:
        if a.run_refresh:
            run_refresh_chain(rep)
        run_checks(rep, tournament_active=a.tournament)
    except Exception as e:
        rep.add("healthcheck", FAIL, "run aborted: %s: %s" % (type(e).__name__, e))
    text = rep.text()
    print(text)
    if a.post:
        ok_sys = post_discord("system", text)
        if rep.worst() == FAIL:
            post_discord("alerts", text)
        if not ok_sys:
            print("\n** heartbeat could not be posted — check the system webhook")
    sys.exit({OK: 0, WARN: 1, FAIL: 2}[rep.worst()])


if __name__ == "__main__":
    main()
