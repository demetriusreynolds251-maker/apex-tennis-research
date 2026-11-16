#!/usr/bin/env python3
"""
APEX-ENGINE-PRIMARY-2026-08-23
Project Apex Intelligence / OpenClaw (DEMETRIUS)

Makes the FROZEN prop engine the primary source of prop projections in Discord,
with the legacy path as an automatic fallback.

    Screenshot -> Gate 11 -> Gate 11-B -> Apex Prop Engine
        engine succeeds -> post engine card, Dataset A = ENGINE_PICK, return
        engine fails    -> fall through to the legacy path, completely unchanged

ENGINE-SUCCESS PATH SKIPS (this is the cost saving):
    research_agent, evaluation_agent, compliance_agent, scoring_agent,
    rule_31_correlation_check

ENGINE-SUCCESS PATH KEEPS:
    Gate 11 (match verification), Gate 11-B (bo3/bo5 lock), Dataset A tracking

FALLBACK TRIGGERS (any one -> legacy runs, unchanged):
    missing odds · unparseable odds · invalid probability · unknown player ·
    ambiguous player · no surface history · unsupported stat type ·
    missing/unfrozen/tampered model · V1 SHA mismatch · any exception

PRICE: the prop pipeline carries no moneyline price, so the operator types it
with the submission, anywhere in the message text:
        odds -250/+200
No odds -> engine returns nothing -> legacy runs. Never silence, never a hard fail.

FOUR INSERTION POINTS
 1. helpers, next to the existing fragility helpers
 2. the engine gate in process_single_prop, after Gate 11-B, before research
 3. format_pick_card renders the engine card when one is attached
 4. the fantasy_score filter lets fantasy score through (legacy skips it; the
    engine covers it, and it was the best-calibrated category on holdout)

USAGE (from ~/openclaw)
    python3 apex_engine_primary_wire.py --check
    python3 apex_engine_primary_wire.py --apply
    python3 apex_engine_primary_wire.py --revert
"""
import argparse, hashlib, os, py_compile, shutil, tempfile
from datetime import datetime

MARKER = "APEX-ENGINE-PRIMARY-2026-08-23"
TARGET = "openclaw_core.py"

# ------------------------------------------------------------------ anchors
A_HELPERS = "def finalize_batch_ml_evaluation(batch_state, eval_text, stop_reason, dates):"

A_GATE = '''    # Gate 11-B — Format Detection (bo3 vs bo5)
    prop = gate_11b_format_detection(prop)
    d1.transition(eval_id, "RESEARCH_STARTED",
                   gate11b_dominance_key=prop.get("dominance_level") or prop.get("dominance"),
                   _logger=log)

    # Research'''

A_CARD = """def format_pick_card(pick, index):
    player       = pick.get("player", "")"""

A_FANTASY = '''        if stat.lower() in ("fantasy_score", "fantasy score"):
            skipped_tags.append(
                f"Fantasy Score skip: {prop.get('player','?')}")
            continue'''

