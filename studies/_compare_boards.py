import csv, json
from collections import Counter

def load(path):
    with open(path) as f:
        return list(csv.DictReader(f))

picks = load("apex_engine_picks_log_v1.csv")

oct5 = [r for r in picks if r.get("match_date") == "2026-10-05"]

# "today" = rows from the most recent fetch run -- take rows whose ts
# falls on the latest date present in the log (today's live fetch just archived)
all_ts_dates = sorted(set((r.get("ts") or "")[:10] for r in picks if r.get("ts")))
today_date = all_ts_dates[-1] if all_ts_dates else None
today = [r for r in picks if (r.get("ts") or "")[:10] == today_date]

def f(x):
    try: return float(x)
    except: return None

def summarize(label, rows):
    probs = [f(r.get("prob")) for r in rows if f(r.get("prob")) is not None]
    confs = [f(r.get("confidence")) for r in rows if f(r.get("confidence")) is not None]
    cats = Counter(r.get("category") for r in rows)
    players = Counter(r.get("player") for r in rows)
    print(f"=== {label} (n={len(rows)}) ===")
    print(f"avg stated probability: {sum(probs)/len(probs):.3f}" if probs else "avg prob: n/a", f"(n={len(probs)})")
    print(f"avg confidence: {sum(confs)/len(confs):.1f}" if confs else "avg confidence: n/a", f"(n={len(confs)})")
    print("category mix:", dict(cats.most_common()))
    print("distinct players/matches:", len(players))
    print("top player repeats:", players.most_common(5))
    top20 = sorted(rows, key=lambda r: -(f(r.get("confidence")) or -1))[:20]
    print("-- top 20 by confidence --")
    for r in top20:
        print(f"  {r.get('player'):<28} {r.get('category'):<14} {r.get('line'):>6}  dir={r.get('direction'):<5} "
              f"prob={r.get('prob')}  conf={r.get('confidence')}  tier={r.get('tier')}  prop_type={r.get('prop_type')}")
    print()

print("today_date resolved as:", today_date)
print()
summarize("2026-10-05 (match_date)", oct5)
summarize(f"TODAY ({today_date}, ts-based)", today)
