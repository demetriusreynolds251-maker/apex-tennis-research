#!/usr/bin/env python3
"""APEX-FSG-STUDY-2026-09-04 -- READ-ONLY first-set research study.
Writes NOTHING except /tmp/apex_fsg_study_report.txt. Never imports frozen models.
Step 1: --inventory  find + classify data files, report first-set usability."""
import csv, glob, os, re, sys, collections

SEARCH = [os.path.expanduser(p) for p in (
    "~/openclaw/data", "~/openclaw", "~/Desktop", "~/Downloads", "~/Documents")]
EXTRA = [a for a in sys.argv[2:] if os.path.isdir(os.path.expanduser(a))]
REPORT = "/tmp/apex_fsg_study_report.txt"

def find_csvs():
    seen, out = set(), []
    for root in SEARCH + EXTRA:
        for p in glob.glob(os.path.join(root, "**", "*.csv"), recursive=True):
            rp = os.path.realpath(p)
            if rp in seen or "/venv/" in rp or "/node_modules/" in rp: continue
            seen.add(rp); out.append(rp)
    return out

def header(p):
    try:
        with open(p, newline="", encoding="utf-8", errors="replace") as f:
            return [h.strip() for h in next(csv.reader(f))]
    except Exception:
        return []

def classify(h):
    s = set(h)
    if {"score", "w_ace", "winner_name"} <= s: return "sackmann_match"
    if ("PSW" in s or "B365W" in s) and "W1" in s and "L1" in s: return "tennisdata"
    if "P1Ace" in s or "PointServer" in s or "PointNumber" in s: return "pbp"
    if "match_id" in s and "Pt" in s and "Svr" in s: return "mcp_points"
    return None

SETRE = re.compile(r"^(\d+)-(\d+)(?:\((\d+)\))?")
def first_set(score):
    """Sackmann score string -> (winner_games, loser_games, tiebreak) or None."""
    m = SETRE.match(str(score or "").strip())
    if not m: return None
    a, b = int(m.group(1)), int(m.group(2))
    if max(a, b) < 6 or max(a, b) > 7: return None      # retirement / junk
    return a, b, (max(a, b) == 7 and min(a, b) == 6)

def scan_sackmann(p):
    n = fs = odds = 0; yrs = collections.Counter()
    with open(p, newline="", encoding="utf-8", errors="replace") as f:
        for r in csv.DictReader(f):
            n += 1
            if first_set(r.get("score")): fs += 1
            yrs[str(r.get("tourney_date", ""))[:4]] += 1
    return n, fs, yrs

def scan_tennisdata(p):
    n = fs = odds = 0
    with open(p, newline="", encoding="utf-8", errors="replace") as f:
        for r in csv.DictReader(f):
            n += 1
            try:
                w1, l1 = int(float(r.get("W1") or "")), int(float(r.get("L1") or ""))
                if 6 <= max(w1, l1) <= 7: fs += 1
            except ValueError: pass
            if r.get("PSW") or r.get("B365W"): odds += 1
    return n, fs, odds

def inventory():
    lines = ["APEX FIRST-SET STUDY -- DATA INVENTORY (read-only)", ""]
    tot = collections.Counter()
    for p in find_csvs():
        k = classify(header(p))
        if not k: continue
        if k == "sackmann_match":
            n, fs, yrs = scan_sackmann(p)
            tour = "wta" if "wta" in os.path.basename(p).lower() else "atp"
            tot["sack_" + tour] += n; tot["sack_fs_" + tour] += fs
            lines.append(f"[sackmann {tour}] {p}  rows={n} first_set_ok={fs}  years={min(yrs)}-{max(yrs)}")
        elif k == "tennisdata":
            n, fs, odds = scan_tennisdata(p)
            tot["td"] += n; tot["td_fs"] += fs; tot["td_odds"] += odds
            lines.append(f"[tennisdata] {p}  rows={n} first_set_ok={fs} odds={odds}")
        else:
            tot[k] += 1
            lines.append(f"[{k}] {p}")
    lines += ["", "TOTALS",
              f"  Sackmann ATP rows {tot['sack_atp']} (first set parseable {tot['sack_fs_atp']})",
              f"  Sackmann WTA rows {tot['sack_wta']} (first set parseable {tot['sack_fs_wta']})",
              f"  tennis-data rows {tot['td']} (first set {tot['td_fs']}, with odds {tot['td_odds']})",
              f"  Slam point-by-point files {tot['pbp']}   Match Charting point files {tot['mcp_points']}",
              "",
              "READ: tennis-data rows WITH odds AND first set = backtestable with a real price.",
              "      Sackmann rows = rates layer + more first-set outcomes (no price).",
              "      pbp/mcp files = only source for first-set ACES."]
    out = "\n".join(lines)
    print(out)
    open(REPORT, "w").write(out)


# ============ PHASE 3: first-set study on tennis-data odds files ============
import math, collections
import numpy as np
ODDS_DIR = os.path.expanduser("~/openclaw/odds")

def _logit(p): return math.log(p / (1 - p))

