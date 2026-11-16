#!/usr/bin/env python3
"""
APEX-EDGE-ZONE-2026-08-27 -- attention block + tracker wiring
=============================================================

Edits (exact-match, asserted once each, backups first, compile check with
automatic restore):

  openclaw_core.py
    A. _apex_engine_card: prepend apex_edge_tracker.discord_header() -- the
       🔥 POTENTIAL EDGE ZONE block -- above every engine card. Never raises.
    B. _apex_engine_pick: decline goes_5_sets on a best-of-3 match (the probe
       showed it returning 100% LESS "Confidence Medium" on Bo3 -- true but useless).

  apex_prop_engine.py
    C. render_mission_control: insert apex_edge_tracker.mission_control_panel()
       (POTENTIAL EDGE TRACKER) above the BY TIER block, and on the empty-log path.
    D. render_shadow_block: the old "🔥 BEST CATEGORIES" line becomes
       "⭐ BEST TIERS (historical)" so 🔥 means exactly one thing.

  apex_prop_sim_v1.py
    NOT touched. The simulator is a frozen artifact and its loader refuses a
    tampered file; the group-split report lives in apex_edge_tracker.py --report.

Run:  cd ~/openclaw && python3 apex_edge_zone_patch.py [--dry-run]
"""
import hashlib, os, shutil, sys
from datetime import datetime

MARKER = "APEX-EDGE-ZONE-2026-08-27"

EDITS = {"openclaw_core.py": [], "apex_prop_engine.py": []}

# A --------------------------------------------------------------- card header
EDITS["openclaw_core.py"].append(("A card header",
'''        L = [
            "**EXPERIMENTAL · FORWARD TEST ACTIVE**",
            f"{badge} · {t['label']}",
''',
'''        L = []
        # APEX-EDGE-ZONE-2026-08-27: attention block above every card. The
        # tracker is a hypothesis list plus a live record; it never raises.
        try:
            import apex_edge_tracker as _aet
            _hdr = _aet.discord_header(t.get("category"))
            if _hdr:
                L.append(_hdr)
        except Exception:
            pass
        L += [
            "**EXPERIMENTAL · FORWARD TEST ACTIVE**",
            f"{badge} · {t['label']}",
'''))

# B --------------------------------------------------------------- goes_5 on Bo3
EDITS["openclaw_core.py"].append(("B goes_5_sets on Bo3",
'''        bo5   = str(prop.get("match_format", "")).lower() == "bo5"
        wta   = str(prop.get("tour", "")).lower() == "wta"
''',
'''        bo5   = str(prop.get("match_format", "")).lower() == "bo5"
        wta   = str(prop.get("tour", "")).lower() == "wta"
        # APEX-EDGE-ZONE-2026-08-27: a five-setter cannot happen in a best-of-3.
        if cat == "goes_5_sets" and not bo5:
            _apex_decline(prop, f"declined ({player}): goes_5_sets on a best-of-3 match -> legacy")
            return None
'''))

# C --------------------------------------------------------------- MC panel
EDITS["apex_prop_engine.py"].append(("C1 MC panel (empty log path)",
'''        if not os.path.exists(path):
            head.append("FORWARD LOG   empty — no projections logged yet")
            head.append("player state  %s" % z["state"]["latest_date"])
            return "\\n".join(head)
''',
'''        if not os.path.exists(path):
            head.append("FORWARD LOG   empty — no projections logged yet")
            head.append("player state  %s" % z["state"]["latest_date"])
            head.append("")
            head.append(_edge_tracker_panel())          # APEX-EDGE-ZONE-2026-08-27
            return "\\n".join(head)
'''))
EDITS["apex_prop_engine.py"].append(("C2 MC panel",
'''        head.append("FORWARD LOG   rows %d   settled %d   open %d" % (len(rows), len(settled), len(rows) - len(settled)))
        head.append("")
        head.append("BY TIER (settled, with a line)")
''',
'''        head.append("FORWARD LOG   rows %d   settled %d   open %d" % (len(rows), len(settled), len(rows) - len(settled)))
        head.append("")
        head.append(_edge_tracker_panel())              # APEX-EDGE-ZONE-2026-08-27
        head.append("")
        head.append("BY TIER (settled, with a line)   — historical reliability of the CATEGORY, not this pick")
'''))
EDITS["apex_prop_engine.py"].append(("C3 helper",
'''def render_mission_control(limit=12):
''',
'''def _edge_tracker_panel():
    """APEX-EDGE-ZONE-2026-08-27: POTENTIAL EDGE TRACKER text. Never raises."""
    try:
        import apex_edge_tracker as _aet
        return _aet.mission_control_panel()
    except Exception as e:
        return "POTENTIAL EDGE TRACKER — unavailable (%s)" % e

def render_mission_control(limit=12):
'''))

# D --------------------------------------------------------------- rename old 🔥
EDITS["apex_prop_engine.py"].append(("D rename BEST CATEGORIES",
'''L.append("🔥 BEST CATEGORIES: "''',
'''L.append("⭐ BEST TIERS (historical): "'''))


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def main():
    dry = "--dry-run" in sys.argv
    if not os.path.exists("apex_edge_tracker.py"):
        sys.exit("apex_edge_tracker.py is not in this folder -- copy it in first")
    srcs = {}
    for f, edits in EDITS.items():
        if not os.path.exists(f):
            sys.exit(f"{f} not found -- run from ~/openclaw")
        srcs[f] = open(f, encoding="utf-8").read()
        if MARKER in srcs[f]:
            sys.exit(f"{MARKER} already present in {f} -- refusing to re-apply")
        print(f"{MARKER}  {f}  sha256 {sha(f)}")
        bad = []
        for name, old, new in edits:
            n = srcs[f].count(old)
            print(f"  [{'ok' if n == 1 else 'FAIL'}] {name}: {n} match(es)")
            if n != 1: bad.append(name)
        if bad:
            sys.exit(f"ABORT -- {bad} did not match exactly once in {f}. Nothing written.")
    if dry:
        print("dry run: all asserts pass, nothing written"); return

    import py_compile
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    done = []
    for f, edits in EDITS.items():
        out = srcs[f]
        for name, old, new in edits:
            out = out.replace(old, new, 1)
        bak = f"{f}.bak_{stamp}_preedgezone"
        shutil.copy2(f, bak)
        with open(f, "w", encoding="utf-8") as fh:
            fh.write(out)
        try:
            py_compile.compile(f, doraise=True)
        except Exception as e:
            for g, b in done + [(f, bak)]:
                shutil.copy2(b, g)
            sys.exit(f"ABORT -- {f} failed to compile after edit ({e}); all originals restored")
        done.append((f, bak))
        print(f"written {f}  sha256 {sha(f)}  (backup {bak}, py_compile OK)")
    print("next: rm -rf __pycache__ ; python3 apex_edge_tracker.py --selftest ; "
          "python3 -c \"import apex_prop_engine as e; print(e.status()); print(e.render_mission_control())\" ; "
          "python3 apex_wiring_probe.py ; then restart the bot")


if __name__ == "__main__":
    main()
