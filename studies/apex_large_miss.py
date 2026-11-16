#!/usr/bin/env python3
"""APEX-MISS-001 -- large projection miss investigation.
Analyses HOW FAR outcomes fall from projections, independent of win/loss.
Read-only. Answers: category concentration, format, band breach rates, z-distribution.
"""
import csv, os, statistics, collections
SIM = "apex_prop_sim_forward_log_v1.csv"

def _f(v):
    try: return float(v)
    except (TypeError, ValueError): return None

def rows():
    out = []
    if not os.path.exists(SIM): return out
    for r in csv.DictReader(open(SIM, newline="", encoding="utf-8")):
        a, m, sd = _f(r.get("actual")), _f(r.get("mean")), _f(r.get("sd"))
        p10, p90, line = _f(r.get("p10")), _f(r.get("p90")), _f(r.get("line"))
        if a is None or m is None: continue
        po, pu = _f(r.get("p_over")) or 0, _f(r.get("p_under")) or 0
        d = "MORE" if po >= pu else "LESS"
        out.append({"player": r.get("player"), "opponent": r.get("opponent"),
                    "cat": r.get("category"), "date": r.get("match_date"),
                    "bo5": str(r.get("best_of") or "") == "5",
                    "line": line, "proj": m, "sd": sd, "p10": p10, "p90": p90,
                    "actual": a, "err": a - m, "abs": abs(a - m),
                    "z": ((a - m) / sd) if sd else None,
                    "above_p90": (p90 is not None and a > p90),
                    "below_p10": (p10 is not None and a < p10),
                    "dir": d,
                    "hit": None if (line is None or a == line) else ((a > line) if d == "MORE" else (a < line))})
    return out

def main():
    R = rows()
    if not R: print("WAITING FOR DATA"); return
    n = len(R)
    print("# LARGE PROJECTION MISS INVESTIGATION   (n=%d settled picks with projections)\n" % n)

    print("## 1. TEN LARGEST MISSES (by |actual - projection|)")
    print("| player | cat | bo | line | proj | p10-p90 | actual | err | z | breach | W/L |")
    print("|---|---|---|---|---|---|---|---|---|---|---|")
    for x in sorted(R, key=lambda r: -r["abs"])[:10]:
        breach = "ABOVE p90" if x["above_p90"] else ("BELOW p10" if x["below_p10"] else "in band")
        print("| %s | %s | %s | %s | %.1f | %s-%s | %.1f | %+.1f | %s | %s | %s |" % (
            str(x["player"])[:16], x["cat"], "5" if x["bo5"] else "3", x["line"], x["proj"],
            x["p10"], x["p90"], x["actual"], x["err"],
            ("%+.1f" % x["z"]) if x["z"] is not None else "-", breach,
            "-" if x["hit"] is None else ("W" if x["hit"] else "L")))

    print("\n## 2-3. BY CATEGORY")
    print("| category | n | MAE | mean err | out-of-band | above p90 | below p10 | max |z| |")
    print("|---|---|---|---|---|---|---|---|")
    byc = collections.defaultdict(list)
    for x in R: byc[x["cat"]].append(x)
    for c, xs in sorted(byc.items(), key=lambda kv: -statistics.mean(v["abs"] for v in kv[1])):
        oob = sum(1 for v in xs if v["above_p90"] or v["below_p10"])
        zs = [abs(v["z"]) for v in xs if v["z"] is not None]
        print("| %s | %d | %.2f | %+.2f | %d (%.0f%%) | %d | %d | %.1f |" % (
            c, len(xs), statistics.mean(v["abs"] for v in xs), statistics.mean(v["err"] for v in xs),
            oob, 100.0*oob/len(xs), sum(1 for v in xs if v["above_p90"]),
            sum(1 for v in xs if v["below_p10"]), max(zs) if zs else 0))
    print("\n*Expected out-of-band rate if the distribution is honest: ~20%*")

    print("\n## 4. BY FORMAT")
    for lbl, xs in (("Bo5", [x for x in R if x["bo5"]]), ("Bo3", [x for x in R if not x["bo5"]])):
        if not xs: print("| %s | no settled picks |" % lbl); continue
        oob = sum(1 for v in xs if v["above_p90"] or v["below_p10"])
        print("| %-3s | n=%2d | MAE %.2f | bias %+.2f | out-of-band %d (%.0f%%) |" % (
            lbl, len(xs), statistics.mean(v["abs"] for v in xs),
            statistics.mean(v["err"] for v in xs), oob, 100.0*oob/len(xs)))

    print("\n## 5. BY PLAYER (2+ settled)")
    byp = collections.defaultdict(list)
    for x in R: byp[str(x["player"])].append(x)
    multi = [(p, xs) for p, xs in byp.items() if len(xs) >= 2]
    for p, xs in sorted(multi, key=lambda kv: -statistics.mean(v["abs"] for v in kv[1]))[:8]:
        print("  %-20s n=%d  MAE %.2f  bias %+.2f" % (p[:20], len(xs),
              statistics.mean(v["abs"] for v in xs), statistics.mean(v["err"] for v in xs)))

    print("\n## 6. DIAGNOSIS")
    zs = [x["z"] for x in R if x["z"] is not None]
    oob_all = sum(1 for x in R if x["above_p90"] or x["below_p10"])
    above = sum(1 for x in R if x["above_p90"]); below = sum(1 for x in R if x["below_p10"])
    mean_err = statistics.mean(x["err"] for x in R)
    sd_of_z = statistics.pstdev(zs) if len(zs) > 1 else 0
    print("Overall out-of-band: %d/%d (%.0f%%)   [expected ~20%%]" % (oob_all, n, 100.0*oob_all/n))
    print("Breaches above p90: %d | below p10: %d   [expected ~equal if unbiased]" % (above, below))
    print("Mean signed error: %+.2f   [0 if unbiased]" % mean_err)
    print("Std-dev of z-scores: %.2f   [1.0 if the sd model is right; >1 = bands too narrow]" % sd_of_z)
    print("\nREADING:")
    if sd_of_z > 1.25:
        print("  B. DISTRIBUTION ERROR is indicated -- z spread %.2f exceeds 1.0, meaning actual" % sd_of_z)
        print("     variation is wider than the model's sd. Projections may be fine; bands are not.")
    elif abs(mean_err) > 1.0:
        print("  A/E. PROJECTION or SCALING ERROR indicated -- systematic %+.2f bias means the" % mean_err)
        print("     center is off, not just the spread.")
    else:
        print("  No single failure mode dominates at this n. Both spread and center look tolerable.")
    if abs(above - below) >= max(3, 0.3 * max(oob_all, 1)):
        print("  Asymmetric breaches (%d above vs %d below) -- one tail is worse than the other." % (above, below))
    print("\nNOTE: n=%d. Category-level rows with n<5 are indicative only." % n)

if __name__ == "__main__":
    main()