def load_rows():
    import pandas as pd
    fr = []
    for p in sorted(glob.glob(os.path.join(ODDS_DIR, "*.xls*"))):
        try:
            d = pd.read_excel(p)
        except Exception as e:
            print("  skip", os.path.basename(p), "->", e); continue
        d["wta"] = int("wta" in os.path.basename(p).lower())
        fr.append(d)
    d = pd.concat(fr, ignore_index=True)
    for c in ("W1", "L1", "PSW", "PSL", "B365W", "B365L", "Best of"):
        d[c] = pd.to_numeric(d.get(c), errors="coerce")
    d["Date"] = pd.to_datetime(d["Date"], errors="coerce")
    d["ow"] = d["PSW"].fillna(d["B365W"]); d["ol"] = d["PSL"].fillna(d["B365L"])
    d["src"] = np.where(d["PSW"].notna(), "pinn", np.where(d["B365W"].notna(), "b365", ""))
    ok = (d["W1"].notna() & d["L1"].notna() & d[["W1", "L1"]].max(axis=1).between(6, 7)
          & d["ow"].gt(1) & d["ol"].gt(1) & d["Date"].notna())
    d = d[ok].copy()
    pw = (1 / d["ow"]) / ((1 / d["ow"]) + (1 / d["ol"]))          # de-vigged P(winner)
    d["fav_is_w"] = pw >= 0.5
    d["pinn_fav"] = np.where(d["fav_is_w"], pw, 1 - pw).clip(0.5, 0.99)
    d["fav"] = np.where(d["fav_is_w"], d["Winner"], d["Loser"])
    d["dog"] = np.where(d["fav_is_w"], d["Loser"], d["Winner"])
    d["fs_fav"] = np.where(d["fav_is_w"], d["W1"], d["L1"]).astype(int)
    d["fs_dog"] = np.where(d["fav_is_w"], d["L1"], d["W1"]).astype(int)
    d["fs_total"] = d["fs_fav"] + d["fs_dog"]
    d["fs_fav_won"] = (d["fs_fav"] > d["fs_dog"]).astype(int)
    d["bo5"] = (d["Best of"] == 5).astype(int)
    d["lp"] = d["pinn_fav"].map(_logit); d["lp2"] = d["lp"] ** 2
    d["year"] = d["Date"].dt.year
    return d.sort_values("Date").reset_index(drop=True)

def add_rolling(d, k=15, win=40):
    """Player first-set tendency: games won / lost per set, last `win` sets,
    shrunk to the global mean with weight k. Computed in date order -> no leakage."""
    mu = d["fs_total"].mean() / 2.0
    hist = collections.defaultdict(lambda: collections.deque(maxlen=win))
    cols = {c: [] for c in ("fav_gw", "fav_gl", "dog_gw", "dog_gl")}
    for r in d.itertuples(index=False):
        for who, name in (("fav", r.fav), ("dog", r.dog)):
            h = hist[name]; n = len(h)
            cols[who + "_gw"].append((sum(x[0] for x in h) + k * mu) / (n + k))
            cols[who + "_gl"].append((sum(x[1] for x in h) + k * mu) / (n + k))
        hist[r.fav].append((r.fs_fav, r.fs_dog)); hist[r.dog].append((r.fs_dog, r.fs_fav))
    for c, v in cols.items(): d[c] = v
    return d

BASE = ["lp", "lp2", "bo5", "wta"]
RATE = BASE + ["fav_gw", "fav_gl", "dog_gw", "dog_gl"]
def _X(d, feats): return np.column_stack([np.ones(len(d))] + [d[f].values.astype(float) for f in feats])
def _ols(X, y): return np.linalg.lstsq(X, y, rcond=None)[0]
def _logit_fit(X, y, it=25):
    b = np.zeros(X.shape[1])
    for _ in range(it):
        p = 1 / (1 + np.exp(-X @ b)); W = p * (1 - p) + 1e-9
        b += np.linalg.solve((X.T * W) @ X + 1e-6 * np.eye(X.shape[1]), X.T @ (y - p))
    return b

def study_target(d, target, label):
    fit, tune, hold = d[d.year <= 2021], d[d.year.between(2022, 2023)], d[d.year >= 2024]
    y = hold[target].values
    bb = _ols(_X(fit, BASE), fit[target].values); br = _ols(_X(fit, RATE), fit[target].values)
    pb, pr = _X(hold, BASE) @ bb, _X(hold, RATE) @ br
    mae_n, mae_b, mae_r = (np.abs(y - fit[target].mean()).mean(), np.abs(y - pb).mean(), np.abs(y - pr).mean())
    out = [f"--- {label}: fit {len(fit)} / tune {len(tune)} / holdout {len(hold)}",
           f"MAE naive {mae_n:.3f} | price-only {mae_b:.3f} | +player-layer {mae_r:.3f} "
           f"| player-layer gain vs price {100 * (mae_b - mae_r) / mae_b:+.1f}%  (V1 aces ref: ~22%)",
           f"independence corr(price-only, +player-layer) = {np.corrcoef(pb, pr)[0, 1]:.3f}  "
           f"(V1 ref: total_games 0.994 mirror, dfs 0.724, breaks 0.526)"]
    res = tune[target].values - _X(tune, RATE) @ br           # residual dist from tune years
    line = np.floor(pb) + 0.5                                   # synthetic line at price-only median
    p_over = np.array([(pi + res > l).mean() for pi, l in zip(pr, line)])
    over = (y > line).astype(float)
    conf = np.where(p_over >= 0.5, p_over, 1 - p_over); hit = np.where(p_over >= 0.5, over, 1 - over)
    for lo, hi in ((0.5, 0.55), (0.55, 0.6), (0.6, 0.65), (0.65, 0.7), (0.7, 1.01)):
        m = (conf >= lo) & (conf < hi)
        if m.sum(): out.append(f"  band {lo:.2f}-{hi:.2f}: n={m.sum():5d} predicted {conf[m].mean():.3f} actual {hit[m].mean():.3f}")
    m = conf >= 0.55
    out.append(f"PROXY EDGE (line = price-only median; take model side when conf>=0.55): "
               f"n={m.sum()} hit {(hit[m].mean() if m.sum() else float('nan')):.3f}  [6-flex BE 0.542]")
    return out

def study_winner(d):
    fit, hold = d[d.year <= 2021], d[d.year >= 2024]
    y = hold.fs_fav_won.values
    fb, fr = ["lp", "bo5", "wta"], ["lp", "bo5", "wta", "fav_gw", "fav_gl", "dog_gw", "dog_gl"]
    pb = 1 / (1 + np.exp(-_X(hold, fb) @ _logit_fit(_X(fit, fb), fit.fs_fav_won.values)))
    pr = 1 / (1 + np.exp(-_X(hold, fr) @ _logit_fit(_X(fit, fr), fit.fs_fav_won.values)))
    ll = lambda p: -np.mean(y * np.log(p) + (1 - y) * np.log(1 - p))
    return [f"--- 1st Set Winner: fit {len(fit)} / holdout {len(hold)}",
            f"log-loss price-only {ll(pb):.4f} | +player-layer {ll(pr):.4f} | corr {np.corrcoef(pb, pr)[0, 1]:.3f}",
            f"fav wins set 1 actual {y.mean():.3f} vs price-only mean {pb.mean():.3f}"]

