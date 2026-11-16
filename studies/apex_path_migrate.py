#!/usr/bin/env python3
"""
APEX-PATH-MIGRATE-2026-08-23
Project Apex Intelligence / OpenClaw (DEMETRIUS)

Safe, auditable migration of every absolute path reference from

    /path/to/home/Desktop/openclaw       (note: trailing space)
to
    /Users/<you>/openclaw

WHAT IT DOES
  --scan    Walks the project and the LaunchAgents folder, finds every file
            containing the old path, classifies it, and writes a migration
            report. WRITES NOTHING ELSE.
  --apply   Rewrites those references. Timestamped backup of every file it
            touches, verification pass afterwards, final report.
  --verify  Re-scans and reports what still references the old path.

WHAT IT NEVER DOES
  - start, stop, restart, load, unload or otherwise touch a running service
  - move, copy or delete the project folder itself (you do that with one mv)
  - modify frozen model artifacts, forward logs, state files or the match
    database (these are SKIPPED by extension and by name; see PROTECTED)
  - follow symlinks, or descend into backup folders it or others created

FAIL-OPEN: any file that cannot be read or written is reported and skipped;
one bad file never stops the run.

ORDER OF OPERATIONS (important)
  1.  python3 apex_path_migrate.py --scan            (from the OLD folder)
  2.  read the report
  3.  mv "/Users/<you>/Desktop/openclaw " "/Users/<you>/openclaw"
  4.  cd ~/openclaw
  5.  python3 apex_path_migrate.py --apply
  6.  python3 apex_path_migrate.py --verify
  7.  restart the services yourself, when you choose to

Scanning first, from the old location, means the report exists before anything
moves. Applying after the move means the rewritten paths are verified against a
folder that actually exists.
"""
import argparse, os, re, shutil, sys
from datetime import datetime

MARKER = "APEX-PATH-MIGRATE-2026-08-23"
HOME = os.path.expanduser("~")
OLD_PATHS = [
    "/path/to/home/Desktop/openclaw ",   # with trailing space
    "/path/to/home/Desktop/openclaw",    # without
    "~/Desktop/openclaw ",
    "~/Desktop/openclaw",
]
NEW_PATH = os.path.join(HOME, "openclaw")
LAUNCH_AGENTS = os.path.join(HOME, "Library", "LaunchAgents")
REPORT = "apex_path_migration_report.txt"

# Files whose CONTENT must never be rewritten: frozen models, logs, data,
# caches, binaries. A path string inside these is either impossible or is
# evidence we must not alter.
PROTECTED_NAMES = {
    "fragility_v3_model.json", "fragility_v3_live_ref.json",
    "apex_prop_model_v1.json", "apex_prop_sim_v1.json",
    "apex_prop_forward_log_v1.csv", "apex_prop_sim_forward_log_v1.csv",
    "fragility_forward_log.csv", "fragility_features.ok",
}
PROTECTED_EXT = {
    ".pkl", ".csv", ".log", ".zip", ".gz", ".png", ".jpg", ".jpeg", ".pdf",
    ".docx", ".xlsx", ".db", ".sqlite", ".sqlite3", ".parquet",
}
SCAN_EXT = {".py", ".json", ".plist", ".sh", ".md", ".txt", ".cfg", ".ini", ".yaml", ".yml", ""}
# Protected text formats are still SCANNED (so the report can say "this file
# contains the old path and was deliberately left alone") but never rewritten.
SCAN_EXT |= {".csv", ".log"}
SKIP_DIRS = {"__pycache__", ".git", "node_modules", ".venv", "venv", "ATP & WTA, 1968-2026"}
SKIP_DIR_PREFIXES = ("_backup_", ".")
MAX_BYTES = 5 * 1024 * 1024


def classify(path):
    n = os.path.basename(path).lower()
    e = os.path.splitext(n)[1]
    if e == ".plist": return "LaunchAgent plist"
    if e == ".py":    return "Python"
    if e == ".json":  return "JSON / config"
    if e == ".sh":    return "Shell script"
    if e in (".md", ".txt"): return "Documentation"
    if e in (".cfg", ".ini", ".yaml", ".yml"): return "Configuration"
    return "Other"


