#!/usr/bin/env python3
"""
apex_batch_a.py -- 2026-08-17   Batch A: geography features (travel, jet lag, altitude, indoor).

Objective: find information NOT already in Pinnacle's closing line. Nothing here touches Elo.

STAGES (run in order; --audit-only stops after stage 3)
  1  venue table      apex_venues.csv (tournament -> city, country, lat, lon, altitude_m, timezone)
                      + year-dependent rules for moving events (Canada, Tour Finals, WTA Finals,
                      Olympics, Next Gen).  Writes apex_venue_map.csv (every tournament name seen,
                      what it mapped to) and apex_unmapped_tournaments.csv.
  2  coverage report  % of ATP / WTA matches mapped, unmapped tournaments with match counts.
  3  distributions    travel km, time-zone change, east/west, days since arrival, altitude change:
                      mean / median / p90 / missing %.
  4  residual tests   logistic on logit(Pinnacle) + feature, fit on priced rows <= 2023, scored 2024+;
                      pass = gain >= +0.002 logloss vs the Pinnacle calibration refit.
  5  monotonic bins   model-free: for the player on the "worse" side of each feature, actual win rate
                      minus Pinnacle's probability, by bin.  Pass = logical monotone trend AND (4).

Prior-only: every feature for a match uses only tournaments the player had already played.
Round-day offsets inside a tournament are approximate (Sackmann dates are tournament start dates).

USAGE
  python3 apex_batch_a.py --audit-only            # stages 1-3
  python3 apex_batch_a.py                          # stages 1-5 (needs ./odds/, apex_rows_cache.pkl)
  python3 apex_batch_a.py --selftest               # fake data + planted effect: proves the test can detect
"""
import argparse, math, os, re, sys, unicodedata, warnings
from collections import defaultdict
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import apex_combined_model as acm

MARKER = "APEX-BATCH-A-2026-08-17"
STRIP = {"wta", "atp", "open", "masters", "cup", "1000", "500", "250", "premier", "international", "the", "international"}
ROUND_DAY = {"R128": 0, "R64": 2, "R32": 3, "R16": 5, "QF": 6, "SF": 7, "F": 8, "RR": 2, "BR": 8, "Q1": 0, "Q2": 1, "Q3": 2}


def norm(s):
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(c for c in s if not unicodedata.combining(c)).lower().replace("'", "")
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    toks = [t for t in s.split() if t not in STRIP]
    return " ".join(toks)


def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(min(1.0, math.sqrt(a)))


_tz_cache = {}
def utc_offset_hours(tzname, d):
    """UTC offset in hours for zone at date d (DST-aware). None if unknown."""
    if not isinstance(tzname, str) or not tzname:
        return None
    key = (tzname, d.year, d.month)
    if key in _tz_cache:
        return _tz_cache[key]
    try:
        from zoneinfo import ZoneInfo
        off = datetime(d.year, d.month, min(d.day, 28), 12, tzinfo=ZoneInfo(tzname)).utcoffset()
        v = off.total_seconds() / 3600.0
    except Exception:
        v = None
    _tz_cache[key] = v
    return v