def study():
    d = add_rolling(load_rows())
    L = ["APEX FIRST-SET STUDY -- PHASE 3 (read-only; tennis-data odds files, real Pinnacle price)",
         f"rows {len(d)} | years {d.year.min()}-{d.year.max()} | pinnacle-priced {(d.src == 'pinn').sum()} "
         f"| b365-only {(d.src == 'b365').sum()} | wta {int(d.wta.sum())} | bo5 {int(d.bo5.sum())}",
         "split: fit <=2021 / tune 2022-23 / holdout 2024+ (same as V1)", ""]
    L += study_target(d, "fs_total", "1st Set Total Games") + [""]
    L += study_target(d, "fs_fav", "1st Set Games Won (favorite)") + [""]
    L += study_target(d, "fs_dog", "1st Set Games Won (underdog)") + [""]
    L += study_winner(d)
    L += ["", "NOT TESTED: 1st Set Aces -- no point-by-point data on the Mini (mcp/ is aggregate stats only)."]
    out = "\n".join(L); print(out)
    open(REPORT, "w").write(out)


V1R  = ["fav_hold", "fav_break", "dog_hold", "dog_break"]
TEND = ["fav_gw", "fav_gl", "dog_gw", "dog_gl"]
SETS = {"price-only": BASE, "+tendency": BASE + TEND, "+V1 rates": BASE + V1R, "+both": BASE + TEND + V1R}
GATE = "PASS needs: gain >=10% AND corr <=0.90 AND bands within +/-0.05"

def compare_target(d, target, label):
    fit, tune, hold = d[d.year <= 2021], d[d.year.between(2022, 2023)], d[d.year >= 2024]
    y = hold[target].values
    out = [f"--- {label}: fit {len(fit)} / tune {len(tune)} / holdout {len(hold)}   naive MAE {np.abs(y - fit[target].mean()).mean():.3f}"]
    pb = _X(hold, BASE) @ _ols(_X(fit, BASE), fit[target].values)
    resb = tune[target].values - _X(tune, BASE) @ _ols(_X(fit, BASE), fit[target].values)
    line = np.round(pb + np.median(resb) - 0.5) + 0.5          # where price-only is ~50/50
    over = (y > line).astype(float); mae_b = np.abs(y - pb).mean()
    out.append(f"{'layer':12s} {'MAE':>6s} {'gain':>7s} {'corr':>6s} {'maxband':>8s} {'proxy n':>8s} {'hit':>6s}  verdict")
    for name, feats in SETS.items():
        beta = _ols(_X(fit, feats), fit[target].values); pr = _X(hold, feats) @ beta
        mae = np.abs(y - pr).mean(); gain = 100 * (mae_b - mae) / mae_b
        corr = np.corrcoef(pb, pr)[0, 1] if name != "price-only" else 1.0
        res = tune[target].values - _X(tune, feats) @ beta
        p_over = np.array([(pi + res > l).mean() for pi, l in zip(pr, line)])
        conf = np.where(p_over >= 0.5, p_over, 1 - p_over); hit = np.where(p_over >= 0.5, over, 1 - over)
        worst = 0.0
        for lo, hi in ((0.5, 0.55), (0.55, 0.6), (0.6, 0.65), (0.65, 0.7), (0.7, 1.01)):
            m = (conf >= lo) & (conf < hi)
            if m.sum() >= 100: worst = max(worst, abs(conf[m].mean() - hit[m].mean()))
        m = conf >= 0.55; h = hit[m].mean() if m.sum() else float("nan")
        v = "PASS" if (gain >= 10 and corr <= 0.90 and worst <= 0.05) else "fail"
        out.append(f"{name:12s} {mae:6.3f} {gain:+6.1f}% {corr:6.3f} {worst:8.3f} {m.sum():8d} {h:6.3f}  {v}")
    return out

def compare_winner(d):
    fit, hold = d[d.year <= 2021], d[d.year >= 2024]; y = hold.fs_fav_won.values
    ll = lambda p: -np.mean(y * np.log(p) + (1 - y) * np.log(1 - p))
    fb = ["lp", "bo5", "wta"]
    pb = 1 / (1 + np.exp(-_X(hold, fb) @ _logit_fit(_X(fit, fb), fit.fs_fav_won.values)))
    out = [f"--- 1st Set Winner: fit {len(fit)} / holdout {len(hold)}  (fav wins set 1 actual {y.mean():.3f})",
           f"{'layer':12s} {'logloss':>8s} {'corr':>6s}"]
    for name, extra in (("price-only", []), ("+tendency", TEND), ("+V1 rates", V1R), ("+both", TEND + V1R)):
        f = fb + extra
        pr = 1 / (1 + np.exp(-_X(hold, f) @ _logit_fit(_X(fit, f), fit.fs_fav_won.values)))
        out.append(f"{name:12s} {ll(pr):8.4f} {np.corrcoef(pb, pr)[0, 1]:6.3f}")
    return out

def study_v1():
    d = add_rolling(load_rows_v1())
    L = ["APEX FIRST-SET STUDY -- PHASE 3b: V1 hold/break rate layer (read-only)",
         f"rows {len(d)} | years {d.year.min()}-{d.year.max()} | wta {int(d.wta.sum())} | bo5 {int(d.bo5.sum())} "
         f"| median surface-history n: fav {int(d.fav_n.median())} dog {int(d.dog_n.median())}",
         "price = Pinnacle via apex_batch_a_rows; first set + service stats = Sackmann; exact-key join",
         f"split fit<=2021 / tune 22-23 / holdout 2024+.  {GATE}", ""]
    for t, lab in (("fs_total", "1st Set Total Games"), ("fs_fav", "1st Set Games Won (favorite)"), ("fs_dog", "1st Set Games Won (underdog)")):
        L += compare_target(d, t, lab) + [""]
    L += compare_winner(d)
    out = "\n".join(L); print(out); open(REPORT.replace(".txt", "_v1rates.txt"), "w").write(out)