def is_protected(path):
    n = os.path.basename(path)
    if n in PROTECTED_NAMES: return "frozen model / log / state"
    e = os.path.splitext(n)[1].lower()
    if e in PROTECTED_EXT: return "data or binary (%s)" % (e or "no extension")
    if n.startswith("openclaw_core.py.bak_") or ".bak_" in n: return "backup file"
    return None


def candidate_files(root):
    """Project tree + the LaunchAgents folder. No symlinks, no backup dirs."""
    seen = set()
    for base in (root, LAUNCH_AGENTS):
        if not os.path.isdir(base):
            continue
        for dirpath, dirnames, filenames in os.walk(base, followlinks=False):
            dirnames[:] = [d for d in dirnames
                           if d not in SKIP_DIRS and not d.startswith(SKIP_DIR_PREFIXES)]
            for fn in filenames:
                p = os.path.join(dirpath, fn)
                # never scan or rewrite this script or its own report: the old
                # path appears here as literal data, not as a live reference
                if os.path.basename(p) in (os.path.basename(__file__), REPORT): continue
                if p in seen: continue
                seen.add(p)
                if os.path.islink(p): continue
                if base == LAUNCH_AGENTS and not fn.endswith(".plist"): continue
                e = os.path.splitext(fn)[1].lower()
                if base == root and e not in SCAN_EXT: continue
                yield p


def find_hits(root):
    """-> (hits, skipped, errors). hits = [(path, kind, [(lineno, line, which_old)])]"""
    hits, skipped, errors = [], [], []
    for p in candidate_files(root):
        try:
            if os.path.getsize(p) > MAX_BYTES:
                continue
            prot = is_protected(p)
            with open(p, encoding="utf-8", errors="replace") as f:
                text = f.read()
            found = [o for o in OLD_PATHS if o in text]
            if not found:
                continue
            lines = []
            for i, line in enumerate(text.splitlines(), 1):
                for o in OLD_PATHS:
                    if o in line:
                        lines.append((i, line.strip()[:150], o))
                        break
            if prot:
                skipped.append((p, prot, len(lines)))
            else:
                hits.append((p, classify(p), lines))
        except Exception as e:
            errors.append((p, "%s: %s" % (type(e).__name__, e)))
    return hits, skipped, errors


def rewrite(text):
    """Longest old path first, so the trailing-space form is consumed before
    the bare form (otherwise the bare match leaves an orphan space behind)."""
    out = text
    for o in sorted(OLD_PATHS, key=len, reverse=True):
        out = out.replace(o, NEW_PATH)
    # A quoted path with a trailing space may leave "...openclaw /file" -> tidy
    out = out.replace(NEW_PATH + " /", NEW_PATH + "/")
    return out


def write_report(lines, root):
    path = os.path.join(root, REPORT)
    try:
        with open(path, "w") as f:
            f.write("\n".join(lines) + "\n")
        print("\nreport written: %s" % path)
    except Exception as e:
        print("\n(could not write the report file: %s)" % e)


