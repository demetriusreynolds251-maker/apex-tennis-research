"""
test_intake_artifact_fix.py -- 2026-09-28
APEX-HOTFIX FIX #3: proves resolve_player_name() in openclaw_v8_api.py
strips "@ " / "vs " / "vs. " intake artifacts BEFORE any lookup, so
"@ Kamil Majchrzak", "vs Linda Noskova", "vs. Jaume Munar" all resolve
identically to their clean, un-prefixed form -- fixing the confirmed
root cause of 124/178 real Gate 11 rejections in this audit.

No network calls: _api_get is monkeypatched to raise if it is ever
reached, so a passing test PROVES normalization happened early enough
that the local known-names lookup succeeded on the cleaned name -- not
that some later fallback happened to paper over a dirty name.

Run:  python3 test_intake_artifact_fix.py   -> ALL CHECKS PASSED
"""
import sys
import openclaw_v8_api as V

fails = []


def check(cond, msg):
    print(("  PASS  " if cond else "  FAIL  ") + msg)
    if not cond:
        fails.append(msg)


# ---- isolate: no cache, no network, a small fake local known-names table
KNOWN = {
    "atp": {
        "kamil majchrzak": "Kamil Majchrzak",
        "jaume munar": "Jaume Munar",
    },
    "wta": {
        "linda noskova": "Linda Noskova",
    },
}

_api_calls = []


def _fake_api_get(endpoint, params=None):
    _api_calls.append(endpoint)
    raise AssertionError(f"_api_get() reached for endpoint={endpoint!r} -- "
                          f"normalization failed to clean the name before lookup")


def _fake_cache_get(key, ttl_hours):
    return None


def _fake_cache_set(key, data):
    pass


def _fake_log(tag, msg):
    print(f"    [{tag}] {msg}")


def _fake_load_known_names():
    return KNOWN


V._api_get = _fake_api_get
V._cache_get = _fake_cache_get
V._cache_set = _fake_cache_set
V.log = _fake_log
V._load_known_names = _fake_load_known_names

print("EQUIVALENCE: prefixed forms resolve identically to the clean form")
cases = [
    ("@ Kamil Majchrzak",  "Kamil Majchrzak",  "atp", "Kamil Majchrzak"),
    ("@Kamil Majchrzak",   "Kamil Majchrzak",  "atp", "Kamil Majchrzak"),
    ("vs Linda Noskova",   "Linda Noskova",    "wta", "Linda Noskova"),
    ("vs. Jaume Munar",    "Jaume Munar",      "atp", "Jaume Munar"),
    ("VS Jaume Munar",     "Jaume Munar",      "atp", "Jaume Munar"),
    ("  @  Kamil Majchrzak  ", "Kamil Majchrzak", "atp", "Kamil Majchrzak"),
]
for dirty, clean, tour, expected in cases:
    r_dirty = V.resolve_player_name(dirty, tour)
    r_clean = V.resolve_player_name(clean, tour)
    check(r_dirty == expected, f"'{dirty}' -> '{r_dirty}' (expected '{expected}')")
    check(r_clean == expected, f"'{clean}' -> '{r_clean}' (expected '{expected}')")
    check(r_dirty == r_clean, f"'{dirty}' and '{clean}' resolve identically")

print("\nNO NETWORK CALLS were needed for any of the above:")
check(len(_api_calls) == 0, f"_api_get() was never reached (calls: {_api_calls})")

print("\nUNCHANGED: plain names with no artifact still resolve normally")
check(V.resolve_player_name("Kamil Majchrzak", "atp") == "Kamil Majchrzak",
      "plain 'Kamil Majchrzak' unaffected")

print("\nSAFETY: mid-name 'vs'/'@' substrings are NOT stripped (leading-only)")
KNOWN["atp"]["vsevolod versal"] = "Vsevolod Versal"  # starts with 'vs' but is not the artifact
r = V.resolve_player_name("Vsevolod Versal", "atp")
check(r == "Vsevolod Versal", f"'Vsevolod Versal' resolves untouched, got '{r}'")

print()
if fails:
    print(f"{len(fails)} FAILURE(S):")
    for f in fails:
        print("  - " + f)
    sys.exit(1)
print("ALL CHECKS PASSED.")
