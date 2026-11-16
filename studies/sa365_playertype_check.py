#!/usr/bin/env python3
# Confirm /h2h/playerType/{name} works and what it returns. READ-ONLY.
import json, urllib.parse
from sa365_prematch_probe import get
q = urllib.parse.quote
for name in ("Carlos Alcaraz", "Iga Swiatek", "Nick Beamish", "Mutsumi Uemura"):
    st, p = get(f"/h2h/playerType/{q(name)}")
    print(name, "-> HTTP", st, json.dumps(p)[:200])
