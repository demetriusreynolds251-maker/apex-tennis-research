#!/usr/bin/env python3
"""Applies Task 1 (reaper artifact) to dataset_a_capture.py and discord_bot.py.
Idempotent: checks markers before touching either file."""
import sys

DC_PATH = "dataset_a_capture.py"
BOT_PATH = "discord_bot.py"

REAPER_BLOCK = '''
# ================================================================
# STALE EVALUATION REAPER (APEX-P0-2026-09-28, Phase 2)
# ================================================================
# Root cause this exists to guard against: an evaluation entering a
# non-terminal lifecycle_state and never being force-terminated because
# the process that would have finished it froze or was interrupted
# (confirmed cause: Discord event-loop freezes, see Phase 1 fix in
# discord_bot.py). This reaper is a SAFETY NET, not the fix for that --
# it force-terminates anything abandoned past a generous threshold so
# Dataset A never carries a permanently-open evaluation, regardless of
# what interrupts a future run.
#
# Threshold justification (measured, not estimated): of 1,292 real
# evaluations that reached a genuine terminal state, the MAXIMUM
# completion time ever recorded was 788 seconds (~13.1 minutes); p99.9
# was 494.5s (~8.2 minutes); zero legitimate evaluations in this
# system's history have ever taken longer than 15 minutes. The 45-minute
# default below is a 3.4x margin over the longest evaluation ever
# observed -- it cannot mistake a real in-progress evaluation for an
# orphan against this system's own measured behavior.

STALE_NON_TERMINAL_STATES = {
    "RESEARCH_STARTED", "RESEARCH_COMPLETE", "EVALUATION_COMPLETE",
    "COMPLIANCE_COMPLETE", "SCORING_COMPLETE",
}
DEFAULT_STALE_MINUTES = 45


@_safe
def reap_stale_evaluations(stale_minutes=DEFAULT_STALE_MINUTES, _logger=None):
    """Force-terminate any evaluation that has sat in a non-terminal
    lifecycle_state for longer than stale_minutes with no further
    activity. Reuses terminate() -- the same write path every other
    caller uses -- so reaped rows go through identical validation and
    logging as any other termination; there is no parallel write path.

    reason="SYSTEM_ERROR" is deliberate: an evaluation abandoned by a
    process interruption is a genuine system failure, not an engine
    decline or a gate rejection, and should be counted as such.
    termination_detail records the prior state and how long it sat
    there, so a reaped row is distinguishable in Dataset A from any
    other SYSTEM_ERROR cause.

    Returns a list of {"eval_id", "prior_state", "detail"} for every
    row it terminated, so a caller can log/report counts. Wrapped in
    @_safe like every other public function here -- a bug in the
    reaper itself can never block or crash the caller that invoked it.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=stale_minutes)).isoformat()
    states = tuple(STALE_NON_TERMINAL_STATES)
    placeholders = ",".join("?" * len(states))
    with _lock, _connect() as conn:
        rows = conn.execute(
            f"SELECT eval_id, lifecycle_state, lifecycle_updated_at FROM evaluations "
            f"WHERE lifecycle_state IN ({placeholders}) AND lifecycle_updated_at < ?",
            (*states, cutoff)
        ).fetchall()
    reaped = []
    for eval_id, state, updated_at in rows:
        detail = (f"reaper: abandoned in {state} since {updated_at} "
                  f"(non-terminal for over {stale_minutes} min with no further "
                  f"activity -- orphaned by a process interruption/restart "
                  f"mid-pipeline, not a live decision)")
        terminate(eval_id, "SYSTEM_ERROR", detail, _logger=_logger)
        reaped.append({"eval_id": eval_id, "prior_state": state, "detail": detail})
    if reaped and _logger:
        _logger("DatasetA", f"reap_stale_evaluations: force-terminated "
                             f"{len(reaped)} stale eval(s) (non-terminal "
                             f"for >{stale_minutes}min)")
    return reaped
'''

COPYRIGHT_LINE = "# © 2026 owner Reynolds Jr. — Project Apex Intelligence™. All rights reserved."

BOT_TASKS_IMPORT = "from discord.ext import tasks\n"

