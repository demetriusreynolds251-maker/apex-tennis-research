import json, csv, re

d1 = json.load(open("/tmp/gate11_audit_output.json"))
d2 = json.load(open("/tmp/gate11_audit2_output.json"))

# index d2 by (player.lower(), opponent_raw.lower()) for tournament/tour lookup
idx = {}
for r in d2:
    idx[(r["player"].lower(), r["opponent_raw"].lower())] = r

rows = []
for r in d1["results"]:
    key = (r["player"].lower(), r["missing_name_raw"].lower()) if r["missing_name_raw"] != r["player"] else None
    # missing_name_raw is either the opponent (with suffix) or occasionally the player;
    # match against d2 using player+opponent_raw pair
    meta = idx.get((r["player"].lower(), (r["opponent"] if False else None) or ""), None)
    rows.append(r)

# Simpler: iterate d2 directly since it already carries player/opponent_raw/opponent_clean/tournament/tour
resolution = d1["resolution"]

out_rows = []
for r in d2:
    clean = r["opponent_clean"]
    res = resolution.get(clean, {"atp": None, "wta": None})
    resolved = bool(res.get("atp") or res.get("wta"))
    out_rows.append({
        "player": r["player"],
        "opponent_raw_with_suffix": r["opponent_raw"],
        "opponent_cleaned": clean,
        "resolves_after_cleaning": resolved,
        "resolved_atp_as": res.get("atp") or "",
        "resolved_wta_as": res.get("wta") or "",
        "tournament_from_sibling_prop": r.get("tournament") or "(no sibling prop in this run)",
        "tour": r.get("tour") or "",
        "category": "A - Name parsing issue (market-scope suffix contamination)",
        "verdict": "FALSE REJECTION" if resolved else "UNCERTAIN",
    })

with open("gate11_rejection_forensic_audit.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()))
    w.writeheader()
    w.writerows(out_rows)

print("WROTE", len(out_rows), "ROWS")
print("FALSE_REJECTIONS:", sum(1 for r in out_rows if r["verdict"]=="FALSE REJECTION"))
print("TRUE_REJECTIONS:", sum(1 for r in out_rows if r["verdict"]=="TRUE REJECTION"))
print("UNCERTAIN:", sum(1 for r in out_rows if r["verdict"]=="UNCERTAIN"))
