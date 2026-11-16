"""Rewrites the block-fmt / block-line1 anchors in apex_bb3_patch.py to match
the file's literal \\u escape text. Run once, then re-run apex_bb3_patch.py."""
import io, os, sys

P = os.path.expanduser("~/openclaw/apex_bb3_patch.py")
src = io.open(P, encoding="utf-8").read()

OLD_BLOCK = src[src.index('E.append(("block-line1"'):src.index('E.append(("block-footer"')]

NEW_BLOCK = (
    'E.append(("block-render",\n'
    '\'\'\'            return ("**#%d %s** -- %s `%s %s` \\\\u00b7 %d%% \\\\u00b7 %s %s \\\\u00b7 cat %s \\\\u00b7 **APEX SCORE %d** (Evidence: %s)%s"\n'
    '                    % (i, p.get("player", ""), LABEL.get(d["cat"], d["cat"]),\n'
    '                       p.get("line", ""), p.get("direction", ""), round(float(p.get("prob") or 0) * 100),\n'
    '                       icon[d["lvl"]], d["lvl"], d["rs"], d["score"], d["ev"],\n'
    '                       " \\\\u26a0\\\\ufe0f BO5 SAMPLE" if d["bo5"] else ""))\'\'\',\n'
    '\'\'\'            return ("**#%d %s** -- %s `%s %s` \\\\u00b7 %d%% \\\\u00b7 %s %s \\\\u00b7 cat %s \\\\u00b7 **APEX SCORE %d** \\\\u00b7 **CONFIDENCE %d/70** \\\\u00b7 **RANK SCORE %.1f** (Evidence: %s)%s"\n'
    '                    % (i, p.get("player", ""), LABEL.get(d["cat"], d["cat"]),\n'
    '                       p.get("line", ""), p.get("direction", ""), round(float(p.get("prob") or 0) * 100),\n'
    '                       icon[d["lvl"]], d["lvl"], d["rs"], d["score"],\n'
    '                       d.get("conf", 0), d.get("rank", 0.0), d["ev"],\n'
    '                       " \\\\u26a0\\\\ufe0f BO5 SAMPLE" if d["bo5"] else ""))\'\'\'))\n\n'
)

out = src.replace(OLD_BLOCK, NEW_BLOCK, 1)
if out == src:
    print("BLOCKED: could not rewrite the anchors")
    sys.exit(1)
io.open(P, "w", encoding="utf-8").write(out)
print("anchors merged into one: block-render")
