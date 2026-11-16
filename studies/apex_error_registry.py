#!/usr/bin/env python3
"""APEX-REG-001 (ALIS-L4 Phase 3) -- error registry, lesson state machine, knowledge base.
INFRASTRUCTURE: built. VALIDATION: not started.
States: Hypothesis -> Observed -> Supported -> Validated -> Retired.
Validated is NEVER assigned here; only Phase 4 can set it.
"""
import os, sys, json, argparse, statistics
from datetime import datetime
import apex_projection_analysis as PA
import apex_root_cause as RC

ERR = "apex_learning_system/ERROR_REGISTRY.md"
LES = "apex_learning_system/LESSON_REGISTRY.json"
KB  = "apex_learning_system/KNOWLEDGE_BASE.md"
GATE_OBSERVED, GATE_SUPPORTED = 3, 8

def state_for(n, validated=False, retired=False):
    if retired: return "Retired"
    if validated: return "Validated"
    if n >= GATE_SUPPORTED: return "Supported"
    if n >= GATE_OBSERVED: return "Observed"
    return "Hypothesis"

def detect_patterns():
    R = PA.rows()
    if not R: return []
    losses = RC.classify(R)
    pats = {}
    def add(key, desc, cause, rec):
        p = pats.setdefault(key, {"key": key, "desc": desc, "n": 0, "cause": cause, "rec": rec})
        p["n"] += 1
    cats = {}
    for r in R: cats.setdefault(r["category"], []).append(r)
    for c, rs in cats.items():
        if len(rs) >= 5:
            b = statistics.mean(x["err"] for x in rs)
            if abs(b) >= 1.0:
                for _ in range(len(rs)):
                    add("bias:%s" % c,
                        "%s projections run %s by %.2f on average" % (c, "low" if b > 0 else "high", abs(b)),
                        "Systematic projection bias in %s" % c,
                        "Adjust %s projection weighting (Purpose 1)" % c)
    for x in losses:
        add("cause:%s:%s" % (x["cause"], x["category"]),
            "%s losses classified %s" % (x["category"], x["cause"]),
            x["cause"], "Investigate %s in %s" % (x["cause"], x["category"]))
    return sorted(pats.values(), key=lambda p: -p["n"])

def load_lessons():
    return json.load(open(LES)) if os.path.exists(LES) else {}

def save_lessons(d):
    os.makedirs(os.path.dirname(LES), exist_ok=True)
    json.dump(d, open(LES, "w"), indent=1)

def _ev(n):
    return "Very Low" if n < 5 else "Low" if n < 10 else "Moderate" if n < 25 else "Strong" if n < 100 else "Proven"

def build(write=False):
    pats = detect_patterns()
    les = load_lessons()
    L = ["## Error registry / lessons  (ALIS-L4 Phase 3)",
         "INFRASTRUCTURE: BUILT / VALIDATION: NOT STARTED", ""]
    if not pats:
        L += ["**WAITING FOR DATA** -- no settled patterns detected yet.",
              "Promotion to Observed needs %d occurrences." % GATE_OBSERVED]
    else:
        L += ["| pattern | occ | state | evidence | root cause | recommendation |", "|---|---|---|---|---|---|"]
        for p in pats:
            prev = les.get(p["key"], {})
            st = state_for(p["n"], prev.get("validated", False), prev.get("retired", False))
            L.append("| `%s` | %d | **%s** | %s | %s | %s |" % (p["key"], p["n"], st, _ev(p["n"]), p["cause"], p["rec"]))
            les[p["key"]] = {"desc": p["desc"], "occurrences": p["n"], "state": st,
                             "cause": p["cause"], "recommendation": p["rec"],
                             "validated": prev.get("validated", False),
                             "retired": prev.get("retired", False),
                             "adoption_status": prev.get("adoption_status", "not adopted"),
                             "outcome_after_adoption": prev.get("outcome_after_adoption", "NOT AVAILABLE"),
                             "first_seen": prev.get("first_seen", datetime.now().strftime("%Y-%m-%d")),
                             "last_seen": datetime.now().strftime("%Y-%m-%d")}
        L += ["", "**Gates:** Hypothesis <%d occ / Observed >=%d / Supported >=%d / Validated only via Phase 4."
              % (GATE_OBSERVED, GATE_OBSERVED, GATE_SUPPORTED)]
    K = ["# KNOWLEDGE BASE (generated %s)" % datetime.now().strftime("%Y-%m-%d %H:%M"), "",
         "## Known Strengths", "NOT AVAILABLE -- requires validated positive findings.", "",
         "## Known Weaknesses"]
    weak = [p for p in pats if p["n"] >= GATE_OBSERVED]
    K += (["- %s (%d occ, %s)" % (p["desc"], p["n"], _ev(p["n"])) for p in weak] if weak
          else ["INSUFFICIENT EVIDENCE -- nothing has reached Observed."])
    K += ["", "## Open Questions",
          "- Does the APEX score separate winners from losers? (Phase 0)",
          "- Are projections biased by category? (Phase 1)",
          "- Model error vs variance share? (Phase 2)", "",
          "## Validated Fixes", "NOT AVAILABLE -- requires Phase 4 evidence.", "",
          "## Failed Fixes", "NOT AVAILABLE -- no fix adopted and measured.", "",
          "## Recurring Failure Patterns"]
    K += (["- `%s` x%d [%s]" % (p["key"], p["n"], state_for(p["n"])) for p in pats[:10]] if pats else ["WAITING FOR DATA"])
    txt = "\n".join(L); print(txt)
    if write:
        os.makedirs(os.path.dirname(ERR), exist_ok=True)
        hdr = "" if os.path.exists(ERR) else "# ERROR REGISTRY\nAppend-only.\n"
        open(ERR, "a", encoding="utf-8").write(hdr + "\n---\n# Entry %s\n%s\n" % (datetime.now().strftime("%Y-%m-%d %H:%M"), txt))
        open(KB, "w", encoding="utf-8").write("\n".join(K) + "\n")
        save_lessons(les)
        print("\nwrote -> %s, %s, %s" % (ERR, KB, LES))
    return 0

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--write", action="store_true")
    a_ = ap.parse_args()
    sys.exit(build(write=a_.write) if a_.build else ap.print_help())
