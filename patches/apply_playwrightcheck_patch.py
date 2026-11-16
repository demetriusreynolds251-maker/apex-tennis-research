"""
APEX-PLAYWRIGHTCHECK-2026-10-07 (owner, requested)

Investigation found the "Chrome remote debugging / port 9222" check in
system_verification() tests for an architecture openclaw_core.py's OWN
APEX-FETCHPIPE-2026-09-30 note already retired: fetch_props_playwright()
now launches and owns its own Chrome against CHROME_PRIZEPICKS_PROFILE
(~/.chrome-prizepicks, confirmed present and logged in) -- it never
connects to a manually-launched Chrome on :9222 any more. A launchd
service to auto-start Chrome on that port would start a browser nothing
reads from.

This patch:
  1. Replaces the stale port-9222 ping with a check for the thing the
     fallback actually depends on today: the persistent profile directory.
  2. Updates the failed/warned action text to match (drops the
     "start Chrome with --remote-debugging-port" instruction).
Playwright itself stays flagged as "optional" (fallback-only, prop
collection path) since partner-API is primary and Playwright failure is
non-fatal (API-only fetching keeps working) -- that framing was already
correct and is untouched.
"""
PATH = "openclaw_core.py"
with open(PATH) as f:
    src = f.read()

anchor1 = '''    # 5 — Playwright (optional)
    try:
        import playwright
        checks.append(("Playwright installed", "✅"))
        try:
            r = requests.get(f"http://localhost:{PLAYWRIGHT_PORT}/json", timeout=3)
            checks.append(("Chrome remote debugging", "✅ Browser connected"))
        except:
            checks.append(("Chrome remote debugging",
                           f"⚠️ Not running — start Chrome with --remote-debugging-port={PLAYWRIGHT_PORT}"))
    except ImportError:
        checks.append(("Playwright",
                       "⚠️ Not installed — run: pip install playwright && playwright install chromium"))'''
assert src.count(anchor1) == 1, f"anchor1 found {src.count(anchor1)} times"

replacement1 = '''    # 5 — Playwright (optional fallback for prop collection only; not used
    # by the learning system or settlement). APEX-PLAYWRIGHTCHECK-2026-10-07:
    # retired the port-9222 ping -- APEX-FETCHPIPE-2026-09-30 already moved
    # fetch_props_playwright() to launch its own Chrome against
    # CHROME_PRIZEPICKS_PROFILE, so nothing connects to that port any more.
    # The real dependency now is that persistent, logged-in profile existing.
    try:
        import playwright
        checks.append(("Playwright installed", "✅"))
        if Path(CHROME_PRIZEPICKS_PROFILE).exists():
            checks.append(("PrizePicks Chrome profile", "✅ Present (%s)" % CHROME_PRIZEPICKS_PROFILE))
        else:
            checks.append(("PrizePicks Chrome profile",
                           "⚠️ Not found — first Playwright fallback run will create and need login at %s"
                           % CHROME_PRIZEPICKS_PROFILE))
    except ImportError:
        checks.append(("Playwright",
                       "⚠️ Not installed — run: pip install playwright && playwright install chromium"))'''

src = src.replace(anchor1, replacement1, 1)

anchor2 = '''            "1. Fill in config.json with your tokens and keys",
            "2. Run: pip install playwright && playwright install chromium",
            "3. Start Chrome with --remote-debugging-port=9222 for Playwright",
            "4. Check SETUP_INSTRUCTIONS.txt for step-by-step guidance",'''
assert src.count(anchor2) == 1, f"anchor2 found {src.count(anchor2)} times"
replacement2 = '''            "1. Fill in config.json with your tokens and keys",
            "2. Run: pip install playwright && playwright install chromium",
            "3. Check SETUP_INSTRUCTIONS.txt for step-by-step guidance",'''
src = src.replace(anchor2, replacement2, 1)

anchor3 = '''            "⚠️ items work with reduced functionality",
            "Playwright failure = API-only prop fetching (still works)",'''
assert src.count(anchor3) == 1, f"anchor3 found {src.count(anchor3)} times"
replacement3 = '''            "⚠️ items work with reduced functionality",
            "Playwright is a fallback for prop collection only (not used by learning or settlement) -- partner API is primary, so a missing/stale profile just means API-only fetching until it's refreshed",'''
src = src.replace(anchor3, replacement3, 1)

with open(PATH, "w") as f:
    f.write(src)

print("PATCH APPLIED OK")
