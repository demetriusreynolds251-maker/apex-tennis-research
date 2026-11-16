"""
apex_dispersion_fwd.py
APEX-DISPERSION-FWD-001

Forward test for the Ace dispersion calibration candidate, approved 2026-09-26.
See DISPERSION_FWD_DESIGN.md for the full design record.

SHADOW-ONLY: computes an ADDITIONAL prediction for aces-related match props
(most_aces_fav, total_aces, per-player aces) using tour-specific lowered
dispersion, and logs it side-by-side with production's own prediction. NEVER
changes what apex_prop_engine.evaluate_match() returns, what gets posted to
Discord, what gets priced, or what's written to the production forward log.

Fail-open throughout: any exception here is swallowed; the caller's flow is
unaffected either way. Does not modify apex_prop_sim_v1.py / apex_prop_model_v1.py
(frozen) or apex_prop_engine.py (production adapter) -- only reads via
apex_prop_engine._load(), read-only.

SCOPE: aces only. Double-faults dispersion stays on production's own
disp_mult path -- no DF calibration evidence exists for this candidate
(see DISPERSION_FWD_DESIGN.md Section 2).
"""
import os
import csv
import threading
from datetime import date as _date, datetime as _dt

MARKER = "APEX-DISPERSION-FWD-001"
HERE = os.path.dirname(os.path.abspath(__file__))
_FWD_LOG = os.path.join(HERE, "apex_dispersion_fwd_log_v1.csv")
_LOCK = None

# Frozen, evidence-fitted constants -- NOT re-fit here. Method-of-moments on
# fit_df (year<=2021), reproduced identically in apex_v2_dispersion_calib_tune.py,
# apex_v2_dispersion_calib_holdout.py, apex_v2_dispersion_promotion_analysis.py.
R_ATP = {"fav": 8.70148205269834, "dog": 5.885645957929439}
DM_ATP = 0.6
R_WTA = {"fav": 3.9866756061964232, "dog": 2.7971092624925418}
DM_WTA = 0.4

_FIELDS = [
    "ts", "match_id", "match_date", "fav", "dog", "tour", "surface", "best_of",
    "prod_most_aces_fav_p", "cand_most_aces_fav_p",
    "prod_total_aces_mean", "cand_total_aces_mean",
    "total_aces_line", "prod_total_aces_line_p_over", "cand_total_aces_line_p_over",
    "prod_fav_aces_mean", "cand_fav_aces_mean",
    "prod_dog_aces_mean", "cand_dog_aces_mean",
    "actual_fav_aces", "actual_dog_aces", "actual_total_aces", "actual_most_aces_fav",
    "settled_ts", "sim_sha", "v1_sha",
]


def shadow_predict(res, wta):
    """Re-runs ONLY the final simulate() call from res's own solved inputs,
    substituting the candidate's aces dispersion. DFs keep production's own
    disp_mult path. Returns a dict of candidate numbers, or None on failure.
    Never raises. `res` is production's own evaluate_match() return dict,
    unmodified -- this reads it, never writes to it.
    """
    try:
        import numpy as np
        import apex_prop_engine as ape
        z = ape._load()
        v1, sim = z["v1"], z["sim"]
        today = _date.fromisoformat(res["date"])
        favn, dogn = res["fav"], res["dog"]
        pinn = float(res["pinn_fav"])
        surface = str(res["surface"])
        bo = int(res["best_of"])
        bo5 = (bo == 5)
        df = sim.build_live_row(favn, dogn, pinn, surface, bo5, wta, today, z["m"], z["state"])
        _, hf, hd, mu = sim.v1_inputs_from_rows(df, z["m"])
        lv = sim.level_from(hf[0], hd[0], z["c"], sim.price_level_pred(df, z["c"])[0])
        t, _flag = sim.solve_tilt(lv, pinn, z["c"]["tb_k"], bo, sigma=z["c"].get("gap_sigma", 0.0))
        hA = min(max(lv + t, 0.2), 0.995)
        hB = min(max(lv - t, 0.2), 0.995)
        r, dm = (R_WTA, DM_WTA) if wta else (R_ATP, DM_ATP)
        dfs_dm = z["c"].get("disp_mult", 1.0)  # aces-only scope: DFs untouched
        n_sims = int(res.get("sims") or ape.DEFAULT_SIMS)
        s = sim.simulate(
            hA, hB, z["c"]["tb_k"], bo,
            (mu["fav"][0][0], mu["fav"][1][0]), (mu["dog"][0][0], mu["dog"][1][0]),
            (r["fav"] * dm, z["c"]["disp"]["fav"]["dfs"] * dfs_dm),
            (r["dog"] * dm, z["c"]["disp"]["dog"]["dfs"] * dfs_dm),
            n_sims, sigma=z["c"].get("gap_sigma", 0.0),
        )
        return {
            "most_aces_fav_p": float(np.mean(s["most_aces_fav"])),
            "total_aces_mean": float(np.mean(s["total_aces"])),
            "total_aces_samp": s["total_aces"],
            "fav_aces_mean": float(np.mean(s["fav"]["aces"])),
            "dog_aces_mean": float(np.mean(s["dog"]["aces"])),
        }
    except Exception:
        return None


