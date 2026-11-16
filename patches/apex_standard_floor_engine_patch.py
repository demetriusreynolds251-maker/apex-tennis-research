#!/usr/bin/env python3
"""APEX-STANDARD-FLOOR-ENGINE-2026-09-28 -- adds a hard Standard qualification
floor to the live pick path, using the exact same architecture as the Goblin
break-even floor (APEX-GOBLIN-FLOOR-ENGINE-2026-09-28, applied earlier the
same day).

Business/risk decision (explicit, 2026-09-28): historical settled-pick volume
for Standard is far too small to statistically derive an optimal probability
threshold (62 settled Standard picks total, all from 2026-09-24/25 -- see the
backtest report). This floor is NOT a calibration-derived number and is not
claimed to be one. It is a deliberate quality bar: Standard props must clear
70.0% of the engine's own real win probability to qualify for publication at
all. Quality over quantity, by directive, not by backtest.

Placement: inside _apex_engine_pick(), immediately after the existing Goblin
break-even check and before the forward-log write / return -- the same
point every other decline in this function already uses, and the only point
before a pick is logged, ranked, or posted anywhere. Matches
process_single_prop's existing APEX_ENGINE_ONLY guardrail exactly: a None
return here becomes a real ENGINE_DECLINED termination (d1.terminate) with
this check's own reason string, a #alerts post, and no picks-log row --
_apex_forward_log_row() sits below this check and is never reached.

Scope: Standard only (prop.get("prop_type_classified") == "standard"),
matching the classifier's real value (see classify_prop_type()). Does not
touch Goblin, red_demon, or demon handling, and does not alter ranking,
dedup, slip-cap, or board-rendering code -- those all operate on whatever
pick list _apex_engine_pick() hands back, and a Standard prop below 70%
never becomes a pick in the first place, so there is nothing for that code
to filter differently.

Usage: python3 apex_standard_floor_engine_patch.py --check | --apply"""
import hashlib, shutil, sys, py_compile, datetime

F = "openclaw_core.py"
PIN = "4c5425603bdb9761c4b0fb57e657ea72e0bb14189dad1daa9551c2bc5a64f430"
MARK = "APEX-STANDARD-FLOOR-ENGINE-2026-09-28"

A1_OLD = '''            except Exception:
                pass
            return None

        # ── APEX-FORWARD-LOG-2026-08-24: this pick exists outside Discord now
        try:
            _apex_forward_log_row(res, target, prop, player, opponent, cat, line, direction, prob, slug=slug)
        except Exception as _e:
            log("ApexEngine", f"forward log write failed (non-fatal): {_e}")
        return {
'''
A1_NEW = '''            except Exception:
                pass
            return None

        # APEX-STANDARD-FLOOR-ENGINE-2026-09-28: business/risk-management
        # floor (directive, 2026-09-28) -- NOT calibration-derived (settled
        # Standard sample too small: 62 total, 2 days). Quality-over-quantity
        # decision: Standard must clear 70.0% real engine win probability to
        # qualify for publication. Same placement/idiom as the Goblin check
        # immediately above: before logging, ranking, or posting -- a
        # below-floor Standard prop never becomes a pick.
        _STANDARD_MIN_WIN_PROB = 0.70
        if (str(prop.get("prop_type_classified") or "") == "standard"
                and prob < _STANDARD_MIN_WIN_PROB):
            _sf_reason = (f"standard quality floor: engine prob {prob:.1%} is below the "
                          f"{_STANDARD_MIN_WIN_PROB:.1%} minimum required for Standard "
                          f"publication -> legacy")
            _apex_decline(prop, _sf_reason)
            log("ApexEngine", f"STANDARD FLOOR BLOCK (engine path) — {player} {slug} {line} "
                              f"p={prob:.1%} below {_STANDARD_MIN_WIN_PROB:.1%}. No pick produced.")
            try:
                send_discord("alerts",
                    f"\U0001f6d1 **STANDARD BELOW FLOOR — NO PICK** — {player} vs {opponent}\\n"
                    f"`{line} {slug}` engine probability {prob:.1%} is below the "
                    f"{_STANDARD_MIN_WIN_PROB:.1%} minimum required for a Standard pick to publish. "
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
    bak = F + ".bak_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + "_prestandardfloorengine"
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
