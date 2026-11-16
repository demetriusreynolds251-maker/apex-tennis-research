#!/usr/bin/env python3
"""APEX-PICKSCHANNEL-TIER-2026-09-28 -- adds the requested probability-tier
emoji scale and the below-floor research note directly onto the Picks
Channel card text for engine picks (the `card` string built by
_apex_engine_card, returned verbatim by format_pick_card via
pick["_apex_engine_card"]). Purely cosmetic/additive: appends two lines to
the existing card, changes no scoring, ranking, floor, or eligibility
logic (those were handled by apex_floor_to_eligibility_patch.py). Tier
scale as specified: 🟢 Elite Pick 70%+, ✅ Strong Pick 65-69.9%,
🟡 Lean 60-64.9%, ⚠️ Watchlist 55-59.9%, 🔴 Below Edge Threshold <55%.

Usage: python3 apex_picks_channel_tier_patch.py --check | --apply"""
import hashlib, shutil, sys, py_compile, datetime

F = "openclaw_core.py"
PIN = "ab34c5155a8bab03e6bf15bef5bd1084fcd3baa47efadd459caa9d40e42e32b2"
MARK = "APEX-PICKSCHANNEL-TIER-2026-09-28"

A1_OLD = '''        elif _ptype_elig == "standard" and not best_standard_eligible:
            _eligibility_note = (f"⚠️ Below Best Standard Threshold ({prob:.1%}) — "
                                  f"still tracked for research purposes.")
            log("ApexEngine", f"STANDARD below Best-Standard threshold (still published) — "
                              f"{player} {slug} {line} p={prob:.1%} < {_STANDARD_MIN_WIN_PROB:.1%}")

'''
A1_NEW = '''        elif _ptype_elig == "standard" and not best_standard_eligible:
            _eligibility_note = (f"⚠️ Below Best Standard Threshold ({prob:.1%}) — "
                                  f"still tracked for research purposes.")
            log("ApexEngine", f"STANDARD below Best-Standard threshold (still published) — "
                              f"{player} {slug} {line} p={prob:.1%} < {_STANDARD_MIN_WIN_PROB:.1%}")

        # APEX-PICKSCHANNEL-TIER-2026-09-28: cosmetic scan-tier line for the
        # Picks Channel card itself (every prop still gets one, floor or no
        # floor) + the below-floor research note when it applies. Tier is
        # purely a display label over the same real probability -- does not
        # change confidence, score, rank, or eligibility.
        if prob >= 0.70:
            _tier_line = f"🟢 Elite Pick ({prob:.1%})"
        elif prob >= 0.65:
            _tier_line = f"✅ Strong Pick ({prob:.1%})"
        elif prob >= 0.60:
            _tier_line = f"🟡 Lean ({prob:.1%})"
        elif prob >= 0.55:
            _tier_line = f"⚠️ Watchlist ({prob:.1%})"
        else:
            _tier_line = f"🔴 Below Edge Threshold ({prob:.1%})"
        card = f"{card}\\n{_tier_line}"
        if _eligibility_note:
            card = f"{card}\\n{_eligibility_note}"

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
    print("CHECK OK: SHA pinned, anchors %d/%d unique" % (len(ANCHORS), len(ANCHORS)))
    if mode != "--apply":
        return
    bak = F + ".bak_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + "_prepickstier"
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