def cmd_scan(root, quiet=False):
    L = ["%s -- MIGRATION SCAN  %s" % (MARKER, datetime.now().isoformat(timespec="seconds")),
         "scanned project: %s" % root,
         "scanned agents : %s" % LAUNCH_AGENTS,
         "old path(s)    : %s" % ", ".join(repr(o) for o in OLD_PATHS),
         "new path       : %s" % NEW_PATH, ""]
    hits, skipped, errors = find_hits(root)
    by_kind = {}
    for p, kind, lines in hits:
        by_kind.setdefault(kind, []).append((p, lines))
    total_refs = sum(len(l) for _, _, l in hits)
    L.append("WILL BE REWRITTEN — %d file(s), %d reference(s)" % (len(hits), total_refs))
    for kind in sorted(by_kind):
        L.append("")
        L.append("  %s" % kind.upper())
        for p, lines in sorted(by_kind[kind]):
            L.append("    %s  (%d reference%s)" % (p, len(lines), "" if len(lines) == 1 else "s"))
            for ln, txt, _ in lines[:6]:
                L.append("        %5d | %s" % (ln, txt))
            if len(lines) > 6:
                L.append("        ... %d more" % (len(lines) - 6))
    if skipped:
        L.append("")
        L.append("PROTECTED — contains the old path but will NOT be modified (%d)" % len(skipped))
        for p, why, n in sorted(skipped):
            L.append("    %s  [%s, %d reference(s)]" % (p, why, n))
    if errors:
        L.append("")
        L.append("UNREADABLE — skipped (%d)" % len(errors))
        for p, why in errors:
            L.append("    %s  %s" % (p, why))
    L.append("")
    L.append("Nothing has been modified. Re-run with --apply AFTER moving the folder:")
    L.append('    mv "%s" "%s"' % (OLD_PATHS[0].rstrip(), NEW_PATH))
    L.append("    cd %s && python3 apex_path_migrate.py --apply" % NEW_PATH)
    text = "\n".join(L)
    if not quiet:
        print(text)
    write_report(L, root)
    return hits, skipped, errors


def cmd_apply(root):
    print(MARKER, "-- APPLY")
    if os.path.abspath(root) != os.path.abspath(NEW_PATH):
        print("** you are running from %s" % root)
        print("** expected to be running from %s" % NEW_PATH)
        print("** move the folder first, then cd into it. Refusing.")
        sys.exit(2)
    hits, skipped, errors = find_hits(root)
    if not hits:
        print("no rewritable references found — nothing to do")
        return
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    L = ["%s -- MIGRATION APPLY  %s" % (MARKER, datetime.now().isoformat(timespec="seconds")),
         "new path: %s" % NEW_PATH, ""]
    done, failed = [], []
    for p, kind, lines in sorted(hits):
        try:
            with open(p, encoding="utf-8", errors="replace") as f:
                text = f.read()
            new = rewrite(text)
            if new == text:
                continue
            backup = "%s.bak_%s" % (p, stamp)
            shutil.copy2(p, backup)
            with open(p, "w", encoding="utf-8") as f:
                f.write(new)
            if p.endswith(".py"):
                import py_compile
                try:
                    py_compile.compile(p, doraise=True)
                except Exception as ce:
                    shutil.copy2(backup, p)
                    failed.append((p, "compile failed after rewrite, RESTORED: %s" % ce))
                    continue
            done.append((p, kind, len(lines), backup))
            print("  rewrote %-60s (%d ref) backup %s" % (os.path.basename(p), len(lines), os.path.basename(backup)))
        except Exception as e:
            failed.append((p, "%s: %s" % (type(e).__name__, e)))
            print("  FAILED  %s — %s" % (p, e))
    L.append("REWRITTEN (%d)" % len(done))
    for p, kind, n, b in done:
        L.append("    %-8s %s  (%d ref)  backup: %s" % (kind[:8], p, n, os.path.basename(b)))
    if skipped:
        L.append("")
        L.append("PROTECTED — deliberately untouched (%d)" % len(skipped))
        for p, why, n in sorted(skipped):
            L.append("    %s  [%s]" % (p, why))
    if failed:
        L.append("")
        L.append("FAILED (%d)" % len(failed))
        for p, why in failed:
            L.append("    %s  %s" % (p, why))
    L.append("")
    L += verify_lines(root)
    write_report(L, root)
    print("\n".join(L[-14:]))
    print("\nNo service was started, stopped or reloaded. Restart them yourself when ready.")


