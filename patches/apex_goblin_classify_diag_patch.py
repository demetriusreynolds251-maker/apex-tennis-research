#!/usr/bin/env python3
"""APEX-GOBLIN-CLASSIFY-DIAG-2026-09-28 -- diagnostics-only. Adds NO new
behavior to prop classification: is_goblin/is_demon/both_directions_available
are computed exactly as before, byte-for-byte. This only (1) carries the raw
discount_percentage/is_promo values through onto the prop dict (previously
computed and then dropped -- classify_prop_type() downstream never saw them),
and (2) appends one diagnostic row per fetched prop to a new, append-only CSV
so the actual evidence needed to investigate the Goblin classifier (requested
2026-09-28, "gather evidence before changing production behavior") exists
going forward. Confirmed by direct inspection: discount_percentage and
is_promo have never been written to any file on disk before this patch --
there is no way to retroactively audit the last 30 days because the raw data
was never kept, only the already-derived is_goblin/is_demon booleans (which
themselves were never logged either). This patch starts collecting the
missing evidence; it does not analyze it and does not touch classify_prop_type(),
filter_props(), or _apex_engine_pick() in any way.

Usage: python3 apex_goblin_classify_diag_patch.py --check | --apply"""
import hashlib, shutil, sys, py_compile, datetime

F = "openclaw_core.py"
PIN = "e01fa839805f646cd90348fab0f4d9f640bbef28cf6a69c31a9442468b03ce82"
MARK = "APEX-GOBLIN-CLASSIFY-DIAG-2026-09-28"

A1_OLD = '''            # Classify prop type
            is_demon  = attrs.get("is_promo", False) and attrs.get("discount_percentage", 0) < 0
            is_goblin = (attrs.get("discount_percentage", 0) > 0 or
                         attrs.get("is_promo", False)) and not is_demon

            props.append({
                "id":                        proj.get("id"),
                "player":                    attrs.get("name", ""),
                "opponent":                  (attrs.get("description", "")
                                              .split(" vs ")[-1]
                                              if " vs " in attrs.get("description", "")
                                              else ""),
                "stat_type":                 normalize_stat_type(attrs.get("stat_type", "")),
                "line":                      float(attrs.get("line_score", 0)),
                "tournament":                attrs.get("league", "Tennis"),
                "surface":                   attrs.get("surface", "clay"),
                "tournament_stage":          attrs.get("tournament_stage", 1),
                "round":                     attrs.get("round", ""),
                "is_grand_slam":             attrs.get("is_grand_slam", False),
                "both_directions_available": not attrs.get("is_promo", False),
                "is_goblin":                 is_goblin,
                "is_demon":                  is_demon,
                "match_date":                start_time[:10],
                "same_day_3set_count":       0,
            })
'''
A1_NEW = '''            # Classify prop type
            is_demon  = attrs.get("is_promo", False) and attrs.get("discount_percentage", 0) < 0
            is_goblin = (attrs.get("discount_percentage", 0) > 0 or
                         attrs.get("is_promo", False)) and not is_demon

            # APEX-GOBLIN-CLASSIFY-DIAG-2026-09-28: diagnostics only, no
            # behavior change. discount_percentage/is_promo were computed
            # above but never carried past this point or logged anywhere --
            # there was no evidence trail to investigate the classifier
            # with. This just keeps the raw values (as new, additional
            # dict keys -- nothing existing is altered) and records why
            # is_goblin came out the way it did, one row per fetched prop.
            _dp = attrs.get("discount_percentage", 0)
            _ip = attrs.get("is_promo", False)
            if is_demon:
                _reason = "is_demon (is_promo + discount<0)"
            elif _dp and float(_dp) > 0:
                _reason = "discount_percentage>0 (%.4g)" % float(_dp)
            elif _ip and (not _dp or float(_dp) == 0):
                _reason = "is_promo_true_discount_zero"
            elif _ip:
                _reason = "is_promo_true_discount_other (%.4g)" % float(_dp or 0)
            else:
                _reason = "neither_flag (standard)"
            try:
                _apex_log_goblin_classify_diag(
                    player=attrs.get("name", ""), opponent=attrs.get("description", ""),
                    stat_type=attrs.get("stat_type", ""), line=attrs.get("line_score", 0),
                    match_date=start_time[:10], discount_percentage=_dp, is_promo=_ip,
                    is_demon=is_demon, is_goblin=is_goblin, reason=_reason)
            except Exception as _e:
                log("Fetch", f"goblin classify diag log failed (non-fatal): {_e}")

            props.append({
                "id":                        proj.get("id"),
                "player":                    attrs.get("name", ""),
                "opponent":                  (attrs.get("description", "")
                                              .split(" vs ")[-1]
                                              if " vs " in attrs.get("description", "")
                                              else ""),
                "stat_type":                 normalize_stat_type(attrs.get("stat_type", "")),
                "line":                      float(attrs.get("line_score", 0)),
                "tournament":                attrs.get("league", "Tennis"),
                "surface":                   attrs.get("surface", "clay"),
                "tournament_stage":          attrs.get("tournament_stage", 1),
                "round":                     attrs.get("round", ""),
                "is_grand_slam":             attrs.get("is_grand_slam", False),
                "both_directions_available": not attrs.get("is_promo", False),
                "is_goblin":                 is_goblin,
                "is_demon":                  is_demon,
                "match_date":                start_time[:10],
                "same_day_3set_count":       0,
                "discount_percentage":       _dp,          # APEX-GOBLIN-CLASSIFY-DIAG-2026-09-28
                "is_promo_raw":              _ip,          # new field, additive only
                "goblin_classify_reason":    _reason,      # new field, additive only
            })
'''

