#!/usr/bin/env python3
"""
APEX-WIRING-2026-08-27 -- fantasy score / sets won / tiebreak / binary-category wiring
=====================================================================================

Applies eleven exact-match edits to openclaw_core.py. Every edit asserts that its
target text occurs exactly once BEFORE anything is written; if any assert fails the
file is left untouched. A timestamped backup is written first.

  1. remove the "Fantasy score = always skip" filter               (~line 1669)
  2. remove the fantasy raise in the batch screenshot path          (~line 4381)
  3. remove the fantasy raise in the batch text path                (~line 4414)
  4. remove the fantasy odds-gate in evaluate_manual_prop           (~line 9585)
  5. _APEX_STAT_MAP: add sets_won, tiebreaks, first_set_games, any_tiebreak,
     first_set_winner, goes_3_sets, goes_5_sets (+ label aliases)
  6. _APEX_MATCH_LEVEL: register the new match-level categories
  7. _APEX_BINARY: new set; binary categories always use line 0.5
  8. _apex_engine_pick: binary line handling
  9. _apex_engine_pick: first-set-winner dog flip (card + pick direction only;
     the forward-log row stays favorite-relative so settlement matches it)
 10. STAT_ABBREV (typed slip legs): sets -> sets_won, ts -> total_sets
 11. comment updates so the file no longer describes rules it no longer has

Run:  cd ~/openclaw && python3 apex_wiring_patch.py
      (add --dry-run to check the asserts without writing)
"""
import hashlib, os, shutil, sys
from datetime import datetime

MARKER = "APEX-WIRING-2026-08-27"
TARGET = "openclaw_core.py"

EDITS = []
def edit(name, old, new):
    EDITS.append((name, old, new))

# 1 ------------------------------------------------------------------ filter skip
edit("1 filter skip",
'''        # Fantasy score = always skip
        if prop.get("stat_type", "") == "fantasy_score":
            skipped += 1
            log("Filter", f"Fantasy score excluded: {prop.get('player')}")
            continue
''',
'''        # APEX-WIRING-2026-08-27: fantasy score is no longer skipped here.
        # The engine prices it (simulator category fantasy_score); if the engine
        # cannot, it declines like any other prop.
''')

# 2 ------------------------------------------------------------------ batch screenshot raise
edit("2 batch screenshot raise",
'''        # evaluable (non-demon, non-fantasy) prop from the card.
        for p in parsed:
            stat = normalize_stat_type(p.get("stat_type", ""))
            pt   = p.get("prop_type", "standard")
            if p.get("is_demon") or pt == "demon":
                raise ValueError(
                    f"DEMON prop — {p.get('player')} {stat} cannot be batched "
                    f"(DEMON skip rule applies). Re-submit without this prop.")
            if stat.lower() in ("fantasy_score", "fantasy score"):
                raise ValueError(
                    f"Fantasy Score — {p.get('player')} skipped by rule")
''',
'''        # evaluable (non-demon) prop from the card.
        # APEX-WIRING-2026-08-27: fantasy score is evaluable (engine category).
        for p in parsed:
            stat = normalize_stat_type(p.get("stat_type", ""))
            pt   = p.get("prop_type", "standard")
            if p.get("is_demon") or pt == "demon":
                raise ValueError(
                    f"DEMON prop — {p.get('player')} {stat} cannot be batched "
                    f"(DEMON skip rule applies). Re-submit without this prop.")
''')

# 3 ------------------------------------------------------------------ batch text raise
edit("3 batch text raise",
'''        stat = normalize_stat_type(parts[-1])
        if stat.lower() in ("fantasy_score", "fantasy score"):
            raise ValueError(f"Fantasy Score — {first_player} skipped by rule")
''',
'''        stat = normalize_stat_type(parts[-1])
        # APEX-WIRING-2026-08-27: fantasy score is evaluable (engine category).
''')

# 4 ------------------------------------------------------------------ odds gate
edit("4 evaluate_manual_prop odds gate",
'''    # ── Filter out DEMON / Fantasy Score props first (unchanged rule) ──
    evaluable = []
    for prop in props:
        stat = prop.get("stat_type", "")
        pt   = prop.get("prop_type", prop.get("prop_type_classified", "standard"))

        if prop.get("is_demon") or pt == "demon":
            skipped_tags.append(
                f"DEMON skip: {prop.get('player','?')} {stat}")
            continue

        # APEX-ENGINE-PRIMARY-2026-08-23: fantasy score is skipped by the
        # LEGACY path only. The engine covers it (best-calibrated category on
        # the 2024+ holdout), so let it through when the operator supplied odds
        # -- the engine gate decides, and declines back to this skip if it
        # cannot price it.
        if stat.lower() in ("fantasy_score", "fantasy score"):
            _has_odds = bool(prop.get("apex_player_odds") and prop.get("apex_opponent_odds"))
            if not _has_odds:
                skipped_tags.append(
                    f"Fantasy Score skip (no odds supplied): {prop.get('player','?')}")
                continue
''',
'''    # ── Filter out DEMON props first ──
    # APEX-WIRING-2026-08-27: the fantasy-score odds gate is gone. It required
    # operator-typed odds, which a Discord screenshot never carries (the
    # automatic Pinnacle price is fetched later, inside _apex_engine_pick), so
    # it blocked every fantasy screenshot. The engine gate decides now.
    evaluable = []
    for prop in props:
        stat = prop.get("stat_type", "")
        pt   = prop.get("prop_type", prop.get("prop_type_classified", "standard"))

        if prop.get("is_demon") or pt == "demon":
            skipped_tags.append(
                f"DEMON skip: {prop.get('player','?')} {stat}")
            continue
''')

