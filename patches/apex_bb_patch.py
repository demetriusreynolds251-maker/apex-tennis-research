#!/usr/bin/env python3
"""
APEX-BB-001 -- Best Bets ranking + Bo5 card-side LOW forcing
============================================================
apex_edge_tracker.py
  A. discord_header gains bo5 flag -> forces ATTENTION: LOW (BO5-FWD-001)
  B. apex_score() + best_bets_block() -- evidence-weighted 0-100 ranking
  C. selftest additions (Bo5 cap/exclusion, evidence-beats-prior, render)
openclaw_core.py
  D. _apex_engine_pick dict carries apex_best_of
  E. _apex_engine_card passes bo5 to the header
  F. output_agent renders Best Bets below normal picks, above the footer
Run:  cd ~/openclaw && python3 apex_bb_patch.py [--dry-run]
"""
import hashlib, os, shutil, sys, subprocess
from datetime import datetime

MARKER = "APEX-BB-001"
sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()

TRACKER_FUNCS = r'''

# ================================================================= APEX-BB-001
def apex_score(prob, cat, bo5, rec):
    """Evidence-weighted score 0-100. Probability anchors; forward evidence
    (sample-weighted) adjusts; structural prior shrinks as evidence grows;
    the pick's own probability band and attention close it out. Bo5 capped."""
    prob = float(prob or 0.0)
    cs = rec["cats"].get(cat) or _stat([])
    n = cs["n"]; w = min(n / 25.0, 1.0)
    up, down = [], []
    score = 55.0 * max(0.0, min(1.0, (prob - BREAK_EVEN) / (0.85 - BREAK_EVEN)))
    if prob >= 0.65: up.append("stated %d%%" % round(prob * 100))
    if prob <= 0.55: down.append("thin stated probability %d%%" % round(prob * 100))
    if n >= 5 and cs["cal_pts"] is not None:
        ev = 20.0 * w * max(-1.0, min(1.0, cs["cal_pts"] / 0.10))
        score += ev
        (up if ev >= 0 else down).append("%s %s fwd, cal %+.1f (n=%d)"
            % (LABEL.get(cat, cat), _rs(cs), cs["cal_wins"] or 0, n))
    elif n < 5:
        down.append("%s barely tested (n=%d)" % (LABEL.get(cat, cat), n))
    g = group_of(cat)
    prior = {"rate_model": 8.0, "sim_derived": 3.0, "total_games": -8.0}.get(g, 0.0)
    pr = prior * (1.0 - w) * (0.5 if n < 5 else 1.0)
    score += pr
    if pr >= 2: up.append("rate-model category (research prior)")
    if pr <= -2: down.append("total games market territory (research prior)")
    for name, blo, bhi in BUCKETS:
        if blo <= prob < bhi:
            for bn, bw_, bl_, bstat in rec["buckets"]:
                if bn == name and (bw_ + bl_) >= 3 and bstat:
                    br = bw_ / (bw_ + bl_)
                    adj = 10.0 * min((bw_ + bl_) / 10.0, 1.0) * max(-1.0, min(1.0, (br - bstat) / 0.10))
                    score += adj
                    (up if adj >= 2 else down if adj <= -2 else []).append(
                        "%s band %d-%d vs ~%d%% stated" % (name, bw_, bl_, round(bstat * 100)))
            break
    lvl, _w = attention(cat, prob, rec)
    if bo5: lvl = "LOW"
    score += {"HIGH": 5.0, "MEDIUM": 2.0}.get(lvl, 0.0)
    if bo5:
        score = min(score, 49.0)
        down.append("Bo5 experimental -- LOW until 25 settled (BO5-FWD-001)")
    score = max(0.0, min(100.0, score))
    ev_label = ("Very Low" if n < 5 else "Low" if n < 10 else
                "Moderate" if n < 25 else "Strong" if n < 100 else "Proven")
    return round(score), ev_label, lvl, up, down


def best_bets_block(picks, rec=None):
    """APEX-BB-001: rendered Best Bets section. picks: dicts with player,
    category, prob, line, direction, bo5. Never raises; '' on any problem."""
    try:
        rec = rec or records()
        scored = []
        for p in picks:
            cat = p.get("category") or ""
            if not cat:
                continue
            sc, ev, lvl, up, down = apex_score(p.get("prob"), cat, bool(p.get("bo5")), rec)
            cs = rec["cats"].get(cat) or _stat([])
            scored.append({"p": p, "cat": cat, "score": sc, "ev": ev, "lvl": lvl,
                           "up": up, "down": down, "rs": _rs(cs), "bo5": bool(p.get("bo5"))})
        if not scored:
            return ""
        scored.sort(key=lambda d: -d["score"])
        icon = {"HIGH": "\U0001F7E2", "MEDIUM": "\U0001F7E1", "LOW": "\u26aa"}
        def line1(i, d):
            p = d["p"]
            return ("**#%d %s** -- %s `%s %s` \u00b7 %d%% \u00b7 %s %s \u00b7 cat %s \u00b7 **APEX SCORE %d** (Evidence: %s)%s"
                    % (i, p.get("player", ""), LABEL.get(d["cat"], d["cat"]),
                       p.get("line", ""), p.get("direction", ""), round(float(p.get("prob") or 0) * 100),
                       icon[d["lvl"]], d["lvl"], d["rs"], d["score"], d["ev"],
                       " \u26a0\ufe0f BO5 SAMPLE" if d["bo5"] else ""))
        L = ["\U0001F3C6 **APEX BEST BETS** -- evidence-weighted (probability \u00b7 category record \u00b7 calibration \u00b7 bands \u00b7 attention)"]
        for i, d in enumerate(scored[:8], 1):
            L.append(line1(i, d))
        best3 = [d for d in scored if not d["bo5"]][:3]
        L.append("")
        L.append("\U0001F947 **BEST 3 PICKS TODAY**")
        if best3:
            for i, d in enumerate(best3, 1):
                why = "; ".join(d["up"][:2]) or "highest evidence-weighted score on the board"
                L.append("%d. %s -- %s (%d): %s" % (i, d["p"].get("player", ""),
                                                    LABEL.get(d["cat"], d["cat"]), d["score"], why))
        else:
            L.append("-- no eligible picks (Bo5 picks cannot enter Best 3 under BO5-FWD-001)")
        low = [d for d in scored if d not in best3][-3:][::-1]
        L.append("")
        L.append("\u26a0\ufe0f **LOW PRIORITY PICKS**")
        if low:
            for d in low:
                why = "; ".join(d["down"][:2]) or "no negative flags -- simply outranked today"
                L.append("\u00b7 %s -- %s (%d): %s" % (d["p"].get("player", ""),
                                                       LABEL.get(d["cat"], d["cat"]), d["score"], why))
        else:
            L.append("-- board too small to split")
        L.append("_Scores re-derive from the settled ledger at every post -- they sharpen as evidence settles._")
        return "\n".join(L)
    except Exception:
        return ""


'''