def log_shadow_row(res, wta):
    """Call once per evaluated match, after apex_prop_engine.evaluate_match()
    has returned ok, for an aces-related category only. Appends one row
    (deduped on match_id) to apex_dispersion_fwd_log_v1.csv. Fail-open:
    any error returns False, writes nothing, never raises -- the caller's
    flow (pick, price, Discord card, production forward log) is completely
    unaffected either way.
    """
    global _LOCK
    if _LOCK is None:
        _LOCK = threading.Lock()
    try:
        import numpy as np
        if not res or not res.get("ok"):
            return False
        cand = shadow_predict(res, wta)
        if cand is None:
            return False

        props = res.get("props") or []
        prod_maf = next((p for p in props if p["category"] == "most_aces_fav"), None)
        prod_ta = next((p for p in props if p["category"] == "total_aces"), None)
        prod_fav_a = next((p for p in props if p["category"] == "aces" and p["player"] == res["fav"]), None)
        prod_dog_a = next((p for p in props if p["category"] == "aces" and p["player"] == res["dog"]), None)

        ta_line = None
        prod_p_over = ""
        cand_p_over = ""
        if prod_ta is not None and prod_ta.get("line") is not None:
            ta_line = float(prod_ta["line"])
            prod_p_over = "%.4f" % prod_ta["p_over"]
            cand_p_over = "%.4f" % float(np.mean(cand["total_aces_samp"] > ta_line))

        match_id = res.get("match_id") or ""
        row = {
            "ts": _dt.now().isoformat(timespec="seconds"), "match_id": match_id,
            "match_date": res.get("date", ""), "fav": res["fav"], "dog": res["dog"],
            "tour": "wta" if wta else "atp", "surface": res.get("surface", ""), "best_of": res.get("best_of", ""),
            "prod_most_aces_fav_p": ("%.4f" % prod_maf["probability"]) if prod_maf else "",
            "cand_most_aces_fav_p": "%.4f" % cand["most_aces_fav_p"],
            "prod_total_aces_mean": ("%.3f" % prod_ta["mean"]) if prod_ta else "",
            "cand_total_aces_mean": "%.3f" % cand["total_aces_mean"],
            "total_aces_line": ("%.1f" % ta_line) if ta_line is not None else "",
            "prod_total_aces_line_p_over": prod_p_over, "cand_total_aces_line_p_over": cand_p_over,
            "prod_fav_aces_mean": ("%.3f" % prod_fav_a["mean"]) if prod_fav_a else "",
            "cand_fav_aces_mean": "%.3f" % cand["fav_aces_mean"],
            "prod_dog_aces_mean": ("%.3f" % prod_dog_a["mean"]) if prod_dog_a else "",
            "cand_dog_aces_mean": "%.3f" % cand["dog_aces_mean"],
            "actual_fav_aces": "", "actual_dog_aces": "", "actual_total_aces": "",
            "actual_most_aces_fav": "", "settled_ts": "",
            "sim_sha": res.get("sim_sha", ""), "v1_sha": res.get("v1_sha", ""),
        }

        with _LOCK:
            existing = set()
            if os.path.exists(_FWD_LOG):
                with open(_FWD_LOG, newline="") as fh:
                    for r in csv.DictReader(fh):
                        existing.add(r.get("match_id"))
            if match_id and match_id in existing:
                return False
            wh = not os.path.exists(_FWD_LOG)
            with open(_FWD_LOG, "a", newline="") as fh:
                w = csv.DictWriter(fh, fieldnames=_FIELDS)
                if wh:
                    w.writeheader()
                w.writerow(row)
        return True
    except Exception:
        return False


def _selftest():
    """Runs production evaluate_match() for a real known matchup, then the
    shadow candidate on top of it, and prints both side-by-side plus whether
    a log row would be written. Never writes to the real log path -- redirects
    to a temp file first. Prints MARKER and PASS/FAIL. Never raises."""
    import tempfile
    global _FWD_LOG
    orig_log = _FWD_LOG
    tmp = tempfile.NamedTemporaryFile(prefix="apex_dfwd_selftest_", suffix=".csv", delete=False)
    tmp.close()
    _FWD_LOG = tmp.name
    try:
        import apex_prop_engine as ape
        r = ape.evaluate_match("Jannik Sinner", "Alex Michelsen", 0.91, surface="Hard", bo5=True, wta=False)
        if not r or not r.get("ok"):
            print(MARKER, "SELFTEST FAIL -- evaluate_match:", (r or {}).get("error"))
            return
        ok = log_shadow_row(r, wta=False)
        prod_maf = next((p for p in r["props"] if p["category"] == "most_aces_fav"), None)
        cand = shadow_predict(r, wta=False)
        print(MARKER, "SELFTEST")
        print("  evaluate_match ok, sim_sha=%s" % r["sim_sha"][:12])
        print("  prod most_aces_fav_p=%.4f" % (prod_maf["probability"] if prod_maf else float("nan")))
        print("  cand most_aces_fav_p=%.4f" % (cand["most_aces_fav_p"] if cand else float("nan")))
        print("  log_shadow_row wrote row:", ok)
        with open(_FWD_LOG) as fh:
            print("  log file contents:\n" + fh.read())
        print(MARKER, "PASS")
    except Exception as e:
        print(MARKER, "SELFTEST FAIL:", type(e).__name__, e)
    finally:
        _FWD_LOG = orig_log
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv:
        _selftest()
    else:
        print(MARKER)
        print("Candidate: ATP dm=%.1f r=%s | WTA dm=%.1f r=%s" % (DM_ATP, R_ATP, DM_WTA, R_WTA))
        print("Log path:", _FWD_LOG)
        print("Run with --selftest to verify against a live matchup.")
