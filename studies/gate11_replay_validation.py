import json
import openclaw_core as oc

data = json.load(open("/tmp/gate11_audit_output.json"))
results = data["results"]  # each: player, opponent(clean, no use), missing_name_raw, missing_name_clean, tours_tried

print("REPLAYING", len(results), "HISTORICAL GATE 11 REJECTIONS THROUGH THE FIXED CODE")
print("(calling the real, patched v8_resolve_player_name() with the ORIGINAL")
print(" contaminated opponent strings, exactly as Gate 11 saw them before the fix)")
print()

before_rejected = len(results)
after_recovered = 0
after_still_rejected = 0
examples_recovered = []
examples_still_failed = []

for r in results:
    player = r["player"]
    opponent_raw = r["missing_name_raw"]  # the ORIGINAL contaminated string, e.g. "Alex Molcan 1st Set"
    tours = r["tours_tried"]

    passed_any_tour = False
    resolved_player = None
    resolved_opp = None
    for tour in tours:
        cp = oc.v8_resolve_player_name(player, tour)
        co = oc.v8_resolve_player_name(opponent_raw, tour)
        if cp:
            resolved_player = cp
        if co:
            resolved_opp = co
        if cp and co:
            passed_any_tour = True
            break

    if passed_any_tour:
        after_recovered += 1
        if len(examples_recovered) < 15:
            examples_recovered.append((player, opponent_raw, resolved_player, resolved_opp))
    else:
        after_still_rejected += 1
        examples_still_failed.append((player, opponent_raw, resolved_player, resolved_opp))

print("=" * 60)
print("BEFORE FIX: ", before_rejected, "rejected")
print("AFTER FIX:  ", after_recovered, "recovered  /  ", after_still_rejected, "still rejected")
print("=" * 60)
print()
print("EXAMPLES RECOVERED:")
for p, o_raw, rp, ro in examples_recovered:
    print(f"  {p!r} vs {o_raw!r}  ->  resolved as {rp!r} vs {ro!r}")

if examples_still_failed:
    print()
    print("STILL REJECTED (examine):")
    for p, o_raw, rp, ro in examples_still_failed[:15]:
        print(f"  {p!r} vs {o_raw!r}  ->  player_resolved={rp!r}  opp_resolved={ro!r}")

print()
print("DONE_REPLAY")