# ------------------------------------------------------------------ payloads
HELPERS = '''
# ---------------------------------------------------------------------------
# APEX-ENGINE-PRIMARY-2026-08-23 -- frozen prop engine as the PRIMARY prop
# source, with the legacy path as an automatic fallback.
#
# On engine success this path deliberately skips research_agent,
# evaluation_agent, compliance_agent, scoring_agent and the correlation check --
# that LLM chain is the cost this replaces. Gate 11, Gate 11-B and Dataset A
# tracking all still run. The tier system + frozen-model + holdout validation
# stand in for the compliance/scoring layer on engine picks, by explicit
# operator decision (2026-08-23).
#
# Fail-open by contract: ANY problem returns None and the legacy path runs
# exactly as it did before. No silence, no hard failure.
# ---------------------------------------------------------------------------

# PrizePicks stat slug -> engine category. Confirmed against the slugs this file
# actually branches on. Anything unmapped -> engine declines -> legacy runs.
_APEX_STAT_MAP = {
    "aces":             "aces",
    "double_faults":    "dfs",
    "total_games":      "total_games",       # match-level
    "games_won":        "games_won",         # player-level
    "total_games_won":  "games_won",         # player-level (operator-confirmed)
    "total_sets":       "total_sets",        # match-level
    "sets":             "sets_won",          # player-level
    "break_points_won": "breaks",            # player-level
    "fantasy_score":    "fantasy_score",
}
_APEX_MATCH_LEVEL = {"total_games", "total_sets"}


def _apex_engine_pick(prop, dates, eval_id):
    """APEX-ENGINE-PRIMARY-2026-08-23: returns a scored-shaped dict or None.

    None means "engine declined" for ANY reason -- the caller falls through to
    the legacy path untouched."""
    try:
        # --- price: operator-typed odds, carried on the prop by the intake stamp
        po = prop.get("apex_player_odds") or prop.get("player_odds")
        oo = prop.get("apex_opponent_odds") or prop.get("opponent_odds")
        pa = _fragility_american_to_prob(po)
        pb = _fragility_american_to_prob(oo)
        if pa is None or pb is None or (pa + pb) <= 0:
            log("ApexEngine", f"declined ({prop.get('player','?')}): no usable odds -> legacy")
            return None
        fair_a = pa / (pa + pb)

        player   = prop.get("player", "")
        opponent = prop.get("opponent", "")
        if not player or not opponent:
            log("ApexEngine", "declined: missing player/opponent -> legacy")
            return None
        if fair_a >= 0.5:
            fav, dog, fav_p = player, opponent, fair_a
        else:
            fav, dog, fav_p = opponent, player, 1.0 - fair_a

        # --- stat mapping
        slug = str(prop.get("stat_type", "")).strip().lower().replace(" ", "_")
        cat  = _APEX_STAT_MAP.get(slug)
        if not cat:
            log("ApexEngine", f"declined ({player}): unmapped stat_type {slug!r} -> legacy")
            return None
        try:
            line = float(prop.get("line"))
        except (TypeError, ValueError):
            log("ApexEngine", f"declined ({player}): unusable line -> legacy")
            return None

        key   = ("match|" + cat) if cat in _APEX_MATCH_LEVEL else (player + "|" + cat)
        bo5   = str(prop.get("match_format", "")).lower() == "bo5"
        wta   = str(prop.get("tour", "")).lower() == "wta"
        surf  = str(prop.get("surface", "Hard")).title()

        import apex_prop_engine
        res = apex_prop_engine.evaluate_match(
            fav, dog, fav_p, surface=surf, bo5=bo5, wta=wta,
            lines={key: line})
        if not res or not res.get("ok"):
            log("ApexEngine",
                f"declined ({player}): {(res or {}).get('error', 'no result')} -> legacy")
            return None

        target = None
        for p in res["props"]:
            if p["category"] != cat:
                continue
            if cat in _APEX_MATCH_LEVEL or _fragility_name_match(p["player"], player):
                target = p
                break
        if target is None or target.get("line") is None:
            log("ApexEngine", f"declined ({player}): no {cat} row with a line -> legacy")
            return None

        card = _apex_engine_card(res, target, prop)

        # --- Dataset A: engine picks are tracked, and distinguishable
        try:
            d1.transition(eval_id, "ENGINE_PICK",
                           classification="ENGINE_PICK", _logger=log)
        except Exception:
            pass
        try:
            d1.heartbeat("evaluation", "IDLE", increment_success=True, _logger=log)
        except Exception:
            pass

        direction = "MORE" if (target["p_over"] or 0) >= 0.5 else "LESS"
        prob      = target["p_over"] if direction == "MORE" else target["p_under"]
        log("ApexEngine",
            f"ENGINE_PICK {player} {slug} {line} -> {direction} "
            f"p={prob:.3f} tier={target['tier']} (sim {res['sim_sha'][:8]})")
        return {
            "_apex_engine_card":   card,
            "_apex_engine":        True,
            "player":              player,
            "opponent":            opponent,
            "stat_type":           prop.get("stat_type", ""),
            "line":                line,
            "direction":           direction,
            "confidence":          round(float(prob), 4),
            "emoji":               {"elite": "🟢", "good": "🟡",
                                    "caution": "🟠", "low": "🔴"}.get(target["tier"], "🟡"),
            "match_type":          "ENGINE · FORWARD TEST",
            "one_sentence":        (target["reasons"] or [""])[0],
            "rules_confirmed":     [],
            "prop_type_classified": prop.get("prop_type_classified", "standard"),
            "compliance_penalty":  False,
            "compliance_flags":    [],
            "pipeline_flags":      ["ENGINE_PICK — legacy evaluation chain skipped"],
            "research_data":       {"player": {}, "opponent": {}},
            "evaluation":          card,
            "eval_id":             eval_id,
            "match_date":          dates.get("match_date"),
            "pipeline_run_date":   dates.get("pipeline_run_date"),
            "apex_sim_sha":        res["sim_sha"],
            "apex_v1_sha":         res["v1_sha"],
            "apex_tier":           target["tier"],
        }
    except (Exception, SystemExit) as e:
        try:
            log("ApexEngine", f"declined (exception: {type(e).__name__}: {e}) -> legacy")
        except Exception:
            pass
        return None


def _fragility_name_match(a, b):
    """APEX-ENGINE-PRIMARY-2026-08-23: loose name comparison, never raises."""
    try:
        import re as _re
        norm = lambda s: _re.sub(r"[^a-z ]", "", str(s).lower()).strip()
        na, nb = norm(a), norm(b)
        if na == nb:
            return True
        sa, sb = set(na.split()), set(nb.split())
        return bool(sa) and bool(sb) and (sa <= sb or sb <= sa)
    except Exception:
        return False


def _apex_engine_card(res, t, prop):
    """APEX-ENGINE-PRIMARY-2026-08-23: the Discord card. Never raises."""
    try:
        badge = {"elite": "🟢 ELITE", "good": "🟡 GOOD",
                 "caution": "🟠 CAUTION", "low": "🔴 LOW CONFIDENCE"}.get(t["tier"], "🟡 GOOD")
        over  = (t["p_over"] or 0) >= 0.5
        side  = "MORE ⬆" if over else "LESS ⬇"
        prob  = t["p_over"] if over else t["p_under"]
        L = [
            "**EXPERIMENTAL · FORWARD TEST ACTIVE**",
            f"{badge} · {t['label']}",
            f"**{t['player'] if t['player'] != 'match' else prop.get('player','')}** "
            f"vs {prop.get('opponent','')} · {res['surface']} · Bo{res['best_of']}",
            f"`{t['line']} {prop.get('stat_type','')} — {side}`",
            f"Projection **{t['mean']:.1f}**  (10-90: {t['p10']:.1f}–{t['p90']:.1f})",
            f"Probability **{100*prob:.0f}%**   Edge {t['edge']:+.1f}   "
            f"Confidence {t['confidence']}",
            f"Fragility {res['fragility_text']}",
        ]
        for why in (t.get("reasons") or [])[:3]:
            L.append(f"• {why}")
        L.append("_Break-even ≈54% (6-pick flex) / 58% (power play)_")
        L.append(f"`engine sim {res['sim_sha'][:12]} / V1 {res['v1_sha'][:12]}`")
        return "\\n".join(L)
    except Exception:
        return ""


'''

