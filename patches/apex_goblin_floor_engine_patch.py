#!/usr/bin/env python3
"""APEX-GOBLIN-FLOOR-ENGINE-2026-09-28 -- moves the Goblin break-even floor
into the actual live pick path.

Audit finding (confirmed by code inspection, not guessed): the 72.1%
Goblin break-even floor added by apex_goblin_floor_patch.py (2026-09-24)
lives entirely inside scoring_agent(), the legacy 11-step evaluator.
_apex_engine_pick() (APEX-ENGINE-PRIMARY-2026-08-23 -- Prop Model V1 +
Simulator V1) is what actually produces essentially every live pick today,
and its own docstring/comment says plainly: "On success this returns
immediately: no research_agent, no evaluation_agent, no compliance_agent,
no scoring_agent." Verified apex_prop_model_v1.py and apex_prop_sim_v1.py
(the frozen engine/simulator files) contain no Goblin/break-even logic of
their own. Net effect: every Goblin pick produced by the engine path has
had NO break-even enforcement since the engine went live -- the 09-24
patch has been dead code for the path that matters.

Fix: check the engine's own final `prob` (the number it already reports
as "Win Probability" -- the real win-probability the break-even math is
about) against the same GOBLIN_BREAKEVEN=0.721 constant, right where the
engine finalizes direction/prob and BEFORE the pick is written to the
forward/picks log or returned -- so a below-floor Goblin pick never
reaches the board at all, not just gets flagged after the fact.

On block: follows the exact same idiom every other decline path in this
function already uses (_apex_decline + return None), which the caller
(process_single_prop, APEX-ENGINE-ONLY-2026-08-24 guardrail) turns into a
proper d1.terminate(eval_id, "ENGINE_DECLINED", ...) + #alerts post + no
legacy fallback (APEX_ENGINE_ONLY defaults to on) -- no new decline
plumbing needed, this only had to be wired into a code path that already
handles it correctly.

Scope: Goblin only, matching the pre-existing, already-approved 0.721
constant. Demon has no equivalent floor anywhere in this codebase (old or
new) and none is added here -- its payout/break-even math was never
given to me and I'm not guessing at money math. 0 Demon props were on the
board at audit time, so this is lower urgency, but it is a real gap, not
an oversight (see the audit report).

Usage: python3 apex_goblin_floor_engine_patch.py --check | --apply"""
import hashlib, shutil, sys, py_compile, datetime

F = "openclaw_core.py"
PIN = "3acf8cff04cfec3723a6ac8f45027166ae9055c5867c2fc290b094fede66b98b"
MARK = "APEX-GOBLIN-FLOOR-ENGINE-2026-09-28"

A1_OLD = '''        target["push_prob"]  = round(_push, 4)
        target["p_pick_raw"] = round(_raw, 4)
        log("ApexEngine",
            f"ENGINE_PICK {player} {slug} {line} -> {direction} "
            f"p={prob:.3f} tier={target['tier']} (sim {res['sim_sha'][:8]})")
        # ── APEX-FORWARD-LOG-2026-08-24: this pick exists outside Discord now
        try:
            _apex_forward_log_row(res, target, prop, player, opponent, cat, line, direction, prob, slug=slug)
        except Exception as _e:
            log("ApexEngine", f"forward log write failed (non-fatal): {_e}")
        return {
'''
A1_NEW = '''        target["push_prob"]  = round(_push, 4)
        target["p_pick_raw"] = round(_raw, 4)
        log("ApexEngine",
            f"ENGINE_PICK {player} {slug} {line} -> {direction} "
            f"p={prob:.3f} tier={target['tier']} (sim {res['sim_sha'][:8]})")

        # APEX-GOBLIN-FLOOR-ENGINE-2026-09-28: the 09-24 Goblin break-even
        # floor lived only in scoring_agent(), which this engine path never
        # calls on success -- so it never ran for engine-produced Goblin
        # picks. Checked here, against the engine's own real win
        # probability, before the pick is logged or returned. Same
        # GOBLIN_BREAKEVEN constant as the original patch; same "no pick
        # produced" intent, now enforced where picks are actually made.
        _GOBLIN_BREAKEVEN_ENGINE = 0.721
        if (str(prop.get("prop_type_classified") or "") == "goblin"
                and prob < _GOBLIN_BREAKEVEN_ENGINE):
            _gb_reason = (f"goblin break-even block: engine prob {prob:.1%} is below the "
                          f"{_GOBLIN_BREAKEVEN_ENGINE:.1%} goblin payout needs to break even "
                          f"-> legacy")
            _apex_decline(prop, _gb_reason)
            log("ApexEngine", f"GOBLIN BREAK-EVEN BLOCK (engine path) — {player} {slug} {line} "
                              f"p={prob:.1%} below {_GOBLIN_BREAKEVEN_ENGINE:.1%}. No pick produced.")
            try:
                send_discord("alerts",
                    f"\U0001f6d1 **GOBLIN BELOW BREAK-EVEN — NO PICK** — {player} vs {opponent}\\n"
                    f"`{line} {slug}` engine probability {prob:.1%} is below the "
                    f"{_GOBLIN_BREAKEVEN_ENGINE:.1%} goblin payout requires to break even. "
                    f"Blocked in the engine path before posting."
                )
            except Exception:
                pass
            return None

        # ── APEX-FORWARD-LOG-2026-08-24: this pick exists outside Discord now
        try:
            _apex_forward_log_row(res, target, prop, player, opponent, cat, line, direction, prob, slug=slug)
        except Exception as _e:
            log("ApexEngine", f"forward log write failed (non-fatal): {_e}")
        return {
'''

ANCHORS = [("A1", A1_OLD, A1_NEW)]


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "--check"
    src = open(F, encoding="utf-8").read()
    s = sha(F)
    assert s == PIN, f"SHA mismatch: {s}"
    assert MARK not in src, "already applied"
    for n, o, _ in ANCHORS:
        c = src.count(o)
        assert c == 1, f"anchor {n} matched {c}x"
    print("CHECK OK: SHA pinned, anchors 1/1 unique")
    if mode != "--apply":
        return
    bak = F + ".bak_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + "_pregoblinfloorengine"
    shutil.copy2(F, bak)
    new = src
    for _, o, nw in ANCHORS:
        new = new.replace(o, nw, 1)
    open(F, "w", encoding="utf-8").write(new)
    try:
        py_compile.compile(F, doraise=True)
    except Exception as e:
        shutil.copy2(bak, F)
        print("py_compile FAILED -> restored:", e)
        sys.exit(1)
    print("APPLIED. backup:", bak)
    print("new sha:", sha(F))


if __name__ == "__main__":
    main()