# ============ PHASE 3b: same study with V1's hold/break rate layer ============
SACK_DIR = os.path.expanduser("~/openclaw/ATP & WTA, 1968-2026")
BATCH = "apex_batch_a_rows.csv"
WIN, K = 40, 15                       # V1 chosen window / shrink

def sack_files():
    out = []
    for p in glob.glob(os.path.join(SACK_DIR, "**", "*.csv"), recursive=True):
        b = os.path.basename(p).lower()
        if "backup" in p.lower() or "amateur" in b: continue
        m = re.match(r"^((?:19|20)\d\d)(_wta|_challenger|_atp_quali)?\.csv$", b)
        if (m and int(m.group(1)) >= 2005) or "ongoing" in b: out.append(p)
    return sorted(out)

def _sums(h):
    return len(h), sum(x[0] for x in h), sum(x[1] for x in h), sum(x[2] for x in h), sum(x[3] for x in h)

def v1_rates(hist, surface):
    """V1 rate_bundle logic: surface window rate shrunk toward all-surface rate, k=K."""
    ns, hs, gs, bs, os_ = _sums(hist[surface]); na, ha, ga, ba, oa = _sums(hist["All"])
    def rate(num_s, den_s, num_a, den_a, prior):
        ra = num_a / den_a if den_a > 0 else prior
        rs = num_s / den_s if den_s > 0 else ra
        return (ns * rs + K * ra) / (ns + K)
    return rate(hs, gs, ha, ga, 0.78), rate(bs, os_, ba, oa, 0.22)

def nsets(score):
    """Count completed sets in a Sackmann score string; None on retirement/walkover."""
    sc = str(score or "")
    if "RET" in sc or "W/O" in sc or "DEF" in sc or "ABN" in sc: return None
    return len(re.findall(r"\d+-\d+", sc)) or None