# ----------------------------------------------------------------------------- venues
class Venues:
    def __init__(self, path):
        v = pd.read_csv(path)
        self.rows = {}
        self.alias = {}
        for r in v.itertuples(index=False):
            rec = dict(city=r.city, country=r.country, lat=r.latitude, lon=r.longitude, alt=r.altitude_m, tz=r.timezone, key=r.key)
            self.rows[r.key] = rec
            self.alias[norm(r.key)] = r.key
            if isinstance(r.aliases, str):
                for a in r.aliases.split("|"):
                    if a.strip():
                        self.alias[norm(a)] = r.key
        # longest-first list for substring matching
        self.alias_sorted = sorted(self.alias.keys(), key=len, reverse=True)
        self.cache = {}

    def _special(self, n, tour, year):
        if "tour finals" in n or n in ("finals", "atp finals", "nitto finals", "masters"):
            return "shanghai" if year <= 2008 else ("london indoor" if year <= 2020 else "turin")
        if "wta finals" in n or "championships" in n:
            if year <= 2005: return "los angeles"
            if year <= 2007: return "madrid"
            if year <= 2010: return "doha"
            if year <= 2013: return "istanbul"
            if year <= 2018: return "singapore"
            if year == 2019: return "shenzhen"
            if year == 2021: return "guadalajara"
            if year == 2022: return "fort worth"
            if year == 2023: return "cancun"
            return "riyadh"
        if n in ("canada", "rogers", "national bank", "canadian") or "canada" in n or "rogers" in n or "national bank" in n:
            atp_toronto = (year % 2 == 0) if year <= 2019 else (year % 2 == 1)
            toronto = atp_toronto if tour == "ATP" else (not atp_toronto)
            return "toronto" if toronto else "montreal"
        if "olympic" in n:
            return {2008: "beijing", 2012: "wimbledon", 2016: "rio de janeiro", 2020: "tokyo", 2021: "tokyo", 2024: "roland garros"}.get(year)
        if "next gen" in n or "nextgen" in n:
            return "milan" if year <= 2022 else "jeddah"
        if "masters cup" in n:
            return "houston" if year <= 2004 else "shanghai"
        if "tournament of champions" in n:
            return "bali" if year <= 2011 else "sofia"
        return None

    def lookup(self, name, tour, year):
        k = (name, tour, year)
        if k in self.cache:
            return self.cache[k]
        n = norm(name)
        key = self._special(n, tour, year)
        if key is None:
            key = self.alias.get(n)
        if key is None:
            toks = set(n.split())
            for a in self.alias_sorted:
                at = a.split()
                if len(at) >= 1 and all(t in toks for t in at) and (len(a) >= 4 or len(at) > 1):
                    key = self.alias[a]; break
        rec = self.rows.get(key) if key else None
        if rec is not None and (pd.isna(rec["lat"]) or pd.isna(rec["lon"])):
            rec = None
        self.cache[k] = rec
        return rec


def parse_indoor(x):
    """Sackmann 'indoor' column can be 0/1, True/False, 'I'/'O', 'Indoor'/'Outdoor', or missing."""
    if x is None:
        return None
    try:
        if pd.isna(x):
            return None
    except Exception:
        pass
    s = str(x).strip().lower()
    if s in ("1", "1.0", "true", "t", "yes", "y", "i", "indoor"):
        return 1
    if s in ("0", "0.0", "false", "f", "no", "n", "o", "outdoor"):
        return 0
    return None


# events that are (essentially always) played indoors -- used only when the file column is empty
INDOOR_EVENTS = {k: 1 for k in ["rotterdam", "marseille", "montpellier", "sofia", "paris masters", "vienna", "basel", "antwerp", "stockholm",
                                "metz", "moscow", "st petersburg", "memphis", "san jose", "milan", "london indoor", "turin", "zagreb", "dallas",
                                "linz", "ostrava", "luxembourg", "cluj napoca", "lyon", "nur sultan", "astana", "cologne", "zurich", "hasselt",
                                "filderstadt", "stuttgart", "tokyo", "quebec city", "new york", "indianapolis", "st poelten", "bratislava",
                                "kolding", "oslo", "sopot pl", "courmayeur", "tenerife", "limoges", "poitiers", "bergamo", "singapore", "shenzhen",
                                "riyadh", "fort worth", "jeddah", "cancun", "guadalajara", "doha", "dubai", "abu dhabi", "monastir", "hua hin",
                                "seoul", "hong kong", "guangzhou", "tashkent", "nanchang", "zhengzhou", "wuhan", "beijing", "shanghai", "chengdu",
                                "hangzhou", "ningbo", "zhuhai", "tianjin", "dalian", "nanjing", "kaohsiung", "taipei", "osaka", "hiroshima"]}