A2_OLD = '''NON_COMPLETION_KEYWORDS = [
    "retired", "ret.", "walkover", "w/o", "withdrawal", "injured",
    "defaulted", "postponed", "suspended", "rain", "weather",
    "abandoned", "not completed", "early retirement", "retires"
]
'''
A2_NEW = '''NON_COMPLETION_KEYWORDS = [
    "retired", "ret.", "walkover", "w/o", "withdrawal", "injured",
    "defaulted", "postponed", "suspended", "rain", "weather",
    "abandoned", "not completed", "early retirement", "retires"
]

# ================================================================
# APEX-GOBLIN-CLASSIFY-DIAG-2026-09-28 -- diagnostics-only evidence log.
# Appends one row per fetched prop, capturing the raw discount_percentage /
# is_promo values from PrizePicks and the reason is_goblin/is_demon came out
# the way it did. Never read by, and never influences, classification,
# filtering, ranking, or the engine -- write-only, fail-open, purely so the
# evidence exists to later investigate whether is_promo-without-discount
# props are real Goblin markets or something else. Directive: "gather
# sufficient evidence before changing classification logic."
# ================================================================
import csv as _apex_csv_diag
_APEX_GOBLIN_DIAG_LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                      "apex_goblin_classification_diag_v1.csv")
_APEX_GOBLIN_DIAG_FIELDS = ["ts", "match_date", "player", "opponent", "stat_type", "line",
                            "discount_percentage", "is_promo", "is_demon", "is_goblin", "reason"]


def _apex_log_goblin_classify_diag(player, opponent, stat_type, line, match_date,
                                    discount_percentage, is_promo, is_demon, is_goblin, reason):
    row = {"ts": datetime.now().isoformat(timespec="seconds"),
           "match_date": match_date, "player": player, "opponent": opponent,
           "stat_type": stat_type, "line": line, "discount_percentage": discount_percentage,
           "is_promo": is_promo, "is_demon": is_demon, "is_goblin": is_goblin, "reason": reason}
    _is_new = not os.path.exists(_APEX_GOBLIN_DIAG_LOG)
    with open(_APEX_GOBLIN_DIAG_LOG, "a", newline="", encoding="utf-8") as fh:
        w = _apex_csv_diag.DictWriter(fh, fieldnames=_APEX_GOBLIN_DIAG_FIELDS)
        if _is_new:
            w.writeheader()
        w.writerow(row)
'''

ANCHORS = [("A1", A1_OLD, A1_NEW), ("A2", A2_OLD, A2_NEW)]


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
    print("CHECK OK: SHA pinned, anchors 2/2 unique")
    if mode != "--apply":
        return
    bak = F + ".bak_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + "_pregoblindiag"
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
