#!/usr/bin/env python3
"""
SPW% ECONOMIC IMPACT -- analysis over apex_spw_econ_rows.csv (real
2024+ market-priced matches, MODEL A = BASE vs MODEL B = BASE+SPW%
shrink, joined and simulated by apex_spw_econ_impact.py).
"""
import numpy as np
import pandas as pd

df = pd.read_csv("apex_spw_econ_rows.csv", low_memory=False)
print("rows:", len(df))

print("\n===== 0. ARCHITECTURAL CHECK: is match-winner probability pinned to market? =====")
d = (df["p_fav_A"] - df["p_fav_B"]).abs()
print("  |p_fav_A - p_fav_B|: max=%.6f mean=%.6f  (both vs real market pinn_fav, mean abs diff=%.6f / %.6f)" %
      (d.max(), d.mean(), (df["p_fav_A"] - df["pinn_fav"]).abs().mean(), (df["p_fav_B"] - df["pinn_fav"]).abs().mean()))

df["line"] = (df["tg_mean_A"] * 2).round() / 2.0   # Model-A-implied half-point Total Games line, frozen
df["over_A"] = df["tg_mean_A"] > df["line"]
df["over_B"] = df["tg_mean_B"] > df["line"]
df["real_over"] = df["real_total_games"] > df["line"]
df["decision_flip"] = df["over_A"] != df["over_B"]
df["err_A"] = (df["tg_mean_A"] - df["real_total_games"]).abs()
df["err_B"] = (df["tg_mean_B"] - df["real_total_games"]).abs()


print("\n===== 1. TOTAL-GAMES PROP: overall accuracy (MAE vs real total games) =====")
print("  MAE(A)=%.4f  MAE(B)=%.4f  delta=%.4f (positive = B better)" %
      (df["err_A"].mean(), df["err_B"].mean(), df["err_A"].mean() - df["err_B"].mean()))
print("  RMSE(A)=%.4f  RMSE(B)=%.4f" %
      ((df["err_A"]**2).mean()**0.5, (df["err_B"]**2).mean()**0.5))

print("\n===== 2. EDGE / DECISION ANALYSIS (Total Games O/U vs frozen Model-A line) =====")
n_flip = int(df["decision_flip"].sum())
print("  matches where the O/U decision changes between A and B: %d / %d (%.2f%%)" %
      (n_flip, len(df), 100 * n_flip / len(df)))
flips = df[df["decision_flip"]]
if n_flip:
    b_right = (flips["over_B"] == flips["real_over"]).sum()
    a_right = (flips["over_A"] == flips["real_over"]).sum()
    print("  on those %d flipped matches: A correct=%d (%.1f%%)  B correct=%d (%.1f%%)" %
          (n_flip, a_right, 100*a_right/n_flip, b_right, 100*b_right/n_flip))
print("  mean |tg_mean_B - tg_mean_A| (typical shift in the Total Games number): %.4f games" %
      (df["tg_mean_B"] - df["tg_mean_A"]).abs().mean())
print("  mean |dist_B - dist_A| (goes-the-distance probability shift): %.4f" %
      (df["dist_B"] - df["dist_A"]).abs().mean())
print("  mean |favgames_B - favgames_A| (favorite's games-won shift): %.4f games" %
      (df["favgames_B"] - df["favgames_A"]).abs().mean())

print("\n  distribution of the Total-Games shift (tg_mean_B - tg_mean_A):")
shift = df["tg_mean_B"] - df["tg_mean_A"]
for q in (0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99):
    print("    p%02d = %+.4f" % (int(q*100), shift.quantile(q)))


print("\n===== 3. CONFIDENCE BUCKETS (real market pinn_fav, 50-55/55-60/.../75+) =====")
bins = [0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 1.01]
labels = ["50-55", "55-60", "60-65", "65-70", "70-75", "75+"]
df["bucket"] = pd.cut(df["pinn_fav"], bins=bins, labels=labels, right=False)
print("%-8s %6s %10s %10s %10s %12s %12s %10s" %
      ("bucket", "n", "act_win%", "predA%", "predB%", "gapA", "gapB", "MAE_A/B(tg)"))