def load_rows_v1():
    import pandas as pd
    b = pd.read_csv(BATCH, low_memory=False)
    pcol = [c for c in b.columns if c.lower().startswith("pinn")][0]
    price = {}
    for r in b.itertuples(index=False):
        t, a, p2, pa = str(r.tourney_id), str(r.player_a), str(r.player_b), getattr(r, pcol)
        price[(t, a, p2)] = pa; price[(t, p2, a)] = 1 - pa
    need = ["tourney_id", "tourney_date", "match_num", "winner_name", "loser_name", "score", "surface",
            "best_of", "w_SvGms", "w_bpFaced", "w_bpSaved", "l_SvGms", "l_bpFaced", "l_bpSaved"]
    fr = []
    for p in sack_files():
        try:
            d = pd.read_csv(p, low_memory=False, usecols=lambda c: c in need)
        except Exception as e:
            print("  skip", os.path.basename(p), "->", e); continue
        d["wta"] = int("wta" in os.path.basename(p).lower()); fr.append(d)
    d = pd.concat(fr, ignore_index=True)
    for c in ("w_SvGms", "w_bpFaced", "w_bpSaved", "l_SvGms", "l_bpFaced", "l_bpSaved", "best_of", "match_num"):
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d = d.drop_duplicates(["tourney_id", "winner_name", "loser_name"])
    d["tourney_date"] = pd.to_numeric(d["tourney_date"], errors="coerce")
    d = d.dropna(subset=["tourney_date"]).sort_values(["tourney_date", "tourney_id", "match_num"])
    hist = collections.defaultdict(lambda: collections.defaultdict(lambda: collections.deque(maxlen=WIN)))
    rows = []
    for r in d.itertuples(index=False):
        surf = str(r.surface or "Hard")
        stats_ok = all(np.isfinite([r.w_SvGms, r.w_bpFaced, r.w_bpSaved, r.l_SvGms, r.l_bpFaced, r.l_bpSaved])) \
                   and r.w_SvGms > 0 and r.l_SvGms > 0
        key = (str(r.tourney_id), r.winner_name, r.loser_name)
        fs = first_set(r.score)
        if key in price and fs and np.isfinite(price[key]):
            pw = float(price[key]); fav_is_w = pw >= 0.5
            fav, dog = (r.winner_name, r.loser_name) if fav_is_w else (r.loser_name, r.winner_name)
            fh, fb = v1_rates(hist[fav], surf); dh, db = v1_rates(hist[dog], surf)
            rows.append({"Date": r.tourney_date, "fav": fav, "dog": dog, "pinn_fav": max(pw, 1 - pw),
                         "fs_fav": fs[0] if fav_is_w else fs[1], "fs_dog": fs[1] if fav_is_w else fs[0],
                         "bo5": int(r.best_of == 5), "wta": r.wta, "surface": surf,
                         "fav_hold": fh, "fav_break": fb, "dog_hold": dh, "dog_break": db,
                         "fav_n": len(hist[fav][surf]), "dog_n": len(hist[dog][surf]),
                         "nsets": nsets(r.score)})
        if stats_ok:
            w = (r.w_SvGms - (r.w_bpFaced - r.w_bpSaved), r.w_SvGms, r.l_bpFaced - r.l_bpSaved, r.l_SvGms)
            l = (r.l_SvGms - (r.l_bpFaced - r.l_bpSaved), r.l_SvGms, r.w_bpFaced - r.w_bpSaved, r.w_SvGms)
            for name, rec in ((r.winner_name, w), (r.loser_name, l)):
                hist[name][surf].append(rec); hist[name]["All"].append(rec)
    d = pd.DataFrame(rows)
    d["pinn_fav"] = d["pinn_fav"].clip(0.5, 0.99)
    d["fs_total"] = d.fs_fav + d.fs_dog; d["fs_fav_won"] = (d.fs_fav > d.fs_dog).astype(int)
    d["lp"] = d.pinn_fav.map(_logit); d["lp2"] = d.lp ** 2
    d["year"] = (d.Date // 10000).astype(int)
    return d.sort_values("Date").reset_index(drop=True)


def _bin_study(d, y, label, fb):
    fit, hold = d[d.year <= 2021], d[d.year >= 2024]
    yf, yh = fit[y].values, hold[y].values
    ll = lambda p: -np.mean(yh * np.log(p) + (1 - yh) * np.log(1 - p))
    out = [f"--- {label}: fit {len(fit)} / holdout {len(hold)}  base rate {yh.mean():.3f}",
           f"{'layer':12s} {'logloss':>8s} {'gain':>7s} {'corr':>6s} {'maxband':>8s} {'proj~act':>9s}"]
    pb = None; llb = None
    for name, extra in (("price-only", []), ("+tendency", TEND), ("+V1 rates", V1R), ("+both", TEND + V1R)):
        f = fb + extra
        pr = 1 / (1 + np.exp(-_X(hold, f) @ _logit_fit(_X(fit, f), yf)))
        if pb is None: pb, llb = pr, ll(pr)
        worst = 0.0
        for lo, hi in ((0.2, 0.3), (0.3, 0.4), (0.4, 0.5), (0.5, 0.6), (0.6, 0.7), (0.7, 0.8)):
            m = (pr >= lo) & (pr < hi)
            if m.sum() >= 100: worst = max(worst, abs(pr[m].mean() - yh[m].mean()))
        out.append(f"{name:12s} {ll(pr):8.4f} {100*(llb-ll(pr))/llb:+6.2f}% {np.corrcoef(pb, pr)[0,1]:6.3f} {worst:8.3f} {np.corrcoef(pr, yh)[0,1]:9.3f}")
    return out, pb

def study_sets():
    d = add_rolling(load_rows_v1()); d = d[d.nsets.notna()].copy()
    d["sum_hold"] = d.fav_hold + d.dog_hold; d["sum_break"] = d.fav_break + d.dog_break
    b3, b5 = d[d.bo5 == 0].copy(), d[d.bo5 == 1].copy()
    b3["goes3"] = (b3.nsets >= 3).astype(int); b5["goes4"] = (b5.nsets >= 4).astype(int); b5["goes5"] = (b5.nsets == 5).astype(int)
    L = ["APEX TOTAL SETS STUDY (read-only; Pinnacle price via batch rows, sets from Sackmann, V1 rates)",
         f"rows {len(d)} | bo3 {len(b3)} | bo5 {len(b5)} | years {d.year.min()}-{d.year.max()}", ""]
    fb = ["lp", "lp2", "wta"]
    o, pb = _bin_study(b3, "goes3", "Bo3 -- P(goes 3 sets)  [line 2.5, MORE = 3 sets]", fb); L += o + [""]
    hold = b3[b3.year >= 2024]
    L.append(f"Bo3 serve-dominance check: corr(sum_hold, goes3) = {np.corrcoef(hold.sum_hold, hold.goes3)[0,1]:+.3f}; "
             f"corr(sum_hold, price-only P(goes3)) = {np.corrcoef(hold.sum_hold, pb)[0,1]:+.3f}")
    L.append("")
    o, _ = _bin_study(b5, "goes4", "Bo5 -- P(4+ sets)  [line 3.5]", fb); L += o + [""]
    o, _ = _bin_study(b5, "goes5", "Bo5 -- P(5 sets)   [line 4.5]", fb); L += o + [""]
    L += ["DEMON BREAK-EVEN (per leg, all legs equal): required p = M^(-1/n) for an n-leg slip paying M x",
          f"{'slip':>10s} " + " ".join(f"{m:>6}x" for m in (3, 6, 10, 25, 37.5, 50, 100))]
    for n in (2, 3, 4, 5, 6):
        L.append(f"{n:>9d}-leg " + " ".join(f"{m ** (-1 / n):7.3f}" for m in (3, 6, 10, 25, 37.5, 50, 100)))
    L.append("Read: a demon is playable when the model's P(MORE) exceeds the required p for the slip multiplier it produces.")
    out = "\n".join(L); print(out); open(REPORT.replace(".txt", "_sets.txt"), "w").write(out)


# ============ SCORECARD: every live category, same price / rates / split ============
def _games(score):
    g = re.findall(r"(\d+)-(\d+)", str(score or ""))
    if not g or "RET" in str(score) or "W/O" in str(score): return None
    return sum(int(a) for a, _ in g), sum(int(b) for _, b in g)

def v1_bundle(hist, surf):
    """(hold, break, ace_rate, df_rate, spg) with V1 surface->all shrink."""
    def sums(h): return len(h), [sum(x[i] for x in h) for i in range(8)]
    ns, S = sums(hist[surf]); na, A = sums(hist["All"])
    def rate(i, j, prior):
        ra = A[i] / A[j] if A[j] > 0 else prior
        rs = S[i] / S[j] if S[j] > 0 else ra
        return (ns * rs + K * ra) / (ns + K)
    # rec = (holds, svgms, breaks, opp_svgms, aces, dfs, svpt, 1)
    return rate(0, 1, 0.78), rate(2, 3, 0.22), rate(4, 6, 0.07), rate(5, 6, 0.04), rate(6, 1, 6.5)

def load_rows_full():
    import pandas as pd
    b = pd.read_csv(BATCH, low_memory=False)
    pcol = [c for c in b.columns if c.lower().startswith("pinn")][0]
    price = {}
    for r in b.itertuples(index=False):
        t, a, p2, pa = str(r.tourney_id), str(r.player_a), str(r.player_b), getattr(r, pcol)
        price[(t, a, p2)] = pa; price[(t, p2, a)] = 1 - pa
    need = ["tourney_id", "tourney_date", "match_num", "winner_name", "loser_name", "score", "surface", "best_of",
            "w_ace", "w_df", "w_svpt", "w_SvGms", "w_bpFaced", "w_bpSaved", "l_ace", "l_df", "l_svpt", "l_SvGms", "l_bpFaced", "l_bpSaved"]
    fr = []
    for p in sack_files():
        try: d = pd.read_csv(p, low_memory=False, usecols=lambda c: c in need)
        except Exception: continue
        d["wta"] = int("wta" in os.path.basename(p).lower()); fr.append(d)
    d = pd.concat(fr, ignore_index=True)
    for c in need[7:] + ["match_num"]: d[c] = pd.to_numeric(d[c], errors="coerce")
    d = d.drop_duplicates(["tourney_id", "winner_name", "loser_name"])
    d["tourney_date"] = pd.to_numeric(d["tourney_date"], errors="coerce")
    d = d.dropna(subset=["tourney_date"]).sort_values(["tourney_date", "tourney_id", "match_num"])
    hist = collections.defaultdict(lambda: collections.defaultdict(lambda: collections.deque(maxlen=WIN)))
    rows = []
    for r in d.itertuples(index=False):
        surf = str(r.surface or "Hard")
        st = [r.w_ace, r.w_df, r.w_svpt, r.w_SvGms, r.w_bpFaced, r.w_bpSaved, r.l_ace, r.l_df, r.l_svpt, r.l_SvGms, r.l_bpFaced, r.l_bpSaved]
        ok = all(np.isfinite(st)) and r.w_svpt > 0 and r.l_svpt > 0 and r.w_SvGms > 0 and r.l_SvGms > 0
        key = (str(r.tourney_id), r.winner_name, r.loser_name); g = _games(r.score)
        if ok and g and key in price and np.isfinite(price[key]):
            pw = float(price[key]); fw = pw >= 0.5
            W = {"aces": r.w_ace, "dfs": r.w_df, "breaks": r.l_bpFaced - r.l_bpSaved, "games": g[0]}
            L_ = {"aces": r.l_ace, "dfs": r.l_df, "breaks": r.w_bpFaced - r.w_bpSaved, "games": g[1]}
            F, D = (W, L_) if fw else (L_, W)
            fav, dog = (r.winner_name, r.loser_name) if fw else (r.loser_name, r.winner_name)
            fb_, db_ = v1_bundle(hist[fav], surf), v1_bundle(hist[dog], surf)
            row = {"Date": r.tourney_date, "pinn_fav": max(pw, 1 - pw), "bo5": int(r.best_of == 5), "wta": r.wta,
                   "total_games": g[0] + g[1]}
            for k_, v in F.items(): row["fav_" + k_] = v
            for k_, v in D.items(): row["dog_" + k_] = v
            for i, nm in enumerate(("hold", "break", "ace_rate", "df_rate", "spg")):
                row["fav_" + nm] = fb_[i]; row["dog_" + nm] = db_[i]
            rows.append(row)
        if ok:
            w = (r.w_SvGms - (r.w_bpFaced - r.w_bpSaved), r.w_SvGms, r.l_bpFaced - r.l_bpSaved, r.l_SvGms, r.w_ace, r.w_df, r.w_svpt, 1)
            l = (r.l_SvGms - (r.l_bpFaced - r.l_bpSaved), r.l_SvGms, r.w_bpFaced - r.w_bpSaved, r.w_SvGms, r.l_ace, r.l_df, r.l_svpt, 1)
            for name, rec in ((r.winner_name, w), (r.loser_name, l)):
                hist[name][surf].append(rec); hist[name]["All"].append(rec)
    d = pd.DataFrame(rows)
    d["pinn_fav"] = d.pinn_fav.clip(0.5, 0.99); d["lp"] = d.pinn_fav.map(_logit); d["lp2"] = d.lp ** 2
    d["year"] = (d.Date // 10000).astype(int)
    return d.sort_values("Date").reset_index(drop=True)

RATES_ALL = [s + "_" + n for s in ("fav", "dog") for n in ("hold", "break", "ace_rate", "df_rate", "spg")]

def score_target(d, target, label):
    fit, tune, hold = d[d.year <= 2021], d[d.year.between(2022, 2023)], d[d.year >= 2024]
    y = hold[target].values
    bb = _ols(_X(fit, BASE), fit[target].values); br = _ols(_X(fit, RATES_ALL + BASE), fit[target].values)
    pb, pr = _X(hold, BASE) @ bb, _X(hold, RATES_ALL + BASE) @ br
    mae_b, mae_r = np.abs(y - pb).mean(), np.abs(y - pr).mean()
    res = tune[target].values - _X(tune, RATES_ALL + BASE) @ br
    line = np.round(pb + np.median(tune[target].values - _X(tune, BASE) @ bb) - 0.5) + 0.5
    p_over = np.array([(pi + res > l).mean() for pi, l in zip(pr, line)]); over = (y > line).astype(float)
    conf = np.where(p_over >= 0.5, p_over, 1 - p_over); hit = np.where(p_over >= 0.5, over, 1 - over)
    worst = 0.0
    for lo, hi in ((0.5, 0.55), (0.55, 0.6), (0.6, 0.65), (0.65, 0.7), (0.7, 1.01)):
        m = (conf >= lo) & (conf < hi)
        if m.sum() >= 100: worst = max(worst, abs(conf[m].mean() - hit[m].mean()))
    return (f"{label:22s} {len(hold):6d} {mae_b:7.3f} {mae_r:7.3f} {100*(mae_b-mae_r)/mae_b:+7.1f}% "
            f"{np.corrcoef(pb, pr)[0,1]:6.3f} {np.corrcoef(pr, y)[0,1]:7.3f} {np.corrcoef(pb, y)[0,1]:7.3f} {worst:7.3f}")

def scorecard():
    d = load_rows_full()
    L = ["APEX CATEGORY SCORECARD -- historical, same price / V1 rates / split for every category (read-only)",
         f"rows {len(d)} | years {d.year.min()}-{d.year.max()} | wta {int(d.wta.sum())} | bo5 {int(d.bo5.sum())}",
         "gain = MAE improvement of +V1 rates over price-only | indep = corr(price-only, +rates) | r_act = corr(proj, actual)", "",
         f"{'category':22s} {'n_hold':>6s} {'MAE_px':>7s} {'MAE_r':>7s} {'gain':>8s} {'indep':>6s} {'r_act_r':>7s} {'r_act_px':>7s} {'maxband':>7s}"]
    for t, lab in (("fav_aces", "Aces (fav)"), ("dog_aces", "Aces (dog)"), ("fav_dfs", "DFs (fav)"), ("dog_dfs", "DFs (dog)"),
                   ("fav_breaks", "Breaks (fav)"), ("dog_breaks", "Breaks (dog)"), ("fav_games", "Games won (fav)"),
                   ("dog_games", "Games won (dog)"), ("total_games", "Total games")):
        L.append(score_target(d, t, lab))
    out = "\n".join(L); print(out); open(REPORT.replace(".txt", "_scorecard.txt"), "w").write(out)


# ============ OPPONENT RETURN STUDY (read-only) ============
# Does knowing the RETURNER improve the ace projection? Same price/rates/split as the scorecard.
# rec = (holds, svgms, breaks, opp_svgms, aces, dfs, svpt, 1, ret_pts_won, ret_pts)
def v1_bundle2(hist, surf):
    def sums(h): return len(h), [sum(x[i] for x in h) for i in range(10)]
    ns, S = sums(hist[surf]); na, A = sums(hist["All"])
    def rate(i, j, prior):
        ra = A[i] / A[j] if A[j] > 0 else prior
        rs = S[i] / S[j] if S[j] > 0 else ra
        return (ns * rs + K * ra) / (ns + K)
    return (rate(0, 1, 0.78), rate(2, 3, 0.22), rate(4, 6, 0.07),
            rate(5, 6, 0.04), rate(6, 1, 6.5), rate(8, 9, 0.38))   # last = return points won %

def load_rows_ret():
    import pandas as pd
    b = pd.read_csv(BATCH, low_memory=False)
    pcol = [c for c in b.columns if c.lower().startswith("pinn")][0]
    price = {}
    for r in b.itertuples(index=False):
        t, a, p2, pa = str(r.tourney_id), str(r.player_a), str(r.player_b), getattr(r, pcol)
        price[(t, a, p2)] = pa; price[(t, p2, a)] = 1 - pa
    need = ["tourney_id", "tourney_date", "match_num", "winner_name", "loser_name", "score", "surface", "best_of",
            "w_ace", "w_df", "w_svpt", "w_SvGms", "w_bpFaced", "w_bpSaved", "w_1stWon", "w_2ndWon",
            "l_ace", "l_df", "l_svpt", "l_SvGms", "l_bpFaced", "l_bpSaved", "l_1stWon", "l_2ndWon"]
    fr = []
    for p in sack_files():
        try: d = pd.read_csv(p, low_memory=False, usecols=lambda c: c in need)
        except Exception: continue
        d["wta"] = int("wta" in os.path.basename(p).lower()); fr.append(d)
    d = pd.concat(fr, ignore_index=True)
    for c in need[7:] + ["match_num"]: d[c] = pd.to_numeric(d.get(c), errors="coerce")
    d = d.drop_duplicates(["tourney_id", "winner_name", "loser_name"])
    d["tourney_date"] = pd.to_numeric(d["tourney_date"], errors="coerce")
    d = d.dropna(subset=["tourney_date"]).sort_values(["tourney_date", "tourney_id", "match_num"])
    hist = collections.defaultdict(lambda: collections.defaultdict(lambda: collections.deque(maxlen=WIN)))
    rows = []
    for r in d.itertuples(index=False):
        surf = str(r.surface or "Hard")
        st = [r.w_ace, r.w_df, r.w_svpt, r.w_SvGms, r.w_bpFaced, r.w_bpSaved, r.w_1stWon, r.w_2ndWon,
              r.l_ace, r.l_df, r.l_svpt, r.l_SvGms, r.l_bpFaced, r.l_bpSaved, r.l_1stWon, r.l_2ndWon]
        ok = all(np.isfinite(st)) and r.w_svpt > 0 and r.l_svpt > 0 and r.w_SvGms > 0 and r.l_SvGms > 0
        key = (str(r.tourney_id), r.winner_name, r.loser_name)
        if ok and key in price and np.isfinite(price[key]):
            pw = float(price[key]); fw = pw >= 0.5
            fav, dog = (r.winner_name, r.loser_name) if fw else (r.loser_name, r.winner_name)
            fb, db = v1_bundle2(hist[fav], surf), v1_bundle2(hist[dog], surf)
            row = {"Date": r.tourney_date, "pinn_fav": max(pw, 1 - pw), "bo5": int(r.best_of == 5), "wta": r.wta,
                   "fav_aces": (r.w_ace if fw else r.l_ace), "dog_aces": (r.l_ace if fw else r.w_ace),
                   "fav_dfs": (r.w_df if fw else r.l_df), "dog_dfs": (r.l_df if fw else r.w_df)}
            for i, nm in enumerate(("hold", "break", "ace_rate", "df_rate", "spg", "ret_pct")):
                row["fav_" + nm] = fb[i]; row["dog_" + nm] = db[i]
            rows.append(row)
        if ok:
            # return points won = opponent's service points - opponent's points won on serve
            w = (r.w_SvGms - (r.w_bpFaced - r.w_bpSaved), r.w_SvGms, r.l_bpFaced - r.l_bpSaved, r.l_SvGms,
                 r.w_ace, r.w_df, r.w_svpt, 1, r.l_svpt - (r.l_1stWon + r.l_2ndWon), r.l_svpt)
            l = (r.l_SvGms - (r.l_bpFaced - r.l_bpSaved), r.l_SvGms, r.w_bpFaced - r.w_bpSaved, r.w_SvGms,
                 r.l_ace, r.l_df, r.l_svpt, 1, r.w_svpt - (r.w_1stWon + r.w_2ndWon), r.w_svpt)
            for name, rec in ((r.winner_name, w), (r.loser_name, l)):
                hist[name][surf].append(rec); hist[name]["All"].append(rec)
    d = pd.DataFrame(rows)
    d["pinn_fav"] = d.pinn_fav.clip(0.5, 0.99); d["lp"] = d.pinn_fav.map(_logit); d["lp2"] = d.lp ** 2
    d["year"] = (d.Date // 10000).astype(int)
    return d.sort_values("Date").reset_index(drop=True)

def ret_study():
    d = load_rows_ret()
    fit, tune, hold = d[d.year <= 2021], d[d.year.between(2022, 2023)], d[d.year >= 2024]
    L = ["APEX OPPONENT-RETURN STUDY (read-only; does knowing the RETURNER improve the projection?)",
         f"rows {len(d)} | holdout {len(hold)} | years {d.year.min()}-{d.year.max()}",
         "GATE (pre-registered): gain >= 10% AND calibration bands within +/-0.05", ""]
    for side, opp in (("fav", "dog"), ("dog", "fav")):
        for cat in ("aces", "dfs"):
            t = f"{side}_{cat}"
            A = ["lp", "lp2", "bo5", "wta", f"{side}_ace_rate", f"{side}_df_rate", f"{side}_spg", f"{side}_hold"]
            B = A + [f"{opp}_ret_pct"]                       # + the returner
            y = hold[t].values
            ba, bb = _ols(_X(fit, A), fit[t].values), _ols(_X(fit, B), fit[t].values)
            pa, pb = _X(hold, A) @ ba, _X(hold, B) @ bb
            ma, mb = np.abs(y - pa).mean(), np.abs(y - pb).mean()
            res = tune[t].values - _X(tune, B) @ bb
            line = np.round(pa - 0.5) + 0.5
            over = (y > line).astype(float)
            p_over = np.array([(pi + res > l).mean() for pi, l in zip(pb, line)])
            conf = np.where(p_over >= 0.5, p_over, 1 - p_over)
            hit = np.where(p_over >= 0.5, over, 1 - over)
            worst = 0.0
            for lo, hi in ((0.5, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 1.01)):
                m = (conf >= lo) & (conf < hi)
                if m.sum() >= 100: worst = max(worst, abs(conf[m].mean() - hit[m].mean()))
            gain = 100 * (ma - mb) / ma
            coef = bb[-1]
            L.append(f"{t:10s} MAE {ma:6.3f} -> {mb:6.3f}  gain {gain:+6.2f}%  "
                     f"maxband {worst:.3f}  ret-coef {coef:+.3f}  corr(A,B) {np.corrcoef(pa, pb)[0,1]:.3f}  "
                     f"{'PASS' if gain >= 10 and worst <= 0.05 else 'fail'}")
    # how big is the effect at the extremes?
    q = hold[[c for c in hold.columns if c.endswith('ret_pct')][0]]
    L += ["", f"returner quality spread in holdout: p10 {q.quantile(.1):.3f} / median {q.median():.3f} / p90 {q.quantile(.9):.3f}",
          "ret-coef is aces per unit of return-points-won: multiply by the p10-p90 spread for the real-world swing."]
    out = "\n".join(L); print(out); open(REPORT.replace(".txt", "_return.txt"), "w").write(out)


def length_study():
    """Does a point-estimate of match length inflate LESS probabilities?
    Compares P(under line) from mean service games vs from the real spread."""
    d = load_rows_ret()
    d["svgms_fav"] = np.nan
    fit, tune, hold = d[d.year <= 2021], d[d.year.between(2022, 2023)], d[d.year >= 2024]
    L = ["APEX MATCH-LENGTH PROPAGATION STUDY (read-only)",
         f"rows {len(d)} | holdout {len(hold)}", "",
         "For each category: stated P(LESS hits) using a POINT estimate of length vs the SPREAD,",
         "then what actually happened. A gap means LESS props are being overpriced.", ""]
    for side in ("fav", "dog"):
        for cat in ("aces", "dfs"):
            t = f"{side}_{cat}"
            F = ["lp", "lp2", "bo5", "wta", f"{side}_ace_rate", f"{side}_df_rate", f"{side}_spg", f"{side}_hold"]
            b = _ols(_X(fit, F), fit[t].values)
            proj_h = _X(hold, F) @ b
            res = tune[t].values - _X(tune, F) @ b          # full residual spread from tune years
            y = hold[t].values
            line = np.round(proj_h - 0.5) + 0.5             # line just under the projection -> a LESS bet
            # point-estimate view: treat the projection as exact, spread = residual sd only
            sd = res.std()
            from math import erf, sqrt
            p_point = np.array([0.5 * (1 + erf((l - m) / (sd * sqrt(2)))) for m, l in zip(proj_h, line)])
            # spread view: empirical residuals (fat tails, skew, all of it)
            p_spread = np.array([(m + res < l).mean() for m, l in zip(proj_h, line)])
            actual = (y < line).astype(float)
            for name, p in (("point-est", p_point), ("spread", p_spread)):
                m = p >= 0.70                                # the band you actually bet
                if m.sum() >= 50:
                    L.append(f"{t:10s} {name:9s} stated {p[m].mean():.3f} on n={m.sum():5d} -> actual {actual[m].mean():.3f}"
                             f"  gap {actual[m].mean() - p[m].mean():+.3f}")
            L.append("")
    out = "\n".join(L); print(out); open(REPORT.replace(".txt", "_length.txt"), "w").write(out)

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "--inventory"
    {"--inventory": inventory, "--study": study, "--study-v1": study_v1, "--sets": study_sets,
     "--scorecard": scorecard, "--return": ret_study, "--length": length_study}.get(mode, inventory)()