# NOTE: several entries above are open-air (doha, dubai, tokyo, beijing, shanghai, wuhan, seoul, hong kong, guangzhou, chengdu, hangzhou,
# ningbo, zhuhai, tianjin, dalian, nanjing, kaohsiung, taipei, osaka, hiroshima, guadalajara, cancun, hua hin, tashkent, nanchang, zhengzhou,
# monastir, abu dhabi, riyadh(2024 indoor), fort worth(indoor), jeddah(indoor)) -- they are removed below; kept in one place for audit.
for _k in ["doha", "dubai", "tokyo", "beijing", "shanghai", "wuhan", "seoul", "hong kong", "guangzhou", "chengdu", "hangzhou", "ningbo", "zhuhai",
           "tianjin", "dalian", "nanjing", "kaohsiung", "taipei", "osaka", "hiroshima", "guadalajara", "cancun", "hua hin", "tashkent",
           "nanchang", "zhengzhou", "monastir", "abu dhabi", "singapore", "shenzhen", "stuttgart", "tenerife"]:
    INDOOR_EVENTS.pop(_k, None)
INDOOR_EVENTS.update({"stuttgart": 1, "singapore": 1, "shenzhen": 1})   # WTA Stuttgart (indoor clay), WTA Finals Singapore/Shenzhen indoor


# ----------------------------------------------------------------------------- feature build
def build_geo_features(df, venues):
    """Per match, per side (winner/loser): geography features known BEFORE the match."""
    P = defaultdict(lambda: {"venue": None, "date": None, "tid": None, "hops": [], "arr": {},
                             "n": 0, "w": 0, "in_n": 0, "in_w": 0, "alt_n": 0, "alt_w": 0})
    out = {}
    unmapped = defaultdict(int); mapped_ct = defaultdict(int); total_ct = defaultdict(int)
    venue_map = {}
    for r in df.itertuples(index=False):
        rd = r._asdict()
        tour = rd["tour"]; d = rd["tdate"]; yr = d.year
        name = str(rd.get("tourney_name")); tid = str(rd.get("tourney_id"))
        v = venues.lookup(name, tour, yr)
        total_ct[tour] += 1
        venue_map[(name, tour)] = (v["city"] if v else "", v["country"] if v else "")
        if v is None:
            unmapped[(name, tour)] += 1
        else:
            mapped_ct[tour] += 1
        indoor = parse_indoor(rd.get("indoor"))
        if indoor is None and v is not None:
            indoor = INDOOR_EVENTS.get(v["key"], 0)        # venue-based fallback: known indoor events = 1, else outdoor
            if (v["key"], tour) in (("lyon", "ATP"), ("san jose", "WTA"), ("stuttgart", "ATP")):
                indoor = 0                                 # mixed-use names: ATP Lyon/Stuttgart outdoor, WTA San Jose outdoor
        rnd = str(rd.get("round")).strip()
        wn, ln = str(rd.get("winner_name")), str(rd.get("loser_name"))
        feats = {}
        for who, pname in (("w", wn), ("l", ln)):
            s = P[pname]
            f = dict(travel_km=np.nan, tz_shift=np.nan, days_since_arrival=np.nan, km_30d=np.nan, km_60d=np.nan,
                     alt_change=np.nan, venue_alt=np.nan, indoor=indoor, indoor_rec=np.nan, alt_rec=np.nan, mapped=int(v is not None))
            if v is not None:
                f["venue_alt"] = v["alt"] if not pd.isna(v["alt"]) else np.nan
                if s["tid"] != tid:                     # arriving at a new tournament
                    if s["venue"] is not None and s["date"] is not None:
                        km = haversine(s["venue"]["lat"], s["venue"]["lon"], v["lat"], v["lon"])
                        o1 = utc_offset_hours(s["venue"]["tz"], s["date"]); o2 = utc_offset_hours(v["tz"], d)
                        tz = (o2 - o1) if (o1 is not None and o2 is not None) else np.nan
                        gap = (d - s["date"]).days
                        altc = (v["alt"] - s["venue"]["alt"]) if not (pd.isna(v["alt"]) or pd.isna(s["venue"]["alt"])) else np.nan
                        s["hops"].append((d, km))
                        s["arr"][tid] = dict(km=km, tz=tz, gap=gap, altc=altc)
                    else:
                        s["arr"][tid] = None
                a = s["arr"].get(tid)
                if a is not None:
                    f["travel_km"] = a["km"]; f["tz_shift"] = a["tz"]; f["alt_change"] = a["altc"]
                    f["days_since_arrival"] = min(a["gap"], 120) + ROUND_DAY.get(rnd, 3)
                    f["km_30d"] = sum(k for dd, k in s["hops"] if 0 <= (d - dd).days <= 30)
                    f["km_60d"] = sum(k for dd, k in s["hops"] if 0 <= (d - dd).days <= 60)
                if s["in_n"] >= 10 and s["n"] >= 20:
                    f["indoor_rec"] = s["in_w"] / s["in_n"] - s["w"] / s["n"]
                if s["alt_n"] >= 5 and s["n"] >= 20:
                    f["alt_rec"] = s["alt_w"] / s["alt_n"] - s["w"] / s["n"]
            feats[who] = f
        out[(d, frozenset({acm.norm_text(wn), acm.norm_text(ln)}))] = (wn, ln, feats["w"], feats["l"])
        # ---- update AFTER
        for who, pname, won in (("w", wn, 1), ("l", ln, 0)):
            s = P[pname]
            s["n"] += 1; s["w"] += won
            if indoor == 1:
                s["in_n"] += 1; s["in_w"] += won
            if v is not None and not pd.isna(v["alt"]) and v["alt"] >= 1000:
                s["alt_n"] += 1; s["alt_w"] += won
            if v is not None:
                s["venue"] = v; s["date"] = d; s["tid"] = tid
    return out, unmapped, mapped_ct, total_ct, venue_map