EDITS = {"apex_edge_tracker.py": [], "openclaw_core.py": []}

EDITS["apex_edge_tracker.py"] += [
("A1 header signature",
"def discord_header(card_category=None, rec=None, prob=None):",
"def discord_header(card_category=None, rec=None, prob=None, bo5=False):"),
("A2 header LOW override",
"""        lvl, why = attention(c, prob, rec)""",
"""        lvl, why = attention(c, prob, rec)
        if bo5:
            lvl, why = "LOW", "BO5-FWD-001 -- Bo5 experimental stream, forced LOW until 25 settled"
"""),
("B functions",
"def bo5_block(rec):",
TRACKER_FUNCS.strip("\n") + "\n\n\ndef bo5_block(rec):"),
("C selftest",
"""    except SystemExit:
        pass
    print(MARKER, "selftest", "PASS" if not fails else "FAIL")""",
"""    except SystemExit:
        pass
    # ---- APEX-BB-001 checks
    r_bb = records(synth(30, 0.62, 0.55, "dfs") + synth(30, 0.45, 0.55, "total_games"))
    if not apex_score(0.60, "dfs", False, r_bb)[0] > apex_score(0.60, "breaks", False, r_bb)[0]:
        fails.append("BB: evidenced category must outrank empty category at equal probability")
    s5 = apex_score(0.80, "aces", True, r_bb)
    if s5[0] > 49 or s5[2] != "LOW": fails.append("BB: Bo5 must cap <=49 and force LOW")
    _blk = best_bets_block([
        {"player": "AA", "category": "dfs", "prob": 0.62, "line": 2.5, "direction": "MORE", "bo5": False},
        {"player": "BB", "category": "total_games", "prob": 0.55, "line": 22.5, "direction": "MORE", "bo5": False},
        {"player": "ZZBO5", "category": "aces", "prob": 0.80, "line": 5.5, "direction": "MORE", "bo5": True}], rec=r_bb)
    for need in ("APEX BEST BETS", "BEST 3", "LOW PRIORITY", "APEX SCORE"):
        if need not in _blk: fails.append("BB render missing %r" % need)
    if "ZZBO5" in _blk.split("BEST 3")[1].split("LOW PRIORITY")[0]:
        fails.append("BB: Bo5 pick leaked into Best 3")
    if "ATTENTION: LOW" not in discord_header("aces", rec=r_bb, prob=0.75, bo5=True):
        fails.append("BB: header must force LOW on Bo5")
    print(MARKER, "selftest", "PASS" if not fails else "FAIL")"""),
]

