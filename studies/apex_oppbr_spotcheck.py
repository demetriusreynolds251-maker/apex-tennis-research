"""Independent audit script for the trailing opponent break-rate feature.
Recomputes break_rate from raw match data directly (NOT by calling
rate_bundle() or replay() again), to prove the feature's numbers are right
and that no future match entered any calculation. Read-only, no writes.
"""
import math
import pickle
import pandas as pd
import apex_prop_model_v1 as v1

df = v1.load_sackmann('ATP & WTA, 1968-2026', year_from=2005, challengers=False)
WINDOW, SHRINK = 40, 15

def isnan(x):
    return isinstance(x, float) and math.isnan(x)

def player_matches(name, before_date):
    """All matches `name` played strictly before `before_date` that pass
    replay()'s own stats_ok gate (only these get appended to player history
    in the real replay() loop), oldest->newest, ordered exactly the way
    load_sackmann() sorts: (tourney_date, tourney_id, match_num)."""
    out = []
    for r in df.itertuples(index=False):
        d = r.tourney_date.date()
        if d >= before_date:
            continue
        stats_ok = all(not isnan(v) for v in
                       (r.w_ace, r.w_df, r.w_svpt, r.w_SvGms, r.w_bpSaved, r.w_bpFaced,
                        r.l_ace, r.l_df, r.l_svpt, r.l_SvGms, r.l_bpSaved, r.l_bpFaced)) \
            and r.w_svpt > 0 and r.l_svpt > 0 and r.w_SvGms > 0 and r.l_SvGms > 0
        if not stats_ok:
            continue
        mnum = r.match_num if r.match_num == r.match_num else 0
        if r.winner_name == name:
            out.append((d, r.tourney_id, mnum, r.surface, 'W',
                        r.l_SvGms, r.l_bpFaced, r.l_bpSaved))
        elif r.loser_name == name:
            out.append((d, r.tourney_id, mnum, r.surface, 'L',
                        r.w_SvGms, r.w_bpFaced, r.w_bpSaved))
    out.sort(key=lambda x: (x[0], x[1], x[2]))
    return out

def manual_break_rate(name, surface, before_date, window=WINDOW, shrink=SHRINK):
    hist = player_matches(name, before_date)
    allh = hist[-window:]
    surfh = [h for h in hist if h[3] == surface][-window:]
    def agg(rows):
        osv = sum(h[5] for h in rows if h[5] == h[5])
        obf = sum(h[6] for h in rows if h[6] == h[6])
        obs = sum(h[7] for h in rows if h[7] == h[7])
        return osv, obf, obs, len(rows)
    a_osv, a_obf, a_obs, na = agg(allh)
    s_osv, s_obf, s_obs, ns = agg(surfh)
    ra = (a_obf - a_obs) / a_osv if a_osv else 0.0
    rs = (s_obf - s_obs) / s_osv if s_osv else ra
    br = (ns * rs + shrink * ra) / (ns + shrink)
    return br, allh, na

picks = pickle.load(open('/tmp/spotcheck_rows.pkl', 'rb'))
for p in picks:
    row_date = pd.Timestamp(p['date']).date()
    print("=" * 70)
    print("MATCH:", p['date'], p['tourney_name'], p['round'], '|', p['winner'], 'd.', p['loser'])
    for role, name, stored in (
        ('WINNER', p['winner'], p['l_W40_K15_break_rate']),
        ('LOSER', p['loser'], p['w_W40_K15_break_rate']),
    ):
        br, used, na = manual_break_rate(name, p['surface'], row_date)
        last5 = used[-5:]
        newest_used_date = max(h[0] for h in used) if used else None
        ok = abs(br - stored) < 1e-9
        print(f"  [OPPONENT = {name}] independently recomputed break_rate: {br:.6f}  (stored: {stored:.6f})  match: {'YES' if ok else 'NO -- MISMATCH'}")
        print(f"    matches used: {na} (all strictly before {row_date})")
        print(f"    newest match used: {newest_used_date}  -> before row date? {newest_used_date < row_date}")
        print(f"    last 5 of {name}'s matches used (date, tourney_id, match_num, surface, W/L):",
              [(h[0].isoformat(), h[1], h[2], h[3], h[4]) for h in last5])