def attach(rows, feats):
    """Join per-match geo features to the cached rows (A/B oriented)."""
    cols = ["travel_km", "tz_shift", "days_since_arrival", "km_30d", "km_60d", "alt_change", "venue_alt", "indoor", "indoor_rec", "alt_rec"]
    A = {c: [] for c in cols}; B = {c: [] for c in cols}; hit = []
    for r in rows.itertuples(index=False):
        rec = feats.get((r.date, frozenset({acm.norm_text(r.player_a), acm.norm_text(r.player_b)})))
        if rec is None:
            hit.append(0)
            for c in cols: A[c].append(np.nan); B[c].append(np.nan)
            continue
        wn, ln, fw, fl = rec
        a_is_w = acm.norm_text(r.player_a) == acm.norm_text(wn)
        fa, fb = (fw, fl) if a_is_w else (fl, fw)
        hit.append(1)
        for c in cols:
            A[c].append(fa[c]); B[c].append(fb[c])
    R = rows.copy()
    R["geo_hit"] = hit
    for c in cols:
        R[f"a_{c}"] = A[c]; R[f"b_{c}"] = B[c]
    R["indoor_match"] = R["a_indoor"]
    R["venue_alt"] = R["a_venue_alt"]
    # A - B differences (the model inputs)
    R["d_travel_km"] = R["a_travel_km"] - R["b_travel_km"]
    R["d_km_30d"] = R["a_km_30d"] - R["b_km_30d"]
    R["d_km_60d"] = R["a_km_60d"] - R["b_km_60d"]
    R["d_tz_abs"] = R["a_tz_shift"].abs() - R["b_tz_shift"].abs()
    R["d_tz_east"] = R["a_tz_shift"].clip(lower=0) - R["b_tz_shift"].clip(lower=0)
    R["d_tz_west"] = (-R["a_tz_shift"]).clip(lower=0) - (-R["b_tz_shift"]).clip(lower=0)
    R["d_days_since_arrival"] = R["a_days_since_arrival"] - R["b_days_since_arrival"]
    R["d_alt_change"] = R["a_alt_change"] - R["b_alt_change"]
    R["d_alt_rec"] = R["a_alt_rec"] - R["b_alt_rec"]
    R["d_indoor_rec"] = R["a_indoor_rec"] - R["b_indoor_rec"]
    R["d_alt_rec_x_alt"] = R["d_alt_rec"] * (R["venue_alt"] >= 1000).astype(float)
    R["d_indoor_rec_x_indoor"] = R["d_indoor_rec"] * (R["indoor_match"] == 1).astype(float)
    return R


