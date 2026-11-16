#!/usr/bin/env python3
"""
APEX-SLIP-TIME-2026-08-24
The PrizePicks slip shows the match date and time ("Tue • 9:00am") on every card.
The intake never read it. This patch reads it and uses it.

WHAT CHANGES (four insertions in openclaw_core.py, nothing removed)
--------------------------------------------------------------------
A. SCREENSHOT_PARSE_PROMPT: the props JSON gains "start" -- the date/time text
   exactly as shown under the opponent's name. Copy, never convert.
B. A parser, _apex_parse_slip_start(): "Tue • 9:00am" / "Today • 12:20pm" /
   "Tomorrow • 8:30pm" -> a real timestamp. PrizePicks shows the operator's LOCAL
   time, which is Central (verified 08-24: slip "Tue 9:00am" == fixture 14:00Z).
   Weekday names resolve to the next such day on or after today (same weekday =
   today). Returns (utc_iso, ct_iso) or (None, None). Never raises.
C. The props loop: every prop from a slip carries slip_start (raw text),
   slip_start_utc, slip_start_ct, and match_date becomes the slip's date instead
   of today's.
D. _apex_engine_pick(): right after the names are read, a slip whose time is in
   the past is DECLINED with "match already started per slip (…)" -- before any
   price call is spent. The slip time is also logged next to the pick so it can
   be compared with the fixture time.
E. _apex_forward_log_row(): match_date prefers the slip's Central date, then the
   fixture date, then today.

Text-typed props (no slip) are unchanged: no slip fields, old behaviour.

USAGE
    python3 apex_slip_time_patch.py --check
    python3 apex_slip_time_patch.py --apply
    python3 apex_slip_time_patch.py --apply --force
"""
import argparse
import hashlib
import os
import py_compile
import shutil
import sys
import tempfile
from datetime import datetime

TARGET = "openclaw_core.py"
MARKER = "APEX-SLIP-TIME-2026-08-24"
EXPECTED_SHA = "459d0b015745be8104061265a81359e30a524af3ac6db481223ea2988f85fe5a"

# ------------------------------------------------------------------ A. prompt
ANCHOR_PROMPT = '''[{"player":"exact name as shown","opponent":"exact name as shown or null",
  "stat_type":"exact stat label as shown","line":number,
  "prop_type":"standard/goblin/demon","direction_locked":"MORE/LESS or null"}]
'''
INSERT_PROMPT = '''[{"player":"exact name as shown","opponent":"exact name as shown or null",
  "stat_type":"exact stat label as shown","line":number,
  "prop_type":"standard/goblin/demon","direction_locked":"MORE/LESS or null",
  "start":"the date/time text shown under the opponent name, copied exactly, e.g. 'Tue • 9:00am' or 'Today • 12:20pm', or null"}]
'''
ANCHOR_RULES = '''- If you cannot read a value clearly, omit it rather than guess.
- Return ONLY the JSON. No explanation, no markdown fences.
'''
INSERT_RULES = '''- If you cannot read a value clearly, omit it rather than guess.
- start: copy the date/time line under the opponent name character for character (day word, then the time). Do not convert or reformat it. Use null if it is not visible.
- Return ONLY the JSON. No explanation, no markdown fences.
'''