# 5/6/7 -------------------------------------------------------------- stat map
edit("5-7 stat map / match-level / binary",
'''_APEX_STAT_MAP = {
    "aces":             "aces",
    "double_faults":    "dfs",
    "total_games":      "total_games",       # match-level
    "games_won":        "games_won",         # player-level
    "total_games_won":  "games_won",         # player-level (operator-confirmed)
    "total_sets":       "total_sets",        # match-level
    "sets":             "sets_won",          # player-level
    "break_points_won": "breaks",            # player-level
    "fantasy_score":    "fantasy_score",
    "total_tie_breaks": "tiebreaks",         # match-level  (APEX-ENGINE-ONLY-2026-08-24)
    "tie_breaks":       "tiebreaks",         # match-level
}
_APEX_MATCH_LEVEL = {"total_games", "total_sets", "tiebreaks"}
''',
'''# APEX-WIRING-2026-08-27: normalize_stat_type() lowercases the label PrizePicks
# shows and swaps spaces for underscores -- it does not translate. So the keys
# below must be the labels as displayed ("Sets Won" -> sets_won), plus aliases.
_APEX_STAT_MAP = {
    "aces":               "aces",
    "double_faults":      "dfs",
    "total_games":        "total_games",       # match-level
    "games_won":          "games_won",         # player-level
    "total_games_won":    "games_won",         # player-level (operator-confirmed)
    "total_sets":         "total_sets",        # match-level
    "sets":               "sets_won",          # player-level
    "sets_won":           "sets_won",          # player-level ("Sets Won" card)
    "break_points_won":   "breaks",            # player-level
    "fantasy_score":      "fantasy_score",
    "total_tie_breaks":   "tiebreaks",         # match-level  (APEX-ENGINE-ONLY-2026-08-24)
    "tie_breaks":         "tiebreaks",         # match-level
    "tiebreaks":          "tiebreaks",         # match-level
    "first_set_games":    "first_set_games",   # match-level
    "first_set_total_games": "first_set_games",
    "any_tiebreak":       "any_tiebreak",      # match-level, binary
    "any_tie_break":      "any_tiebreak",
    "any_tie_breaks":     "any_tiebreak",
    "first_set_winner":   "first_set_fav_wins",  # match-level, binary (dog flip below)
    "win_first_set":      "first_set_fav_wins",
    "goes_3_sets":        "goes_3_sets",       # match-level, binary
    "match_goes_3_sets":  "goes_3_sets",
    "3_sets":             "goes_3_sets",
    "goes_5_sets":        "goes_5_sets",       # match-level, binary
    "match_goes_5_sets":  "goes_5_sets",
    "5_sets":             "goes_5_sets",
}
_APEX_MATCH_LEVEL = {"total_games", "total_sets", "tiebreaks", "first_set_games",
                     "any_tiebreak", "goes_3_sets", "goes_5_sets", "first_set_fav_wins"}
# Binary categories: the simulator returns 0/1 per sim, so P(over 0.5) is the
# event probability. The line is always 0.5 regardless of what the card says.
_APEX_BINARY = {"any_tiebreak", "goes_3_sets", "goes_5_sets", "first_set_fav_wins"}
''')

# 8 ------------------------------------------------------------------ binary line
edit("8 binary line handling",
'''        try:
            line = float(prop.get("line"))
        except (TypeError, ValueError):
            _apex_decline(prop, f"declined ({player}): unusable line -> legacy")
            return None

        key   = ("match|" + cat) if cat in _APEX_MATCH_LEVEL else (player + "|" + cat)
''',
'''        # APEX-WIRING-2026-08-27: binary categories always evaluate at 0.5.
        if cat in _APEX_BINARY:
            line = 0.5
        else:
            try:
                line = float(prop.get("line"))
            except (TypeError, ValueError):
                _apex_decline(prop, f"declined ({player}): unusable line -> legacy")
                return None

        key   = ("match|" + cat) if cat in _APEX_MATCH_LEVEL else (player + "|" + cat)
''')