def dist_report(R):
    print("\n  distributions (per player, per match, main-tour rows; A-side and B-side pooled):")
    print(f"  {'feature':22s} {'mean':>10s} {'median':>10s} {'p90':>10s} {'missing%':>9s} {'n':>8s}")
    for c, lab in (("travel_km", "travel km"), ("tz_shift", "tz change (h, +east)"), ("days_since_arrival", "days since arrival"),
                   ("alt_change", "altitude change (m)"), ("km_30d", "km last 30d"), ("indoor_rec", "indoor rec - overall"), ("alt_rec", "alt rec - overall")):
        x = pd.concat([R[f"a_{c}"], R[f"b_{c}"]]).astype(float)
        miss = x.isna().mean(); xv = x.dropna()
        print(f"  {lab:22s} {xv.mean():10.1f} {xv.median():10.1f} {xv.quantile(0.9):10.1f} {miss*100:8.1f}% {len(xv):8,}")
    tz = pd.concat([R["a_tz_shift"], R["b_tz_shift"]]).dropna()
    east = (tz > 0.5).mean(); west = (tz < -0.5).mean()
    print(f"  east/west: eastward hops {east*100:.1f}%   westward {west*100:.1f}%   no change {100*(1-east-west):.1f}%   |zones| p90 {tz.abs().quantile(.9):.1f}")
    print(f"  altitude of venue: <500m {100*(R['venue_alt']<500).mean():.1f}%   500-1500m {100*((R['venue_alt']>=500)&(R['venue_alt']<1500)).mean():.1f}%   >=1500m {100*(R['venue_alt']>=1500).mean():.1f}%   unknown {100*R['venue_alt'].isna().mean():.1f}%")
    print(f"  indoor matches: {100*(R['indoor_match']==1).mean():.1f}%   outdoor {100*(R['indoor_match']==0).mean():.1f}%   unknown {100*R['indoor_match'].isna().mean():.1f}%   (file column where present, else known-indoor-event list)")


# ----------------------------------------------------------------------------- tests
def logit_(p):
    p = np.clip(np.asarray(p, dtype=float), 1e-4, 1 - 1e-4); return np.log(p / (1 - p))


def residual_tests(T, test_from, feats):
    from sklearn.linear_model import LogisticRegression
    H = T[T.year < test_from]; S = T[T.year >= test_from]
    yH, yS = H["label"].values, S["label"].values
    base_raw = acm.logloss(S["pinn_a"].values, yS)
    def fit(fs, mask_H=None, mask_S=None):
        Hh = H if mask_H is None else H[mask_H]; Ss = S if mask_S is None else S[mask_S]
        XH = np.column_stack([logit_(Hh["pinn_a"].values)] + [Hh[f].fillna(0).values for f in fs])
        XS = np.column_stack([logit_(Ss["pinn_a"].values)] + [Ss[f].fillna(0).values for f in fs])
        m = LogisticRegression(C=1.0, max_iter=3000).fit(XH, Hh["label"].values)
        p = m.predict_proba(XS)[:, 1]
        return acm.logloss(p, Ss["label"].values), m.coef_[0], len(Hh), len(Ss)
    ref, _, nH, nS = fit([])
    print(f"\n  priced rows: fit {nH:,} (<= {test_from-1})   score {nS:,} ({test_from}+)   Pinnacle raw LL {base_raw:.4f}   refit LL {ref:.4f}")
    print(f"  {'feature':28s} {'LL':>8s} {'gain':>8s} {'coef':>8s}   verdict")
    res = {}
    for f in feats:
        l_, coef, _, _ = fit([f])
        g = ref - l_
        res[f] = g
        print(f"  {f:28s} {l_:8.4f} {g:+8.4f} {coef[1]:+8.3f}   {'PASS (>= +0.002)' if g >= 0.002 else 'no'}")
    l_, coef, _, _ = fit(feats)
    print(f"  {'ALL geography together':28s} {l_:8.4f} {ref-l_:+8.4f}            {'PASS' if ref-l_ >= 0.002 else 'no'}")
    # subset tests where the feature is defined/relevant
    for f, mask_name, mH, mS in (("d_alt_rec", "altitude venues (>=1000m) only", (H.venue_alt >= 1000).values, (S.venue_alt >= 1000).values),
                                  ("d_indoor_rec", "indoor matches only", (H.indoor_match == 1).values, (S.indoor_match == 1).values)):
        if mH.sum() > 500 and mS.sum() > 100:
            r0, _, a, b = fit([], mH, mS); r1, coef, _, _ = fit([f], mH, mS)
            print(f"  {f:28s} on {mask_name}: fit {a:,} score {b:,}  refit LL {r0:.4f} -> {r1:.4f}  gain {r0-r1:+.4f}  coef {coef[1]:+.3f}")
    return res