# ------------------------------------------------------------------ B. parser (before the intake function)
ANCHOR_PARSER = "def resolve_tournament_context(player_name: str, opponent_name: str) -> dict:"
INSERT_PARSER = '''# ── APEX-SLIP-TIME-2026-08-24: the slip's own date/time, read and used
def _apex_parse_slip_start(text, now_ct=None):
    """'Tue • 9:00am' / 'Today • 12:20pm' / 'Tomorrow • 8:30pm' -> (utc_iso, ct_iso).
    PrizePicks shows the operator's local time (Central). Weekday names resolve to
    the next such day on or after today. Returns (None, None) on anything else.
    Never raises."""
    try:
        import re as _re
        from datetime import datetime as _dt, timedelta as _td, timezone as _tz
        if not text:
            return None, None
        s = str(text).strip().lower()
        m_time = _re.search(r"(\\d{1,2})(?::(\\d{2}))?\\s*(am|pm)", s)
        if not m_time:
            return None, None
        hh = int(m_time.group(1)); mm = int(m_time.group(2) or 0); ap = m_time.group(3)
        if not (1 <= hh <= 12 and 0 <= mm <= 59):
            return None, None
        if ap == "pm" and hh != 12:
            hh += 12
        if ap == "am" and hh == 12:
            hh = 0
        now = now_ct or _dt.now(CT)
        base = now.date()
        m_day = _re.search(r"\\b(today|tomorrow|mon|tue|wed|thu|fri|sat|sun)[a-z]*\\b", s)
        day = m_day.group(1) if m_day else "today"
        if day == "today":
            d = base
        elif day == "tomorrow":
            d = base + _td(days=1)
        else:
            want = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"].index(day)
            d = base + _td(days=(want - base.weekday()) % 7)      # same weekday -> today
        local = CT.localize(_dt(d.year, d.month, d.day, hh, mm)) if hasattr(CT, "localize") \\
            else _dt(d.year, d.month, d.day, hh, mm, tzinfo=CT)
        return local.astimezone(_tz.utc).isoformat(), local.isoformat()
    except Exception:
        return None, None


'''

# ------------------------------------------------------------------ C. props loop
ANCHOR_LOOP = '''        for p in parsed:
            props.append({
                **p,
                "stat_type":                 normalize_stat_type(p.get("stat_type", "")),
                "tournament":                tournament,
                "surface":                   surface,
                "tour":                      tour,
                "tournament_stage":          3 if is_gs else 1,
                "is_grand_slam":             is_gs,
                "both_directions_available": p.get("prop_type") == "standard",
                "match_date":                dates["match_date"],
                "same_day_3set_count":       0,
            })
'''
INSERT_LOOP = '''        for p in parsed:
            # APEX-SLIP-TIME-2026-08-24: the slip's own date/time, Central
            _s_utc, _s_ct = _apex_parse_slip_start(p.get("start"))
            if p.get("start") and not _s_ct:
                log("Manual", f"slip start text not understood: {p.get('start')!r} (ignored)")
            props.append({
                **p,
                "stat_type":                 normalize_stat_type(p.get("stat_type", "")),
                "tournament":                tournament,
                "surface":                   surface,
                "tour":                      tour,
                "tournament_stage":          3 if is_gs else 1,
                "is_grand_slam":             is_gs,
                "both_directions_available": p.get("prop_type") == "standard",
                "match_date":                (_s_ct[:10] if _s_ct else dates["match_date"]),
                "slip_start":                p.get("start"),
                "slip_start_utc":            _s_utc,
                "slip_start_ct":             _s_ct,
                "same_day_3set_count":       0,
            })
'''

# ------------------------------------------------------------------ D. engine pick
ANCHOR_PICK = '''            _apex_decline(prop, "declined: missing player/opponent -> legacy")
            return None
'''
INSERT_PICK = '''            _apex_decline(prop, "declined: missing player/opponent -> legacy")
            return None

        # APEX-SLIP-TIME-2026-08-24: the slip says when the match is. A match
        # already under way per the slip is declined here, before any price call.
        _slip_utc = prop.get("slip_start_utc")
        if _slip_utc:
            try:
                from datetime import datetime as _sdt, timezone as _stz
                _st = _sdt.fromisoformat(str(_slip_utc))
                _now = _sdt.now(_stz.utc)
                log("ApexEngine", f"slip start {prop.get('slip_start')} -> {prop.get('slip_start_ct')} "
                                  f"({(_st - _now).total_seconds() / 60:+.0f} min from now)")
                if (_st - _now).total_seconds() < -120:
                    _apex_decline(prop, f"declined ({player}): match already started per slip "
                                        f"({prop.get('slip_start')} = {prop.get('slip_start_ct')}) -> legacy")
                    return None
            except Exception:
                pass
'''