# 9 ------------------------------------------------------------------ dog flip
edit("9 first-set-winner dog flip (card)",
'''        if target is None or target.get("line") is None:
            _apex_decline(prop, f"declined ({player}): no {cat} row with a line -> legacy")
            return None

        card = _apex_engine_card(res, target, prop)
''',
'''        if target is None or target.get("line") is None:
            _apex_decline(prop, f"declined ({player}): no {cat} row with a line -> legacy")
            return None

        # APEX-WIRING-2026-08-27: first_set_fav_wins is simulated from the
        # FAVORITE's side. When the card names the underdog, present the
        # underdog's side on the card and in the pick direction. The forward
        # log row is written from the unflipped target so it stays
        # favorite-relative, which is what --settle-sackmann compares against.
        _apex_flip = (cat == "first_set_fav_wins"
                      and _fragility_name_match(player, res.get("dog", ""))
                      and not _fragility_name_match(player, res.get("fav", "")))
        if _apex_flip:
            _ct = dict(target)
            _ct["p_over"], _ct["p_under"] = target.get("p_under"), target.get("p_over")
            try:
                _ct["mean"] = 1.0 - float(target.get("mean"))
                _ct["edge"] = _ct["mean"] - 0.5
                _ct["p10"], _ct["p90"] = 1.0 - float(target.get("p90")), 1.0 - float(target.get("p10"))
                _ct["p50"] = 1.0 - float(target.get("p50"))
            except (TypeError, ValueError):
                pass
            _ct["reasons"] = ["shown from the underdog's side (simulated as P(favorite wins set 1))"] + list(target.get("reasons") or [])[:2]
            card = _apex_engine_card(res, _ct, prop)
        else:
            card = _apex_engine_card(res, target, prop)
''')

edit("9b first-set-winner dog flip (pick direction)",
'''        direction = "MORE" if _po >= _pu else "LESS"
        _raw      = _po if direction == "MORE" else _pu
        prob      = (_raw / (_po + _pu)) if (_po + _pu) > 0 else _raw
''',
'''        direction = "MORE" if _po >= _pu else "LESS"
        _raw      = _po if direction == "MORE" else _pu
        prob      = (_raw / (_po + _pu)) if (_po + _pu) > 0 else _raw
        if _apex_flip:
            # APEX-WIRING-2026-08-27: same probability, opposite label for the dog
            direction = "LESS" if direction == "MORE" else "MORE"
''')

# 10 ----------------------------------------------------------------- slip abbreviations
edit("10 slip abbreviations",
'''STAT_ABBREV = {
    "tg":    "total_games",
    "sets":  "total_sets",
''',
'''STAT_ABBREV = {
    "tg":    "total_games",
    "sets":  "sets_won",      # APEX-WIRING-2026-08-27: "Sets Won" is the common player prop
    "ts":    "total_sets",    # APEX-WIRING-2026-08-27
''')


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def main():
    dry = "--dry-run" in sys.argv
    if not os.path.exists(TARGET):
        sys.exit(f"{TARGET} not found -- run from ~/openclaw")
    src = open(TARGET, encoding="utf-8").read()
    if MARKER in src:
        sys.exit(f"{MARKER} already present in {TARGET} -- refusing to re-apply")
    print(f"{MARKER}  {TARGET}  sha256 {sha(TARGET)}")

    problems = []
    for name, old, new in EDITS:
        n = src.count(old)
        print(f"  [{'ok' if n == 1 else 'FAIL'}] {name}: {n} match(es)")
        if n != 1:
            problems.append(name)
    if problems:
        sys.exit(f"ABORT -- {len(problems)} edit(s) did not match exactly once: {problems}. Nothing written.")
    if dry:
        print("dry run: all asserts pass, nothing written")
        return

    out = src
    for name, old, new in EDITS:
        out = out.replace(old, new, 1)

    # sanity: no fantasy skip text survives anywhere in the engine/batch/text paths
    leftovers = [s for s in ("Fantasy Score skip", "skipped by rule", "Fantasy score excluded",
                             "Fantasy score = always skip") if s in out]
    if leftovers:
        sys.exit(f"ABORT -- fantasy skip text still present after edits: {leftovers}. Nothing written.")

    bak = f"{TARGET}.bak_{datetime.now().strftime('%Y%m%d_%H%M%S')}_prewiring"
    shutil.copy2(TARGET, bak)
    with open(TARGET, "w", encoding="utf-8") as fh:
        fh.write(out)
    import py_compile
    try:
        py_compile.compile(TARGET, doraise=True)
    except Exception as e:
        shutil.copy2(bak, TARGET)
        sys.exit(f"ABORT -- patched file failed to compile ({e}); original restored from {bak}")
    print(f"backup  {bak}")
    print(f"written {TARGET}  sha256 {sha(TARGET)}  (py_compile OK)")
    print("next: rm -rf __pycache__ ; python3 apex_wiring_probe.py ; then restart the bot")


if __name__ == "__main__":
    main()