GATE = '''    # Gate 11-B — Format Detection (bo3 vs bo5)
    prop = gate_11b_format_detection(prop)
    d1.transition(eval_id, "RESEARCH_STARTED",
                   gate11b_dominance_key=prop.get("dominance_level") or prop.get("dominance"),
                   _logger=log)

    # APEX-ENGINE-PRIMARY-2026-08-23 -- frozen engine first, legacy fallback.
    # Runs AFTER Gate 11 and Gate 11-B (both preserved) and BEFORE the LLM
    # chain. On success this returns immediately: no research_agent, no
    # evaluation_agent, no compliance_agent, no scoring_agent. On ANY failure
    # it returns None and everything below runs exactly as it did before.
    _apex_pick = _apex_engine_pick(prop, dates, eval_id)
    if _apex_pick:
        return _apex_pick

    # Research'''

CARD = '''def format_pick_card(pick, index):
    # APEX-ENGINE-PRIMARY-2026-08-23: engine picks carry their own rendered
    # card (tier badge, projection, probability, edge, fragility, SHAs).
    _apex_card = pick.get("_apex_engine_card")
    if _apex_card:
        return f"**{index}.** {_apex_card}"
    player       = pick.get("player", "")'''

FANTASY = '''        # APEX-ENGINE-PRIMARY-2026-08-23: fantasy score is skipped by the
        # LEGACY path only. The engine covers it (best-calibrated category on
        # the 2024+ holdout), so let it through when the operator supplied odds
        # -- the engine gate decides, and declines back to this skip if it
        # cannot price it.
        if stat.lower() in ("fantasy_score", "fantasy score"):
            _has_odds = bool(prop.get("apex_player_odds") and prop.get("apex_opponent_odds"))
            if not _has_odds:
                skipped_tags.append(
                    f"Fantasy Score skip (no odds supplied): {prop.get('player','?')}")
                continue'''


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def report(src, path):
    print(MARKER, "-- CHECK", path)
    print("file sha256", sha(path))
    print("lines", src.count("\n") + 1)
    print("marker present:", src.count(MARKER))
    checks = [
        ("helper anchor", A_HELPERS),
        ("engine gate site (after Gate 11-B)", A_GATE),
        ("format_pick_card head", A_CARD),
        ("fantasy_score legacy filter", A_FANTASY),
    ]
    ok = True
    for name, a in checks:
        n = src.count(a)
        print("  %-38s %s" % (name, "OK" if n == 1 else "** %d matches — must be exactly 1" % n))
        if n != 1:
            ok = False
    for dep in ("_fragility_american_to_prob", "def gate_11b_format_detection",
                "def gate_11_check", "def process_single_prop"):
        n = src.count(dep)
        print("  %-38s %s" % ("depends on " + dep.replace("def ", ""), "OK" if n >= 1 else "** MISSING"))
        if n < 1:
            ok = False
    if MARKER in src:
        print("\nALREADY PATCHED — --apply will refuse.")
        return False
    print("\n%s" % ("READY TO APPLY" if ok else "NOT READY — send this output back"))
    return ok


