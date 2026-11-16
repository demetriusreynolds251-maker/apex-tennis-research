#!/usr/bin/env python3
"""
apex_fragility_wire_patch.py -- APEX-FRAGILITY-WIRE-2026-08-21

Wires the Fragility V3 informational layer into the BATCH moneyline Discord
post in openclaw_core.py. Display and logging layer ONLY:
  * adds one helper, _fragility_block(), inserted before
    finalize_batch_ml_evaluation()
  * appends the block to the already-built `compact` message right before
    send_discord("moneyline", compact)
  * touches NOTHING else: winner selection, confidence, recommendation,
    Dataset A, compliance, and cross-check logic are byte-identical
  * fail-open: if fragility cannot score (missing model/state/player/odds or
    any exception), the block is empty and the post is unchanged

Safety: backs up openclaw_core.py, asserts both anchors occur exactly once,
compiles the result, prints marker counts.
Run:   python3 apex_fragility_wire_patch.py           (apply)
       python3 apex_fragility_wire_patch.py --check   (report only)
Rollback: restore the printed .bak file.
"""
import os, sys, shutil, py_compile
from datetime import datetime

CORE = "openclaw_core.py"
MARK = "APEX-FRAGILITY-WIRE-2026-08-21"

HELPER = '''
# ---------------------------------------------------------------------------
# APEX-FRAGILITY-WIRE-2026-08-21 -- Fragility V3 informational display layer.
# Display + logging ONLY. Never alters winner, confidence, recommendations,
# Dataset A, compliance, or cross-check logic. Fail-open by contract: any
# problem returns "" and the Discord post is exactly what it was before.
# ---------------------------------------------------------------------------
def _fragility_american_to_prob(odds_str):
    s = str(odds_str).strip().replace("\\u2212", "-")
    if not s or s in ("--", "-", "\\u2014"):
        return None
    v = float(s.replace("+", ""))
    if v == 0:
        return None
    return (-v) / ((-v) + 100.0) if v < 0 else 100.0 / (v + 100.0)


def _fragility_block(player, opponent, player_odds, opponent_odds,
                     surface, tour, tournament):
    """APEX-FRAGILITY-WIRE-2026-08-21: returns the informational block or ""."""
    try:
        pa = _fragility_american_to_prob(player_odds)
        pb = _fragility_american_to_prob(opponent_odds)
        if pa is None or pb is None or (pa + pb) <= 0:
            return ""
        fair_a = pa / (pa + pb)              # de-vig: normalize the two sides
        if fair_a >= 0.5:
            fav, dog, fav_p = player, opponent, fair_a
        else:
            fav, dog, fav_p = opponent, player, 1.0 - fair_a
        import fragility_live
        r = fragility_live.score_for_apex(
            fav, dog, fav_p,
            surface=str(surface).title(), tour=str(tour),
            tournament=str(tournament), round_="",
            price_source="devig_entered")
        if not r:
            return ""
        return ("\\u2014\\u2014\\u2014 Fragility (informational) \\u2014\\u2014\\u2014\\n"
                + r["block"].replace("\\\\n", "\\n"))
    except (Exception, SystemExit):
        return ""


'''

ANCHOR_DEF = "def finalize_batch_ml_evaluation(batch_state, eval_text, stop_reason, dates):"

ANCHOR_POST = '''        if final.get("compliance_note"):
            compact += f"\\n{final['compliance_note']}"
        _post_ok = send_discord("moneyline", compact)'''

INSERT_POST = '''        if final.get("compliance_note"):
            compact += f"\\n{final['compliance_note']}"
        # APEX-FRAGILITY-WIRE-2026-08-21: informational block, appended last
        _frag_block = _fragility_block(player, opponent, player_odds,
                                       opponent_odds, surface, tour, tournament)
        if _frag_block:
            compact += "\\n" + _frag_block
        _post_ok = send_discord("moneyline", compact)'''


def main():
    src = open(CORE, encoding="utf-8").read()
    applied = src.count(MARK)
    if "--check" in sys.argv:
        print("%s occurrences in %s: %d  (%s)"
              % (MARK, CORE, applied, "APPLIED" if applied >= 3 else "not applied"))
        return
    if applied:
        print("already applied (%d markers) -- nothing to do" % applied)
        return
    assert src.count(ANCHOR_DEF) == 1, \
        "finalize_batch_ml_evaluation def anchor not found exactly once -- core changed; stop and re-read"
    assert src.count(ANCHOR_POST) == 1, \
        "posting anchor not found exactly once -- core changed since 2026-08-20 read; stop and re-read"
    bak = "%s.bak_%s" % (CORE, datetime.now().strftime("%Y%m%d_%H%M%S"))
    shutil.copy2(CORE, bak)
    out = src.replace(ANCHOR_DEF, HELPER + ANCHOR_DEF, 1)
    out = out.replace(ANCHOR_POST, INSERT_POST, 1)
    open(CORE, "w", encoding="utf-8").write(out)
    py_compile.compile(CORE, doraise=True)
    print("patched %s  (backup %s); markers now %d; compiles OK"
          % (CORE, bak, out.count(MARK)))
    print("scope: BATCH moneyline posts only in this patch; display+log layer; fail-open")


if __name__ == "__main__":
    main()
