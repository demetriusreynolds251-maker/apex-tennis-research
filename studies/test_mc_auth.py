import sys, os, threading, base64, http.client, time
sys.path.insert(0, "/home/claude")

# ── Test 1: env vars NOT set -- server must refuse everything ──
os.environ.pop("MC_AUTH_USER", None)
os.environ.pop("MC_AUTH_PASS", None)

import importlib
import openclaw_mission_control as mc
importlib.reload(mc)

from http.server import HTTPServer
server = HTTPServer(("127.0.0.1", 18788), mc.H)
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
time.sleep(0.3)

conn = http.client.HTTPConnection("127.0.0.1", 18788, timeout=5)
conn.request("GET", "/")
resp = conn.getresponse()
body = resp.read()
assert resp.status == 401, f"FAIL: expected 401 with no env vars set, got {resp.status}"
assert b"MC_AUTH_USER" in body, "FAIL: should explain the missing env vars, not just say 'unauthorized'"
print("PASS: with no MC_AUTH_USER/MC_AUTH_PASS set, every request is refused with a clear explanation")
conn.close()
server.shutdown()

# ── Test 2: env vars set -- correct creds pass, wrong creds are rejected ──
os.environ["MC_AUTH_USER"] = "testop"
os.environ["MC_AUTH_PASS"] = "correcthorsebatterystaple"
importlib.reload(mc)

server2 = HTTPServer(("127.0.0.1", 18789), mc.H)
thread2 = threading.Thread(target=server2.serve_forever, daemon=True)
thread2.start()
time.sleep(0.3)

# No credentials at all -> 401
conn2 = http.client.HTTPConnection("127.0.0.1", 18789, timeout=5)
conn2.request("GET", "/")
resp2 = conn2.getresponse(); resp2.read()
assert resp2.status == 401, f"FAIL: no credentials should be 401, got {resp2.status}"
assert resp2.getheader("WWW-Authenticate") is not None, "FAIL: missing WWW-Authenticate header (browser won't prompt for login without this)"
print("PASS: request with zero credentials correctly rejected, WWW-Authenticate header present")
conn2.close()

# Wrong password -> 401
conn3 = http.client.HTTPConnection("127.0.0.1", 18789, timeout=5)
wrong = base64.b64encode(b"testop:wrongpassword").decode()
conn3.request("GET", "/", headers={"Authorization": f"Basic {wrong}"})
resp3 = conn3.getresponse(); resp3.read()
assert resp3.status == 401, f"FAIL: wrong password should be 401, got {resp3.status}"
print("PASS: wrong password correctly rejected")
conn3.close()

# Correct credentials -> 200 (reaches the real route)
conn4 = http.client.HTTPConnection("127.0.0.1", 18789, timeout=5)
correct = base64.b64encode(b"testop:correcthorsebatterystaple").decode()
conn4.request("GET", "/", headers={"Authorization": f"Basic {correct}"})
resp4 = conn4.getresponse(); resp4.read()
assert resp4.status == 200, f"FAIL: correct credentials should reach the real page (200), got {resp4.status}"
print("PASS: correct credentials reach the real dashboard")
conn4.close()

# POST is protected too
conn5 = http.client.HTTPConnection("127.0.0.1", 18789, timeout=5)
conn5.request("POST", "/api/slip_review_reject", body=b'{"id":1}')
resp5 = conn5.getresponse(); resp5.read()
assert resp5.status == 401, f"FAIL: unauthenticated POST should also be 401, got {resp5.status}"
print("PASS: POST routes are protected too, not just GET")
conn5.close()

server2.shutdown()
print("\nALL AUTH TESTS PASSED")
