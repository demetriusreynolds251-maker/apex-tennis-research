#!/usr/bin/env python3
"""APEX-GOBLIN-CLASSIFY-DIAG-2026-09-28 -- read-only report over
apex_goblin_classification_diag_v1.csv (written by the diagnostic hook added
to fetch_prizepicks_api in openclaw_core.py). Never writes anything, never
touches production files. Run any time to see current evidence:
    python3 apex_goblin_diag_report.py
"""
import csv, os
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(HERE, "apex_goblin_classification_diag_v1.csv")


def main():
    if not os.path.exists(LOG):
        print("No diagnostic data yet -- apex_goblin_classification_diag_v1.csv doesn't exist.")
        print("It's created on the next prop fetch (fetch_prizepicks_api) after the "
              "2026-09-28 diagnostic patch. Nothing to report until then.")
        return
    rows = list(csv.DictReader(open(LOG, encoding="utf-8")))
    print("Total props with classification diagnostics logged:", len(rows))
    if not rows:
        print("(file exists but is empty)")
        return
    dates = sorted(set(r["match_date"] for r in rows if r.get("match_date")))
    print("Date range:", dates[0] if dates else "?", "to", dates[-1] if dates else "?")
    print()

    goblin = [r for r in rows if r.get("is_goblin", "").strip() == "True"]
    print("Classified is_goblin=True: %d of %d (%.1f%%)" % (
        len(goblin), len(rows), 100 * len(goblin) / len(rows) if rows else 0))
    print()

    print("--- Reason breakdown, ALL props (goblin + non-goblin) ---")
    reason_counts = Counter(r.get("reason", "?") for r in rows)
    for reason, n in reason_counts.most_common():
        print("  %5d  (%5.1f%%)  %s" % (n, 100 * n / len(rows), reason))
    print()

    if goblin:
        print("--- Reason breakdown, GOBLIN-CLASSIFIED props only ---")
        greason_counts = Counter(r.get("reason", "?") for r in goblin)
        for reason, n in greason_counts.most_common():
            print("  %5d  (%5.1f%%)  %s" % (n, 100 * n / len(goblin), reason))
        print()

        promo_only = [r for r in goblin if r.get("reason", "").startswith("is_promo_true_discount_zero")]
        print("Goblin-tagged SOLELY because of is_promo (discount_percentage == 0): "
              "%d of %d goblin props (%.1f%%)" % (
                  len(promo_only), len(goblin), 100 * len(promo_only) / len(goblin) if goblin else 0))
        print()
        if promo_only:
            print("Sample is_promo-only Goblin classifications (up to 10):")
            for r in promo_only[:10]:
                print("  %s | %-20s vs %-25s | %-12s %6s | discount=%s is_promo=%s" % (
                    r.get("match_date"), r.get("player"), r.get("opponent"),
                    r.get("stat_type"), r.get("line"), r.get("discount_percentage"), r.get("is_promo")))
            print()

    print("--- Daily counts by reason ---")
    by_day = defaultdict(Counter)
    for r in rows:
        by_day[r.get("match_date", "?")][r.get("reason", "?")] += 1
    for day in sorted(by_day):
        print(" ", day, "->", dict(by_day[day]))


if __name__ == "__main__":
    main()
