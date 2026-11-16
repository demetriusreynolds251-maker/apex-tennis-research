import re, json, sys
import openclaw_core as oc

LOG = "/tmp/apex_coverage_fix_run_20260928_221521.log"
lines = open(LOG, encoding="utf-8", errors="replace").readlines()
rejects = [l for l in lines if "[Gate11] REJECTED" in l and "not found in V8" in l]
print("TOTAL_REJECT_LINES:", len(rejects))

pat = re.compile(r"REJECTED — (.+?) vs (.+?) — not found in V8 for any tour tried \(([^)]+)\) — specifically: (.+)$")
parsed = []
for l in rejects:
    m = pat.search(l)
    if m:
        parsed.append({
            "player": m.group(1).strip(),
            "opponent": m.group(2).strip(),
            "tours_tried": [t.strip() for t in m.group(3).split(",")],
            "missing_raw": m.group(4).strip(),
        })
print("PARSED_OK:", len(parsed), "of", len(rejects))

# classify + clean names
SUFFIX_PAT = re.compile(r"\s+1st Set$", re.IGNORECASE)
results = []
for r in parsed:
    missing_names = [m.strip() for m in r["missing_raw"].split(",")]
    for mn in missing_names:
        has_1st_set = bool(SUFFIX_PAT.search(mn))
        clean = SUFFIX_PAT.sub("", mn).strip()
        results.append({
            "player": r["player"],
            "opponent": r["opponent"],
            "missing_name_raw": mn,
            "missing_name_clean": clean,
            "has_1st_set_suffix": has_1st_set,
            "tours_tried": r["tours_tried"],
        })

print("TOTAL_MISSING_NAME_INSTANCES:", len(results))
print("WITH_1ST_SET_SUFFIX:", sum(1 for r in results if r["has_1st_set_suffix"]))
print("WITHOUT_1ST_SET_SUFFIX:", sum(1 for r in results if not r["has_1st_set_suffix"]))

# unique clean names to re-test against live V8
unique_clean = sorted(set(r["missing_name_clean"] for r in results))
print("UNIQUE_CLEAN_NAMES:", len(unique_clean))

resolution = {}
for name in unique_clean:
    res_atp = None
    res_wta = None
    try:
        res_atp = oc.v8_resolve_player_name(name, "atp")
    except Exception as e:
        res_atp = f"ERROR:{e}"
    try:
        res_wta = oc.v8_resolve_player_name(name, "wta")
    except Exception as e:
        res_wta = f"ERROR:{e}"
    resolution[name] = {"atp": res_atp, "wta": res_wta}

resolved_count = sum(1 for v in resolution.values() if v["atp"] or v["wta"])
print("RESOLVED_AFTER_CLEANING:", resolved_count, "of", len(unique_clean))

unresolved = [n for n, v in resolution.items() if not v["atp"] and not v["wta"]]
print("STILL_UNRESOLVED_AFTER_CLEANING:", len(unresolved))
for n in unresolved:
    print("  UNRESOLVED:", n, resolution[n])

# Save full structured output
with open("/tmp/gate11_audit_output.json", "w") as f:
    json.dump({
        "total_reject_lines": len(rejects),
        "parsed_ok": len(parsed),
        "results": results,
        "unique_clean_names": unique_clean,
        "resolution": resolution,
        "resolved_count": resolved_count,
        "unresolved": unresolved,
    }, f, indent=2, default=str)

print("DONE")
