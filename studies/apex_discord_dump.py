#!/usr/bin/env python3
"""
APEX-DISCORD-DUMP-2026-08-26
Pull every message the bot itself posted to Discord since a start date and
write them to a text file, so the picks can be graded by hand.

READ-ONLY. Connects with the bot's own token, reads history, disconnects.
Posts nothing, reacts to nothing, changes nothing.

Token lookup order:
  1. $DISCORD_TOKEN / $DISCORD_BOT_TOKEN / $BOT_TOKEN
  2. any EnvironmentVariables key in ~/Library/LaunchAgents/com.apex.discordbot.plist
     whose name contains TOKEN or DISCORD
  3. a token-shaped literal inside discord_bot.py (the hardcoded one)

USAGE (from ~/openclaw):
    python3 apex_discord_dump.py                     # since Sunday 2026-08-23 00:00 Central
    python3 apex_discord_dump.py --since 2026-08-22  # any date, Central
    python3 apex_discord_dump.py --all-authors       # include your own messages too

OUTPUT
    discord_dump_<since>_to_<today>.txt   every message, full text, embeds flattened
    discord_picks_<since>_to_<today>.txt  only the lines that look like picks
"""
import argparse
import asyncio
import os
import plistlib
import re
import sys
from datetime import datetime, timedelta, timezone

PLIST = os.path.expanduser("~/Library/LaunchAgents/com.apex.discordbot.plist")
BOT_FILE = "discord_bot.py"
TOKEN_RE = re.compile(r"[MN][A-Za-z\d_-]{23,}\.[A-Za-z\d_-]{6}\.[A-Za-z\d_-]{27,}")
CT = timezone(timedelta(hours=-5))  # Central Daylight Time

PICK_WORDS = re.compile(
    r"\b(MORE|LESS|OVER|UNDER|PLAY|PASS|NO PLAY|ELITE|GOOD|CAUTION|LEAN|GREEN|YELLOW|ENGINE|VERDICT|GRADE)\b",
    re.I,
)


def find_token(use_env=False):
    # The launchd plist holds the token the LIVE bot runs with. A shell variable
    # can be stale (pre-reset), so it is only used when asked for with --env.
    if use_env:
        for k in ("DISCORD_TOKEN", "DISCORD_BOT_TOKEN", "BOT_TOKEN"):
            v = os.environ.get(k)
            if v and TOKEN_RE.search(v):
                return v.strip(), f"env {k}"
    try:
        with open(PLIST, "rb") as fh:
            d = plistlib.load(fh)
        env = d.get("EnvironmentVariables") or {}
        for k, v in env.items():
            if ("TOKEN" in k.upper() or "DISCORD" in k.upper()) and TOKEN_RE.search(str(v)):
                return str(v).strip(), f"plist key {k}"
        for k, v in env.items():
            if TOKEN_RE.search(str(v)):
                return str(v).strip(), f"plist key {k}"
    except Exception:
        pass
    try:
        src = open(BOT_FILE, encoding="utf-8", errors="ignore").read()
        m = TOKEN_RE.search(src)
        if m:
            return m.group(0), f"literal in {BOT_FILE}"
    except Exception:
        pass
    return None, None


def flatten(msg):
    """Message text plus every embed field, one string."""
    parts = []
    if msg.content:
        parts.append(msg.content)
    for e in msg.embeds:
        if e.title:
            parts.append(f"[embed title] {e.title}")
        if e.description:
            parts.append(e.description)
        for f in e.fields:
            parts.append(f"[{f.name}] {f.value}")
        if e.footer and e.footer.text:
            parts.append(f"[footer] {e.footer.text}")
    for a in msg.attachments:
        parts.append(f"[attachment] {a.filename}")
    return "\n".join(parts).strip()


async def run(token, since_utc, all_authors, out_all, out_picks):
    import discord

    intents = discord.Intents.default()
    intents.message_content = True
    client = discord.Client(intents=intents)
    done = asyncio.Event()
    stats = {"channels": 0, "messages": 0, "pick_lines": 0}

    @client.event
    async def on_ready():
        try:
            fa = open(out_all, "w", encoding="utf-8")
            fp = open(out_picks, "w", encoding="utf-8")
            fa.write(f"# bot: {client.user}   since: {since_utc.astimezone(CT):%Y-%m-%d %H:%M} CT\n")
            fp.write(f"# candidate pick lines since {since_utc.astimezone(CT):%Y-%m-%d} CT\n")
            for guild in client.guilds:
                for ch in guild.text_channels:
                    perms = ch.permissions_for(guild.me)
                    if not perms.read_message_history:
                        continue
                    stats["channels"] += 1
                    rows = []
                    try:
                        async for m in ch.history(after=since_utc, limit=None, oldest_first=True):
                            if not all_authors and m.author.id != client.user.id:
                                continue
                            text = flatten(m)
                            if not text:
                                continue
                            rows.append((m.created_at, m.author.display_name, text))
                    except discord.Forbidden:
                        continue
                    if not rows:
                        continue
                    fa.write(f"\n\n===== #{ch.name} ({guild.name}) — {len(rows)} message(s) =====\n")
                    for ts, who, text in rows:
                        ct = ts.astimezone(CT).strftime("%a %m-%d %I:%M %p")
                        stats["messages"] += 1
                        fa.write(f"\n--- {ct} CT · {who} ---\n{text}\n")
                        pick_lines = [ln for ln in text.splitlines() if PICK_WORDS.search(ln)]
                        if pick_lines:
                            fp.write(f"\n--- {ct} CT · #{ch.name} ---\n")
                            for ln in pick_lines:
                                fp.write(ln.strip() + "\n")
                                stats["pick_lines"] += 1
            fa.close()
            fp.close()
        finally:
            done.set()

    async def runner():
        try:
            await client.start(token)
        except Exception as e:
            print(f"ERROR connecting: {type(e).__name__}: {e}")
            done.set()

    task = asyncio.create_task(runner())
    await done.wait()
    await client.close()
    try:
        await task
    except Exception:
        pass
    return stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2026-08-23", help="start date, Central (YYYY-MM-DD)")
    ap.add_argument("--all-authors", action="store_true", help="include human messages too")
    ap.add_argument("--env", action="store_true", help="use $DISCORD_BOT_TOKEN from the shell instead of the plist")
    a = ap.parse_args()

    try:
        import discord  # noqa: F401
    except ImportError:
        print("discord.py is not importable with this python3. Run with the same python the bot uses.")
        return 1

    token, where = find_token(use_env=a.env)
    if not token:
        print("No bot token found in the plist or discord_bot.py. Try --env, or set DISCORD_TOKEN.")
        return 1
    print(f"token: found via {where}")

    since_ct = datetime.strptime(a.since, "%Y-%m-%d").replace(tzinfo=CT)
    since_utc = since_ct.astimezone(timezone.utc)
    today = datetime.now(CT).strftime("%Y-%m-%d")
    out_all = f"discord_dump_{a.since}_to_{today}.txt"
    out_picks = f"discord_picks_{a.since}_to_{today}.txt"

    stats = asyncio.run(run(token, since_utc, a.all_authors, out_all, out_picks))
    print(f"channels read: {stats['channels']}   messages: {stats['messages']}   pick-looking lines: {stats['pick_lines']}")
    for f in (out_all, out_picks):
        if os.path.exists(f):
            print(f"wrote {f}")
    if stats["messages"] == 0:
        print("Nothing came back. If the login worked, the bot may lack Read Message History "
              "or the Message Content intent is off in the Developer Portal.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
