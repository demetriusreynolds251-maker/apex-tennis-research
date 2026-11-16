#!/usr/bin/env python3
"""APEX-VAL-001 (ALIS-L4 Phase 4) -- recommendation validation loop.
INFRASTRUCTURE: built. VALIDATION: not started.
Judges a change by the metric matching its purpose:
  Purpose 1 (Evaluation Quality) -> calibration + projection MAE
  Purpose 2 (Selection Quality)  -> score-band separation
Never marks a lesson Validated without a real before/after at sufficient n.
"""
import os, sys, json, glob, argparse, statistics
from datetime import datetime
import apex_projection_analysis as PA
try:
    import apex_error_registry as REG
except ImportError:
    REG = None   # Phase 3 optional at runtime

VAL = "apex_learning_system/VALIDATION_LOOP.md"
ADOPT = "apex_learning_system/ADOPTIONS.json"
MIN_N = 100          # settled picks required per side of a comparison
MIN_TOP = 20         # top-band picks required for a separation claim

def load_adoptions():
    return json.load(open(ADOPT)) if os.path.exists(ADOPT) else {"adoptions": []}

def save_adoptions(d):
    os.makedirs(os.path.dirname(ADOPT), exist_ok=True)
    json.dump(d, open(ADOPT, "w"), indent=1)

def adopt(key, purpose, version, note):
    """Record that a recommendation was adopted, with the scorer version that
    contains it. Phase 4 compares versions before/after this point."""
    d = load_adoptions()
    d["adoptions"].append({"lesson_key": key, "purpose": purpose, "version": version,
                           "note": note, "adopted_ts": datetime.now().isoformat(timespec="seconds"),
                           "outcome": "WAITING FOR DATA"})
    save_adoptions(d)
    print("adopted: %s (purpose %s, version %s)" % (key, purpose, version))
    return 0

def _selection_by_version():
    """Settled snapshot picks grouped by scorer version -> separation per version."""
    try:
        import apex_selection_quality as SQ
    except Exception:
        return {}
    oc = SQ._outcomes()
    out = {}
    for f in sorted(glob.glob(os.path.join(SQ.SEL_DIR, "board_*.json"))):
        doc = json.load(open(f))
        v = doc.get("scorer_version", "?")
        for p in doc["picks"]:
            k = (p.get("match_id"), (p.get("player") or "").lower(), p.get("category"))
            if k in oc and oc[k] is not None:
                out.setdefault(v, []).append({**p, "hit": oc[k]})
    return out

def _sep(rows):
    bands = {}
    for r in rows: bands.setdefault(r.get("score_band"), []).append(r)
    order = [b for b in ["95+","90-94","85-89","80-84","75-79","70-74","65-69","60-64","55-59","50-54","<50"] if b in bands]
    if len(order) < 2: return None, None, 0
    rate = lambda rs: sum(1 for x in rs if x["hit"]) / len(rs)
    seq = [(b, rate(bands[b])) for b in order]
    top_n = sum(len(bands[b]) for b in order[:2])
    mono = all(seq[i][1] >= seq[i+1][1] for i in range(len(seq)-1))
    return 100*(seq[0][1] - seq[-1][1]), mono, top_n

def report(write=False):
    L = ["## Validation loop  (ALIS-L4 Phase 4)",
         "INFRASTRUCTURE: BUILT · VALIDATION: NOT STARTED", ""]
    ad = load_adoptions()["adoptions"]
    L += ["### Adoptions", "| lesson | purpose | version | adopted | outcome |", "|---|---|---|---|---|"]
    if ad:
        for a in ad:
            L.append("| `%s` | %s | %s | %s | %s |" % (a["lesson_key"], a["purpose"], a["version"],
                     a["adopted_ts"][:10], a["outcome"]))
    else:
        L.append("| — | — | — | — | **WAITING FOR DATA — no recommendation adopted yet** |")
    # Purpose 2: selection separation by version
    L += ["", "### Purpose 2 — Selection Quality by scorer version",
          "| version | settled n | separation | monotonic | top-band n | comparable? |", "|---|---|---|---|---|---|"]
    sv = _selection_by_version()
    if not sv:
        L.append("| — | 0 | — | — | — | **WAITING FOR DATA** |")
    else:
        for v, rows in sorted(sv.items()):
            sep, mono, topn = _sep(rows)
            ok = len(rows) >= MIN_N and topn >= MIN_TOP
            L.append("| %s | %d | %s | %s | %d | %s |" % (v, len(rows),
                     ("%+.1f pts" % sep) if sep is not None else "—",
                     ("YES" if mono else "NO") if mono is not None else "—", topn,
                     "yes" if ok else "INSUFFICIENT EVIDENCE (need n>=%d, top>=%d)" % (MIN_N, MIN_TOP)))
        if len(sv) < 2:
            L.append("\n**Version comparison:** INSUFFICIENT EVIDENCE — only %d scorer version on record." % len(sv))
    # Purpose 1: projection quality trend
    R = PA.rows()
    L += ["", "### Purpose 1 — Evaluation Quality"]
    if not R:
        L.append("**WAITING FOR DATA** — no settled picks with projections.")
    else:
        mae = statistics.mean(r["abs_err"] for r in R)
        L.append("Projection MAE: **%.2f** over n=%d · %s" % (mae, len(R),
                 "INSUFFICIENT EVIDENCE for a before/after claim (need >=%d per side)" % MIN_N if len(R) < MIN_N else "comparable"))
    L += ["", "### Validation rule",
          "A lesson becomes **Validated** only when a version containing its fix beats the version",
          "without it, on the metric matching its purpose, with n>=%d per side. No other path exists." % MIN_N,
          "", "**Lessons validated to date:** NOT AVAILABLE — no comparison has met the gate."]
    txt = "\n".join(L); print(txt)
    if write:
        os.makedirs(os.path.dirname(VAL), exist_ok=True)
        hdr = "" if os.path.exists(VAL) else "# VALIDATION LOOP\nAppend-only.\n"
        open(VAL, "a", encoding="utf-8").write(hdr + "\n---\n# Entry %s\n%s\n" % (
            datetime.now().strftime("%Y-%m-%d %H:%M"), txt))
        print("\nappended -> %s" % VAL)
    return 0

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--adopt", nargs=4, metavar=("LESSON_KEY","PURPOSE","VERSION","NOTE"))
    a_ = ap.parse_args()
    sys.exit(adopt(*a_.adopt) if a_.adopt else report(write=a_.write) if a_.report else ap.print_help())