# ------------------------------------------------------------------ E. forward log date
ANCHOR_FWD = '''        if _fc and _fc.get("start_time"):
            match_date = str(_fc["start_time"])[:10]
            tourn = tourn or str(_fc.get("tournament") or "")
'''
INSERT_FWD = '''        if _fc and _fc.get("start_time") and not prop.get("slip_start_ct"):
            match_date = str(_fc["start_time"])[:10]
        if _fc:
            tourn = tourn or str(_fc.get("tournament") or "")
    except Exception:
        pass
    # APEX-SLIP-TIME-2026-08-24: the slip's Central date is the match day
    try:
        if prop.get("slip_start_ct"):
            match_date = str(prop["slip_start_ct"])[:10]
'''


def sha(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def check(src, force):
    ok = True
    print(f"{MARKER}  --check on {TARGET}")
    cur = sha(TARGET)
    print(f"  current SHA  {cur}")
    if cur != EXPECTED_SHA:
        print(f"  expected     {EXPECTED_SHA}")
        print("  !! SHA differs from the core this patch was written against"
              + (" -- continuing because --force" if force else " -- refusing (use --force if you know why)"))
        ok = ok and force
    if MARKER in src:
        print(f"  !! marker {MARKER} already present -- already applied"); ok = False
    for name, anchor in (("prompt JSON shape", ANCHOR_PROMPT), ("prompt rules", ANCHOR_RULES),
                         ("parser insert point (resolver def)", ANCHOR_PARSER), ("props loop", ANCHOR_LOOP),
                         ("engine pick names block", ANCHOR_PICK), ("forward-log fixture date", ANCHOR_FWD)):
        n = src.count(anchor)
        print(f"  anchor {name}: {n} match(es)" + ("" if n == 1 else "  !! need exactly 1"))
        ok = ok and n == 1
    for need in ("CT = ", "def _apex_decline(", "def _apex_forward_log_row(", "APEX-ENGINE-ONLY-2026-08-24"):
        present = need in src
        print(f"  core has {need}: {present}")
        ok = ok and present
    print("  RESULT:", "READY" if ok else "NOT READY -- nothing will be written")
    return ok


def apply(src):
    out = src.replace(ANCHOR_PROMPT, INSERT_PROMPT, 1)
    out = out.replace(ANCHOR_RULES, INSERT_RULES, 1)
    out = out.replace(ANCHOR_PARSER, INSERT_PARSER + ANCHOR_PARSER, 1)
    out = out.replace(ANCHOR_LOOP, INSERT_LOOP, 1)
    out = out.replace(ANCHOR_PICK, INSERT_PICK, 1)
    out = out.replace(ANCHOR_FWD, INSERT_FWD, 1)
    assert out.count(MARKER) == 4, "insertion count wrong"
    tmpdir = tempfile.mkdtemp()
    tmp = os.path.join(tmpdir, TARGET)
    with open(tmp, "w") as fh:
        fh.write(out)
    py_compile.compile(tmp, doraise=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = f"{TARGET}.bak_{stamp}"
    shutil.copy2(TARGET, bak)
    shutil.move(tmp, TARGET)
    print(f"  backup       {bak}  ({sha(bak)[:12]}…)")
    print(f"  new SHA      {sha(TARGET)}")
    print(f"  marker count {open(TARGET).read().count(MARKER)}")
    print("  APPLIED. Restart the bot:  launchctl kickstart -k gui/$(id -u)/com.apex.discordbot")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    if not (a.check or a.apply):
        ap.print_help(); return 2
    if not os.path.exists(TARGET):
        print(f"{TARGET} not found -- run from ~/openclaw"); return 1
    src = open(TARGET, encoding="utf-8").read()
    ready = check(src, a.force)
    if a.apply:
        if not ready:
            print("  --apply refused: fix the items above first"); return 1
        apply(src)
    return 0


if __name__ == "__main__":
    sys.exit(main())