def mono_table(T, focal_val_a, focal_val_b, bins, labels, title, higher_is_worse=True):
    """Focal = the player with the higher value (e.g. travelled more). Report focal win% - Pinnacle prob by bin."""
    a, b = focal_val_a.values.astype(float), focal_val_b.values.astype(float)
    ok = ~(np.isnan(a) | np.isnan(b))
    focal_is_a = a >= b
    val = np.where(focal_is_a, a, b)
    other = np.where(focal_is_a, b, a)
    y = T["label"].values; pa = T["pinn_a"].values
    focal_won = np.where(focal_is_a, y == 1, y == 0).astype(float)
    focal_p = np.where(focal_is_a, pa, 1 - pa)
    print(f"\n  {title}  (focal = player with the larger value; residual = focal win% - Pinnacle's prob; 0 = market had it)")
    print(f"  {'bin':22s} {'n':>7s} {'focal win%':>10s} {'Pinn prob':>10s} {'residual':>9s} {'+/-':>6s}")
    means = []
    for lo, hi, lab in zip(bins[:-1], bins[1:], labels):
        m = ok & (val >= lo) & (val < hi)
        n = int(m.sum())
        if n < 30:
            print(f"  {lab:22s} {n:7,}  (too few)"); means.append(np.nan); continue
        w = focal_won[m].mean(); p = focal_p[m].mean(); r = w - p; se_ = np.sqrt(w * (1 - w) / n)
        means.append(r)
        print(f"  {lab:22s} {n:7,} {w*100:9.1f}% {p*100:9.1f}% {r*100:+8.2f} {se_*100:6.2f}")
    v = [x for x in means if not np.isnan(x)]
    if len(v) >= 3:
        d = np.diff(v)
        trend = "monotone DOWN (worse with more)" if all(x <= 0.0005 for x in d) else ("monotone UP" if all(x >= -0.0005 for x in d) else "NOT monotone")
        print(f"  trend across bins: {trend}")


def monotonic_section(T):
    print("\n" + "=" * 78 + "\nSTAGE 5 -- monotonic checks (model-free, all priced rows)\n" + "=" * 78)
    mono_table(T, T["a_travel_km"], T["b_travel_km"], [0, 500, 2000, 5000, 1e9], ["0-500 km", "500-2000 km", "2000-5000 km", "5000+ km"],
               "TRAVEL DISTANCE into this tournament")
    mono_table(T, T["a_tz_shift"].abs(), T["b_tz_shift"].abs(), [0, 1, 3, 6, 99], ["0 zones", "1-2 zones", "3-5 zones", "6+ zones"],
               "TIME ZONES CROSSED (either direction)")
    mono_table(T, T["a_tz_shift"].clip(lower=0), T["b_tz_shift"].clip(lower=0), [1, 3, 6, 99], ["1-2 east", "3-5 east", "6+ east"],
               "EASTWARD travel (zones)")
    mono_table(T, (-T["a_tz_shift"]).clip(lower=0), (-T["b_tz_shift"]).clip(lower=0), [1, 3, 6, 99], ["1-2 west", "3-5 west", "6+ west"],
               "WESTWARD travel (zones)")
    mono_table(T, -T["a_days_since_arrival"], -T["b_days_since_arrival"], [-120, -14, -7, -3, 1], ["14+ days", "7-13 days", "3-6 days", "0-2 days"],
               "DAYS SINCE ARRIVAL (focal = fewer days; bins run from most rest to least)")
    mono_table(T, T["a_alt_change"], T["b_alt_change"], [-5000, 0, 500, 1500, 9999], ["descended", "0-500 m up", "500-1500 m up", "1500+ m up"],
               "ALTITUDE CHANGE from previous venue (focal = bigger climb)")
    mono_table(T, T["a_km_30d"], T["b_km_30d"], [0, 2000, 8000, 15000, 1e9], ["0-2k km/30d", "2-8k", "8-15k", "15k+"],
               "CUMULATIVE TRAVEL last 30 days")
    ia = T[T.indoor_match == 1]
    if len(ia) > 500:
        mono_table(ia, ia["a_indoor_rec"], ia["b_indoor_rec"], [-1, 0.0, 0.05, 0.10, 1], ["worse indoors", "0-5 pts better", "5-10 pts", "10+ pts"],
                   "INDOOR record minus own overall, on INDOOR matches (focal = better indoor specialist)")
    aa = T[T.venue_alt >= 1000]
    if len(aa) > 300:
        mono_table(aa, aa["a_alt_rec"], aa["b_alt_rec"], [-1, 0.0, 0.05, 0.10, 1], ["worse at altitude", "0-5 pts better", "5-10 pts", "10+ pts"],
                   "ALTITUDE record minus own overall, at ALTITUDE venues >=1000m (focal = better altitude record)")