for lb in labels:
    g = df[df["bucket"] == lb]
    if len(g) == 0:
        continue
    actual = g["a_won"].where(g["a_is_fav"], 1 - g["a_won"]).mean()  # fav win rate
    predA, predB = g["p_fav_A"].mean(), g["p_fav_B"].mean()
    print("%-8s %6d %9.2f%% %9.2f%% %9.2f%% %+11.4f %+11.4f  %.3f/%.3f" %
          (lb, len(g), 100*actual, 100*predA, 100*predB, actual-predA, actual-predB,
           g["err_A"].mean(), g["err_B"].mean()))

print("\n  -> predA and predB are identical to solver precision in every bucket (see Section 0):")
print("     SPW% cannot move Apex's own match-winner/moneyline calibration, by architecture.")
print("     The MAE_A/B(tg) columns are where SPW% actually has room to matter (Total Games prop).")


print("\n===== 4. SEGMENT / ROBUSTNESS ANALYSIS =====")
def seg_report(mask, name):
    g = df[mask]
    if len(g) == 0:
        print("  %-14s n=0" % name); return
    n_flip_g = int(g["decision_flip"].sum())
    print("  %-14s n=%-6d MAE_A=%.4f MAE_B=%.4f dMAE=%+.4f  flips=%d (%.1f%%)" %
          (name, len(g), g["err_A"].mean(), g["err_B"].mean(),
           g["err_A"].mean() - g["err_B"].mean(), n_flip_g, 100*n_flip_g/len(g)))

seg_report(df["is_wta"] == 0, "ATP")
seg_report(df["is_wta"] == 1, "WTA")
for s in ("Hard", "Clay", "Grass"):
    seg_report(df["surface"] == s, s)
seg_report(df["a_is_fav"] & (df["a_won"] == 1) | (~df["a_is_fav"] & (df["a_won"] == 0)), "Favorite-won")
seg_report(df["pinn_fav"] >= 0.70, "High-confidence(>=70%)")
seg_report(df["pinn_fav"] < 0.60, "Low-confidence(<60%)")
seg_report(df["best_of"] == 5, "Best-of-5")
seg_report(df["best_of"] == 3, "Best-of-3")


print("\n===== 5. ERROR ANALYSIS: top-100 most improved vs most degraded (Total Games) =====")
df["improve"] = df["err_A"] - df["err_B"]   # positive = B improved on A
top_improved = df.nlargest(100, "improve")
top_degraded = df.nsmallest(100, "improve")

def composition(g, name):
    print("  %s (n=%d): ATP=%d WTA=%d | Hard=%d Clay=%d Grass=%d | mean pinn_fav=%.3f | mean|improve|=%.3f" %
          (name, len(g), (g["is_wta"] == 0).sum(), (g["is_wta"] == 1).sum(),
           (g["surface"] == "Hard").sum(), (g["surface"] == "Clay").sum(), (g["surface"] == "Grass").sum(),
           g["pinn_fav"].mean(), g["improve"].abs().mean()))

composition(top_improved, "TOP-100 MOST IMPROVED (B beats A)")
composition(top_degraded, "TOP-100 MOST DEGRADED (A beats B)")

print("\n===== 6. REDUNDANCY / INCREMENTAL CONTRIBUTION =====")
levelA_col = 0.5 * (df["hfA"] + df["hdA"])
levelB_col = 0.5 * (df["hfB"] + df["hdB"])
print("  corr(levelA, levelB) on this real 2024+ sample: %.4f" % np.corrcoef(levelA_col, levelB_col)[0, 1])
print("  (Tier-3 investigation already quantified: corr(trailing SPW%%-shrink, trailing hold_rate) = 0.965 --")
print("   most of SPW%%'s contribution is redundant with hold_rate already in Model A; this run measures")
print("   what the small non-redundant remainder is actually worth on real, market-priced holdout matches.)")
