import sys

PATH = "apex_edge_tracker.py"
with open(PATH, "r", encoding="utf-8") as f:
    src = f.read()

orig = src

anchor = '''    _FIXED_CAL_MANUAL = {
        "total_games":   8.1,
        "games_won":     2.1,
        "dfs":          -1.0,
        "fantasy_score": -1.6,
        "breaks":       -3.6,
        "aces":         -11.2,
    }
    GLOBAL_BLEND_FRAC = 0.25   # weight toward the fixed manual table; 0.75 to calibration
    if n >= 5 and cs.get("cal_pts") is not None:
        _cal_scale = cs["cal_pts"] / 0.10
        ev_calibrated = (30.0 if _cal_scale < 0 else 20.0) * w * max(-1.5, min(1.0, _cal_scale))
    else:
        ev_calibrated = 0.0
    ev_fixed_manual = _FIXED_CAL_MANUAL.get(cat, 0.0)
'''
assert src.count(anchor) == 1, "anchor not found exactly once"

insertion = '''    _FIXED_CAL_MANUAL = {
        "total_games":   8.1,
        "games_won":     2.1,
        "dfs":          -1.0,
        "fantasy_score": -1.6,
        "breaks":       -3.6,
        "aces":         -11.2,
    }
    GLOBAL_BLEND_FRAC = 0.25   # weight toward the fixed manual table; 0.75 to calibration

    # APEX-ACESBAND-2026-10-07 (owner, approved production configuration):
    # Aces' calibrated-EV term is computed per PROBABILITY BAND instead of
    # per category. Root-cause study (2026-10-07, Top-6 crossover
    # investigation) found Aces' category-wide calibration gap (n=138,
    # cal_pts=-0.1155) smeared four very different bands together: 60-69%
    # is well-calibrated (gap -1.82pts) while 70-79% and 80%+ are both
    # badly overconfident (gaps -17.70 and -19.74pts) -- the opposite of
    # the "high-confidence Aces are suppressed" hypothesis this was built
    # to test. Band cal_pts values below are a snapshot from that replay
    # (n=47-53 per band); read-only replay confirmed Top 1 and Elite 6
    # unchanged, Top 3 / Top 6 / Best Bets 15 all improved, 0/253 sampled
    # non-Aces picks changed score. Every other category's math below is
    # untouched -- this block only changes which cal_pts value ev_calibrated
    # reads for cat == "aces".
    _ACES_BAND_CAL = {
        (50.0, 60.0):  (-0.1129, 52),
        (60.0, 70.0):  (-0.0182, 49),
        (70.0, 80.0):  (-0.1770, 47),
        (80.0, 101.0): (-0.1974, 53),
    }

    def _aces_band_cal_pts(pct):
        for (blo, bhi), (cp, bn) in _ACES_BAND_CAL.items():
            if blo <= pct < bhi:
                return cp, bn
        return None, 0

    if cat == "aces":
        _band_cal_pts, _band_n = _aces_band_cal_pts(prob * 100.0)
        if _band_n >= 5 and _band_cal_pts is not None:
            _band_scale = _band_cal_pts / 0.10
            _band_w = min(_band_n / 25.0, 1.0)
            ev_calibrated = (30.0 if _band_scale < 0 else 20.0) * _band_w * max(-1.5, min(1.0, _band_scale))
        else:
            ev_calibrated = 0.0
    elif n >= 5 and cs.get("cal_pts") is not None:
        _cal_scale = cs["cal_pts"] / 0.10
        ev_calibrated = (30.0 if _cal_scale < 0 else 20.0) * w * max(-1.5, min(1.0, _cal_scale))
    else:
        ev_calibrated = 0.0
    ev_fixed_manual = _FIXED_CAL_MANUAL.get(cat, 0.0)
'''
src = src.replace(anchor, insertion, 1)

assert src != orig, "no changes were made"

with open(PATH, "w", encoding="utf-8") as f:
    f.write(src)

print("PATCH APPLIED OK")
