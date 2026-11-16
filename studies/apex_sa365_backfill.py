"""
apex_sa365_backfill.py  (APEX-SA365-PERSET-2026-09-27, Phase 1 backfill)

Backfills apex_sa365_perset_capture's DB from the real, known match universe:
every unique (player, opponent, match_date) Apex actually made a pick on,
per apex_engine_picks_log_v1.csv -- which already carries ground-truth
surface / best_of / tour columns, so those ride along into `captures`
for free (no guessing).

Read-only against every existing production file; only writes to the new
DB and its own run log. Reuses apex_settle_sa365.find_event/stat_sheet
as-is, so the existing rate limiting (0.25s sleeps) and on-disk sheet
cache (data/sa365_sheets/*.json) apply unchanged -- matches already
cached there cost zero new API calls.
"""

import sys
import time
import pandas as pd

import apex_sa365_perset_capture as cap

PICKS_LOG = "apex_engine_picks_log_v1.csv"
LOG_FILE = "apex_sa365_backfill.log"


def _tour_guess(row):
    # Apex splits fixtures by tour at fetch time (upcoming/{atp|wta}); the picks
    # log doesn't carry a tour column directly, so this is left blank here --
    # deliberately NOT inferring gender from names. tour will show as None in
    # captures unless a future picks-log column supplies it.
    return None


def main():
    limit = None
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        limit = int(sys.argv[1])

    cap.init_db()
    df = pd.read_csv(PICKS_LOG)
    df = df[df["player"].astype(str) != "match"]  # skip the match-level summary rows; keep player-level

    uniq = df[["player", "opponent", "match_date", "surface", "best_of", "category"]].drop_duplicates(
        subset=["player", "opponent", "match_date"]
    )
    if limit:
        uniq = uniq.head(limit)

    counts = {"stored": 0, "no_event": 0, "no_statsheet": 0, "error": 0}
    lines = []
    t0 = time.time()
    for i, r in enumerate(uniq.itertuples(index=False), 1):
        meta = dict(surface=r.surface, best_of=int(r.best_of) if pd.notna(r.best_of) else None,
                    tour=None, category=r.category)
        try:
            status, note, _dup = cap.capture_one(r.player, r.opponent, r.match_date, meta)
        except Exception as e:
            status, note = "error", "%s: %s" % (type(e).__name__, e)
        counts[status] += 1
        line = "%3d/%d  %-12s %-22s vs %-22s %-10s -> %-13s %s" % (
            i, len(uniq), r.match_date, r.player[:22], r.opponent[:22],
            r.surface, status, note)
        print(line)
        lines.append(line)

    summary = "\nDONE in %.1fs -- %s\nTotal unique matches attempted: %d\n" % (
        time.time() - t0, counts, len(uniq))
    print(summary)
    lines.append(summary)
    with open(LOG_FILE, "a") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
