import sys, json
sys.path.insert(0, '.')
import openclaw_core as core
import apex_edge_tracker as aet
import discord_bot as db

# Suppress only the external/production side-effects (Discord post, archive
# write, membership-log write). Everything else -- scrape, Gate 11, scoring,
# correlation gate, rule 28 dedup -- runs exactly as production code does.
core.send_discord = lambda *a, **k: None
core._archive_picks = lambda *a, **k: None
aet.capture_board_membership = lambda *a, **k: None

result = db._fetch_publish_all_render_inner(core.get_system_dates(), lambda *a, **k: None)

out = {
    "ok": result.get("ok"),
    "error": result.get("error"),
    "raw_total": result.get("raw_total"),
    "deduped_total": result.get("deduped_total"),
    "data_source": result.get("data_source"),
    "engine_evaluated_raw": result.get("engine_evaluated_raw"),
    "pre_engine_drops": result.get("pre_engine_drops"),
    "declined_exact": result.get("declined_exact"),
    "decline_breakdown": result.get("decline_breakdown"),
    "demonlock_dropped": result.get("demonlock_dropped"),
}
with open('/tmp/live_fetch_result.json', 'w') as f:
    json.dump(out, f, indent=1, default=str)
print(json.dumps(out, indent=1, default=str))
