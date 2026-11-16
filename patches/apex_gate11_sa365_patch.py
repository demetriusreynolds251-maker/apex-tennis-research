#!/usr/bin/env python3
"""APEX-GATE11-SA365-2026-09-23 -- Gate 11 checks SportsAPI365's match lists first.
The old stats service is gone; its local name list only knows established players, so
Challenger/ITF pairs were rejected as 'not found'. Listed by SportsAPI365 -> verified
(tour corrected if needed, same alert as before). Not listed -> the old check, unchanged.
Usage: python3 apex_gate11_sa365_patch.py --check | --apply"""
import hashlib, shutil, sys, py_compile, datetime
F = "openclaw_core.py"; PIN = "3c7c34f09ce77c750b57913b9f40b66dba64047c0146e72af006cae5f11dd6fe"
MARK = "APEX-GATE11-SA365-2026-09-23"
A1_OLD = '''    match_date = prop.get("match_date") or dates.get("match_date")

    if not _V8_AVAILABLE:
        # Fix (2026-07-23, approved): every Gate 11 REJECTED/UNVERIFIED
'''
A1_NEW = '''    match_date = prop.get("match_date") or dates.get("match_date")

    # APEX-GATE11-SA365-2026-09-23: check SportsAPI365's match lists first. The old
    # stats service is gone and its local name list only knows established players,
    # so Challenger/ITF pairs were rejected as "not found". If SportsAPI365 lists this
    # pair, the match is real: verified, and its tour is used. A listed match that has
    # already started is NOT rejected here (ITF matches often start late; pricing
    # decides). Not listed -> the old check below, unchanged.
    try:
        import apex_price_feed as _apf_g11
        _fc11 = _apf_g11.fixture_context(player, opponent)
    except Exception as _e:
        _fc11 = None
        log("Gate11", f"SportsAPI365 match-list check unavailable (non-fatal): {_e}")
    if _fc11:
        _t11 = str(_fc11.get("tour") or "").lower()
        _st11 = (prop.get("tour") or "atp").lower().strip()
        if _t11 in ("atp", "wta") and _t11 != _st11:
            prop["tour"] = _t11
            log("Gate11", f"Tour corrected: {_st11} -> {_t11} (SportsAPI365)")
            send_discord("alerts",
                f"⚠️ **Gate 11 TOUR CORRECTED** — {dates['ct_time']}\\n"
                f"Match: {player} vs {opponent}\\n"
                f"Input said: **{_st11.upper()}** | SportsAPI365 lists: **{_t11.upper()}**\\n"
                f"Evaluation proceeding with corrected tour."
            )
        log("Gate11", f"VERIFIED — {player} vs {opponent} — SportsAPI365 lists it: "
            f"{_fc11.get('tournament')} | {_t11 or '?'} | starts {_fc11.get('start_time')} "
            f"| started={_fc11.get('started')} ({_fc11.get('match_method')})")
        return {"status": "PASSED", "verified": True}

    if not _V8_AVAILABLE:
        # Fix (2026-07-23, approved): every Gate 11 REJECTED/UNVERIFIED
'''
def sha(p): return hashlib.sha256(open(p, "rb").read()).hexdigest()
def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "--check"
    src = open(F, encoding="utf-8").read(); s = sha(F)
    assert s == PIN, f"SHA mismatch: {s}"; assert MARK not in src, "already applied"
    c = src.count(A1_OLD); assert c == 1, f"anchor A1 matched {c}x"
    print("CHECK OK: SHA pinned, anchor 1/1 unique")
    if mode != "--apply": return
    bak = F + ".bak_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + "_pregate11sa365"; shutil.copy2(F, bak)
    open(F, "w", encoding="utf-8").write(src.replace(A1_OLD, A1_NEW, 1))
    try: py_compile.compile(F, doraise=True)
    except Exception as e: shutil.copy2(bak, F); print("py_compile FAILED -> restored:", e); sys.exit(1)
    print("APPLIED. backup:", bak); print("new sha:", sha(F))
if __name__ == "__main__": main()