EDITS["openclaw_core.py"] += [
("D apex_best_of",
'''            "apex_tier":           target["tier"],''',
'''            "apex_tier":           target["tier"],
            "apex_best_of":        res.get("best_of", ""),'''),
("E header bo5",
'''            _hdr = _aet.discord_header(t.get("category"), prob=((max(_po, _pu) / (_po + _pu)) if (_po + _pu) > 0 else None))''',
'''            _hdr = _aet.discord_header(t.get("category"), prob=((max(_po, _pu) / (_po + _pu)) if (_po + _pu) > 0 else None), bo5=(str(res.get("best_of") or "") == "5"))'''),
("F best bets in output_agent",
'''    if not green and not yellow:
        lines.append("No qualifying picks found for this date.")

    lines += [
        "\u2500"*38,''',
'''    if not green and not yellow:
        lines.append("No qualifying picks found for this date.")

    # APEX-BB-001: Best Bets below the normal picks. Never blocks the post.
    if selected:
        try:
            import apex_edge_tracker as _aet_bb
            _bb = _aet_bb.best_bets_block([
                {"player": p.get("player", ""), "line": p.get("line", ""),
                 "direction": p.get("direction", ""),
                 "category": _APEX_STAT_MAP.get(str(p.get("stat_type", "")).strip().lower().replace(" ", "_"), ""),
                 "prob": float(p.get("confidence") or 0),
                 "bo5": str(p.get("apex_best_of") or "") == "5"}
                for p in selected])
            if _bb:
                lines.append(_bb); lines.append("")
        except Exception as _e:
            log("ApexBB", f"best bets skipped (non-fatal): {_e}")

    lines += [
        "\u2500"*38,'''),
]

def main():
    for fn in EDITS:
        if MARKER in open(fn, encoding="utf-8", errors="replace").read():
            sys.exit(f"{MARKER} already present in {fn} -- refusing to re-apply")
    ok = True
    srcs = {}
    for fn, edits in EDITS.items():
        srcs[fn] = open(fn, encoding="utf-8", errors="replace").read()
        print(f"{MARKER}  {fn}  sha256 {sha(fn)}")
        for name, old, new in edits:
            n = srcs[fn].count(old)
            print("  [%s] %s: %d match(es)" % ("ok" if n == 1 else "FAIL", name, n))
            ok = ok and n == 1
    if not ok: sys.exit("ABORT -- nothing written")
    if "--dry-run" in sys.argv: print("dry run: ok, nothing written"); sys.exit(0)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    baks = {}
    for fn, edits in EDITS.items():
        baks[fn] = f"{fn}.bak_{ts}_prebb"; shutil.copy2(fn, baks[fn])
        s = srcs[fn]
        for name, old, new in edits: s = s.replace(old, new, 1)
        open(fn, "w", encoding="utf-8").write(s)
    import py_compile
    try:
        for fn in EDITS: py_compile.compile(fn, doraise=True)
        r = subprocess.run(["/usr/bin/python3", "-c",
            "import apex_edge_tracker as a;"
            "h=a.discord_header('aces',prob=0.7,bo5=True);"
            "assert 'ATTENTION: LOW' in h, 'bo5 header not forced LOW';"
            "b=a.best_bets_block([{'player':'X','category':'dfs','prob':0.62,'line':2.5,'direction':'MORE','bo5':False}]);"
            "assert 'APEX BEST BETS' in b and 'APEX SCORE' in b, 'block render failed';"
            "print('smoke OK')"], capture_output=True, text=True, cwd=os.getcwd())
        print(r.stdout.strip() or r.stderr.strip())
        if "smoke OK" not in r.stdout: raise RuntimeError("smoke failed: " + r.stderr[-400:])
    except Exception as e:
        for fn in EDITS: shutil.copy2(baks[fn], fn)
        sys.exit(f"ABORT -- {e}; restored backups")
    for fn in EDITS: print(f"written {fn}  sha256 {sha(fn)}  (backup {baks[fn]})")

if __name__ == "__main__":
    main()