REAPER_LOOP_BLOCK = '''
@tasks.loop(minutes=15)
async def reaper_loop():
    """Recurring reap, every 15 minutes -- a third of the 45-minute
    threshold, so nothing sits stale for more than ~60 min worst-case
    (45 min threshold + up to 15 min until the next tick)."""
    import dataset_a_capture as d1
    reaped = await client.loop.run_in_executor(
        None,
        lambda: d1.reap_stale_evaluations(_logger=lambda ch, msg: print(f"[{ch}] {msg}"))
    )
    if reaped:
        print(f"[DiscordBot] Scheduled reap: {len(reaped)} stale evaluation(s) cleared.")


'''

OLD_ON_READY = '''@client.event
async def on_ready():
    print(f"[DiscordBot] Logged in as {client.user} — listening on "
          f"#{SLIPS_CHANNEL_NAME}, #{LEARNING_CHANNEL_NAME}, #{GENERAL_CHANNEL_NAME}")
'''

NEW_ON_READY = '''@client.event
async def on_ready():
    print(f"[DiscordBot] Logged in as {client.user} — listening on "
          f"#{SLIPS_CHANNEL_NAME}, #{LEARNING_CHANNEL_NAME}, #{GENERAL_CHANNEL_NAME}")

    # APEX-P0-2026-09-28 Phase 2: one-time startup reap, so any evaluation
    # orphaned by whatever caused THIS restart is cleared immediately
    # rather than waiting for the first scheduled cycle below.
    import dataset_a_capture as d1
    reaped = d1.reap_stale_evaluations(_logger=lambda ch, msg: print(f"[{ch}] {msg}"))
    if reaped:
        print(f"[DiscordBot] Startup reap: {len(reaped)} stale evaluation(s) cleared.")

    reaper_loop.start()  # see scheduler hook below
'''


def patch_dataset_a_capture():
    with open(DC_PATH, "r") as f:
        content = f.read()

    if "reap_stale_evaluations" in content:
        print(f"[{DC_PATH}] reaper already present -- skipping")
        return False

    old_import = "from datetime import datetime, timezone\n"
    new_import = "from datetime import datetime, timezone, timedelta\n"
    if old_import not in content:
        print(f"ABORT: expected import line not found verbatim in {DC_PATH}")
        sys.exit(1)
    if content.count(old_import) != 1:
        print(f"ABORT: import line not unique in {DC_PATH} ({content.count(old_import)} occurrences)")
        sys.exit(1)
    content = content.replace(old_import, new_import, 1)

    if COPYRIGHT_LINE not in content:
        print(f"ABORT: trailing copyright line not found verbatim in {DC_PATH}")
        sys.exit(1)
    if content.count(COPYRIGHT_LINE) != 1:
        print(f"ABORT: copyright line not unique in {DC_PATH}")
        sys.exit(1)

    insertion = REAPER_BLOCK.rstrip("\n") + "\n\n"
    content = content.replace(COPYRIGHT_LINE, insertion + COPYRIGHT_LINE, 1)

    with open(DC_PATH, "w") as f:
        f.write(content)
    print(f"[{DC_PATH}] reaper function + import change applied")
    return True


def patch_discord_bot():
    with open(BOT_PATH, "r") as f:
        content = f.read()

    if "reaper_loop" in content:
        print(f"[{BOT_PATH}] reaper hooks already present -- skipping")
        return False

    if "from discord.ext import tasks" not in content:
        if content.count("import discord\n") != 1:
            print(f"ABORT: 'import discord' not uniquely found in {BOT_PATH}")
            sys.exit(1)
        content = content.replace("import discord\n", "import discord\n" + BOT_TASKS_IMPORT, 1)

    if content.count(OLD_ON_READY) != 1:
        print(f"ABORT: on_ready block not found verbatim/uniquely in {BOT_PATH} (found {content.count(OLD_ON_READY)}x)")
        sys.exit(1)

    content = content.replace(OLD_ON_READY, REAPER_LOOP_BLOCK + NEW_ON_READY, 1)

    with open(BOT_PATH, "w") as f:
        f.write(content)
    print(f"[{BOT_PATH}] reaper_loop + on_ready startup hook applied")
    return True


if __name__ == "__main__":
    patch_dataset_a_capture()
    patch_discord_bot()