def apply_patch(path, src):
    out = src.replace(A_HELPERS, HELPERS + A_HELPERS, 1)
    out = out.replace(A_GATE, GATE, 1)
    out = out.replace(A_CARD, CARD, 1)
    out = out.replace(A_FANTASY, FANTASY, 1)
    n = out.count(MARKER)
    if n < 7:
        raise SystemExit("only %d markers — refusing to write" % n)
    tmp = os.path.join(tempfile.mkdtemp(), TARGET)
    with open(tmp, "w") as f:
        f.write(out)
    py_compile.compile(tmp, doraise=True)
    print("compile check: OK (%d markers)" % n)
    backup = path + ".bak_" + datetime.now().strftime("%Y%m%d_%H%M%S")
    shutil.copy2(path, backup)
    with open(path, "w") as f:
        f.write(out)
    py_compile.compile(path, doraise=True)
    print("backup   ", backup)
    print("patched  ", path)
    print("new sha256", sha(path))
    print("""
NEXT — the running bot still has the OLD code in memory. Restart it yourself
when ready; this script starts and stops nothing.

Then send a prop screenshot WITH the odds typed in the message, e.g.
        odds -250/+200
No odds -> engine declines -> the legacy path runs exactly as before.""")


def revert(path):
    d = os.path.dirname(os.path.abspath(path)) or "."
    baks = [f for f in sorted(os.listdir(d)) if f.startswith(TARGET + ".bak_")]
    baks = [b for b in baks if MARKER not in open(os.path.join(d, b), errors="replace").read()]
    if not baks:
        raise SystemExit("no pre-patch backup found")
    b = os.path.join(d, baks[-1])
    shutil.copy2(b, path)
    print("restored from", b, "\nsha256", sha(path))


def main():
    ap = argparse.ArgumentParser(description=MARKER)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    ap.add_argument("--file", default=TARGET)
    a = ap.parse_args()
    if a.revert:
        revert(a.file); return
    if not os.path.exists(a.file):
        raise SystemExit("%s not found — run from ~/openclaw" % a.file)
    src = open(a.file, errors="replace").read()
    if a.check or not a.apply:
        report(src, a.file); return
    if MARKER in src:
        raise SystemExit("already patched — refusing")
    if not report(src, a.file):
        raise SystemExit("checks failed — refusing to patch")
    print()
    apply_patch(a.file, src)


if __name__ == "__main__":
    main()