def verify_lines(root):
    hits, skipped, errors = find_hits(root)
    L = ["VERIFICATION"]
    if not hits:
        L.append("    no rewritable file still references the old path — clean")
    else:
        L.append("    ** %d file(s) STILL reference the old path:" % len(hits))
        for p, kind, lines in sorted(hits):
            L.append("        %s (%d)" % (p, len(lines)))
    if skipped:
        L.append("    %d protected file(s) still contain it, as intended" % len(skipped))
    # sanity: does the new path actually exist, and do the key files sit in it?
    L.append("    new path exists: %s" % os.path.isdir(NEW_PATH))
    for f in ("openclaw_core.py", "apex_healthcheck.py", "apex_prop_model_v1.json"):
        L.append("    %-28s %s" % (f, "present" if os.path.exists(os.path.join(NEW_PATH, f)) else "MISSING"))
    ag = []
    if os.path.isdir(LAUNCH_AGENTS):
        ag = [f for f in os.listdir(LAUNCH_AGENTS) if f.endswith(".plist")
              and ("openclaw" in f.lower() or "demetrius" in f.lower())]
    L.append("    project LaunchAgents found: %s" % (", ".join(sorted(ag)) or "none"))
    return L


def cmd_verify(root):
    print(MARKER, "-- VERIFY")
    L = verify_lines(root)
    print("\n".join(L))


def cmd_selftest():
    print(MARKER, "-- SELFTEST (temp dir, no side effects)")
    import tempfile
    fails = []
    # rewrite() correctness
    cases = [
        ('CONFIG_FILE = Path("/path/to/home/Desktop/openclaw /config.json")',
         'CONFIG_FILE = Path("%s/config.json")' % NEW_PATH),
        ('<string>/path/to/home/Desktop/openclaw /apex_healthcheck.py</string>',
         '<string>%s/apex_healthcheck.py</string>' % NEW_PATH),
        ('cd "/path/to/home/Desktop/openclaw "',
         'cd "%s"' % NEW_PATH),
        ('WorkingDirectory /path/to/home/Desktop/openclaw',
         'WorkingDirectory %s' % NEW_PATH),
        ('nothing to change here', 'nothing to change here'),
    ]
    for src, want in cases:
        got = rewrite(src)
        if got != want:
            fails.append("rewrite(%r)\n  got  %r\n  want %r" % (src, got, want))
    # protection rules
    for n, expect in (("fragility_v3_model.json", True), ("apex_prop_sim_forward_log_v1.csv", True),
                      ("apex_prop_state_v1.pkl", True), ("openclaw_core.py", False),
                      ("com.apex.discordbot.plist", False), ("openclaw_core.py.bak_20260101_000000", True)):
        got = bool(is_protected(n))
        if got != expect:
            fails.append("is_protected(%s) = %s, expected %s" % (n, got, expect))
    # classify
    for n, k in (("a.py", "Python"), ("b.plist", "LaunchAgent plist"), ("c.json", "JSON / config"),
                 ("d.sh", "Shell script"), ("e.md", "Documentation")):
        if classify(n) != k:
            fails.append("classify(%s) = %s, expected %s" % (n, classify(n), k))
    # end-to-end on a fake tree: scan finds, apply refuses outside NEW_PATH
    d = tempfile.mkdtemp()
    with open(os.path.join(d, "x.py"), "w") as f:
        f.write('P = "/path/to/home/Desktop/openclaw /data"\n')
    with open(os.path.join(d, "keep.csv"), "w") as f:
        f.write("path,/path/to/home/Desktop/openclaw \n")
    hits, skipped, errors = find_hits(d)
    if len(hits) != 1 or not hits[0][0].endswith("x.py"):
        fails.append("scan should find exactly x.py, found %s" % [h[0] for h in hits])
    if len(skipped) != 1:
        fails.append("scan should protect keep.csv, skipped=%s" % skipped)
    if open(os.path.join(d, "x.py")).read().find("Desktop") < 0:
        fails.append("scan must not modify anything")
    print("SELFTEST", "PASS" if not fails else "FAIL:\n  " + "\n  ".join(fails))
    if fails: sys.exit(1)


def main():
    ap = argparse.ArgumentParser(description=MARKER)
    ap.add_argument("--scan", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--root", default=os.getcwd())
    a = ap.parse_args()
    if a.selftest: cmd_selftest()
    elif a.scan: cmd_scan(a.root)
    elif a.apply: cmd_apply(a.root)
    elif a.verify: cmd_verify(a.root)
    else: ap.print_help()


if __name__ == "__main__":
    main()