# ----------------------------------------------------------------------------- self-test
def selftest(venues):
    print("SELF-TEST: fake data, planted travel effect that Pinnacle does NOT know about")
    d = acm.make_fake("/tmp/apex_fake")
    df = acm.load_sackmann(d, 2015, False)
    cities = ["australian open", "dubai", "indian wells", "miami", "monte carlo", "madrid", "rome", "roland garros", "halle", "wimbledon",
              "washington", "toronto", "cincinnati", "us open", "tokyo", "shanghai", "vienna", "paris masters"]
    df["tourney_name"] = df["tourney_name"].map(lambda t: cities[int(str(t)[1:]) % len(cities)])
    df["indoor"] = df["tourney_name"].isin(["vienna", "paris masters"]).astype(int)
    feats, unmapped, mapped_ct, total_ct, _ = build_geo_features(df, venues)
    print(f"  mapped: " + ", ".join(f"{t} {mapped_ct[t]}/{total_ct[t]}" for t in total_ct))
    rows = pd.read_pickle("/tmp/apex_fake/rows.pkl") if os.path.exists("/tmp/apex_fake/rows.pkl") else acm.build_rows(df, 5, 7, True)
    R = attach(rows, feats)
    print(f"  rows joined: {R.geo_hit.mean()*100:.1f}%")
    dist_report(R)
    # synthetic market + outcomes: Pinnacle knows skill (p0), outcome ALSO depends on travel diff (planted)
    rng = np.random.RandomState(0)
    p0 = 1 / (1 + np.exp(-(rng.normal(0, 1.0, len(R)))))
    trav = np.nan_to_num(R["d_travel_km"].values) / 1000.0
    for label, beta in (("NULL (no effect planted)", 0.0), ("PLANTED (-0.06 per 1000 km more travel)", -0.06)):
        p_true = 1 / (1 + np.exp(-(logit_(p0) + beta * trav)))
        T = R.copy(); T["pinn_a"] = p0; T["label"] = (rng.rand(len(R)) < p_true).astype(int)
        print(f"\n  --- {label} ---")
        residual_tests(T, 2024, ["d_travel_km", "d_tz_abs", "d_days_since_arrival"])
        mono_table(T, T["a_travel_km"], T["b_travel_km"], [0, 500, 2000, 5000, 1e9], ["0-500 km", "500-2000 km", "2000-5000 km", "5000+ km"], "TRAVEL DISTANCE")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sack-dir", default="ATP & WTA, 1968-2026")
    ap.add_argument("--venues", default="apex_venues.csv")
    ap.add_argument("--cache", default="apex_rows_cache.pkl")
    ap.add_argument("--odds-dir", default="odds")
    ap.add_argument("--year-from", type=int, default=2005)
    ap.add_argument("--test-from", type=int, default=2024)
    ap.add_argument("--audit-only", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    print(f"[{MARKER}]")
    venues = Venues(args.venues)
    print(f"venue table: {len(venues.rows)} entries, {len(venues.alias)} names/aliases")
    if args.selftest:
        selftest(venues); return

    df = acm.load_sackmann(args.sack_dir, args.year_from, False)
    df["is_main"] = ~df["tourney_level"].astype(str).str.strip().isin(acm.NON_MAIN_LEVELS)
    if "indoor" in df.columns:
        raw = df["indoor"]
        print(f"indoor column in source files: non-empty {raw.notna().mean()*100:.1f}% of rows; values: "
              + ", ".join(f"{k!r}={v:,}" for k, v in raw.value_counts(dropna=False).head(6).items()))
        byyr = df.groupby(df.tdate.map(lambda d: d.year))["indoor"].apply(lambda s: s.notna().mean() * 100)
        print("  non-empty by year: " + ", ".join(f"{y}={p:.0f}%" for y, p in byyr.items()))
    else:
        print("indoor column NOT present in the source files -> venue-based indoor fallback will be used")
    feats, unmapped, mapped_ct, total_ct, venue_map = build_geo_features(df, venues)

    print("\n" + "=" * 78 + "\nSTAGE 1/2 -- venue mapping and coverage\n" + "=" * 78)
    for t in ("ATP", "WTA"):
        print(f"  {t}: {mapped_ct[t]:,} of {total_ct[t]:,} matches mapped ({100*mapped_ct[t]/max(total_ct[t],1):.1f}%)")
    dm = df[df.is_main]
    for t in ("ATP", "WTA"):
        sub = dm[dm.tour == t]
        m = sub.apply(lambda r: venues.lookup(str(r.tourney_name), t, r.tdate.year) is not None, axis=1)
        print(f"  {t} main-tour only: {int(m.sum()):,} of {len(sub):,} matches mapped ({100*m.mean():.1f}%)")
    um = pd.DataFrame([(n, t, c) for (n, t), c in unmapped.items()], columns=["tourney_name", "tour", "matches"]).sort_values("matches", ascending=False)
    um.to_csv("apex_unmapped_tournaments.csv", index=False)
    vm = pd.DataFrame([(n, t, c, cty) for (n, t), (c, cty) in venue_map.items()], columns=["tourney_name", "tour", "mapped_city", "mapped_country"]).sort_values(["tour", "tourney_name"])
    vm.to_csv("apex_venue_map.csv", index=False)
    print(f"  distinct tournament names seen: {len(vm):,}   unmapped names: {len(um):,}   -> apex_venue_map.csv / apex_unmapped_tournaments.csv")
    print("  top unmapped by match count (paste these back and I will add rows):")
    for r in um.head(40).itertuples(index=False):
        print(f"    {r.tourney_name:40s} {r.tour}  {r.matches:,}")

    print("\n" + "=" * 78 + "\nSTAGE 3 -- feature distributions\n" + "=" * 78)
    if not os.path.exists(args.cache):
        sys.exit("apex_rows_cache.pkl not found -- run apex_diagnose.py first")
    rows = pd.read_pickle(args.cache)
    R = attach(rows, feats)
    print(f"  rows: {len(R):,}   joined to a match: {R.geo_hit.mean()*100:.1f}%   both venues known: {100*(R.a_travel_km.notna() & R.b_travel_km.notna()).mean():.1f}%")
    dist_report(R)
    R.to_pickle("apex_rows_geo.pkl")
    print("  saved -> apex_rows_geo.pkl")
    if args.audit_only:
        print("\n(audit-only: stopping before residual tests)"); return

    print("\n" + "=" * 78 + "\nSTAGE 4 -- residual tests vs Pinnacle (fit <= %d, score %d+)\n" % (args.test_from - 1, args.test_from) + "=" * 78)
    odds = acm.load_odds(args.odds_dir)
    T = acm.market_join(R, odds)
    T = T[T["pinn_a"].notna()].reset_index(drop=True)
    print(f"  priced rows: {len(T):,} of {len(R):,}")
    feats_list = ["d_travel_km", "d_km_30d", "d_km_60d", "d_tz_abs", "d_tz_east", "d_tz_west", "d_days_since_arrival",
                  "d_alt_change", "d_alt_rec_x_alt", "d_indoor_rec_x_indoor"]
    residual_tests(T, args.test_from, feats_list)
    monotonic_section(T)
    T.to_csv("apex_batch_a_rows.csv", index=False)
    print(f"\n  saved priced rows with geo features -> apex_batch_a_rows.csv   [{MARKER}]")
    print("  DECISION RULE: a feature moves on only if (stage 4 gain >= +0.002) AND (stage 5 shows a logical monotone trend).")


if __name__ == "__main__":
    main()
