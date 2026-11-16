#!/usr/bin/env python3
"""
APEX-RESTORELOG-2026-10-22 (owner: "When we save restore points we need to
also add a system of what all was change and why"): one command that saves a
restore point AND writes down what is changing and why.

  python3 apex_restore_point.py save <name> --what "..." --why "..." --files a.py b.py
      -> git tag <name> (snapshot of the working tree), backups/<name>_<date>/ with
         copies of the files + CHANGE.md, and a new entry at the top of RESTORE_POINTS.md
  python3 apex_restore_point.py done <name> --commit <sha> [--undo "..."] [--boards "..."]
      -> adds the commit (and how to undo it) to CHANGE.md and RESTORE_POINTS.md
  python3 apex_restore_point.py list
"""
import argparse, os, re, shutil, subprocess, sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(HERE, "RESTORE_POINTS.md")
MARK = "\n---\n"


def _git(*a):
    return subprocess.run(["git", *a], cwd=HERE, capture_output=True, text=True).stdout.strip()


def _folder(name):
    for d in sorted(os.listdir(os.path.join(HERE, "backups")), reverse=True):
        if d == name or d.startswith(name + "_"):
            return os.path.join(HERE, "backups", d)
    return None


def save(a):
    today = date.today().isoformat()
    folder = os.path.join(HERE, "backups", "%s_%s" % (a.name, today))
    os.makedirs(folder, exist_ok=True)
    for f in a.files:
        if os.path.exists(os.path.join(HERE, f)):
            dst = os.path.join(folder, os.path.basename(f))
            shutil.copy2(os.path.join(HERE, f), dst)
    snap = _git("stash", "create") or "HEAD"
    _git("tag", a.name, snap)
    entry = ("## %s (%s)\n- **What changes:** %s\n- **Why:** %s\n- **Files:** %s\n- **Saved:** git tag `%s` (%s) + `backups/%s`\n"
             % (a.name, today, a.what, a.why, ", ".join("`%s`" % f for f in a.files), a.name, snap[:7],
                os.path.basename(folder)))
    with open(os.path.join(folder, "CHANGE.md"), "w") as fh:
        fh.write("# " + entry[3:])
    text = open(LOG).read() if os.path.exists(LOG) else "# Apex restore points: what changed and why\n" + MARK
    i = text.find(MARK)
    text = text[:i + len(MARK)] + "\n" + entry + "\n" + text[i + len(MARK):] if i >= 0 else text + MARK + entry
    open(LOG, "w").write(text)
    print("saved %s -> %s" % (a.name, folder))


def done(a):
    add = "- **Commit:** %s\n" % a.commit
    if a.boards:
        add += "- **Boards changed?** %s\n" % a.boards
    if a.undo:
        add += "- **Undo:** %s\n" % a.undo
    folder = _folder(a.name)
    if folder:
        with open(os.path.join(folder, "CHANGE.md"), "a") as fh:
            fh.write(add)
    text = open(LOG).read()
    m = re.search(r"## %s \(.*?\n(?=\n## |\Z)" % re.escape(a.name), text, re.S)
    if not m:
        sys.exit("no entry for %s in RESTORE_POINTS.md" % a.name)
    text = text[:m.end()] + add + text[m.end():]
    open(LOG, "w").write(text)
    print("recorded %s for %s" % (a.commit, a.name))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("save"); s.add_argument("name"); s.add_argument("--what", required=True)
    s.add_argument("--why", required=True); s.add_argument("--files", nargs="+", required=True)
    d = sub.add_parser("done"); d.add_argument("name"); d.add_argument("--commit", required=True)
    d.add_argument("--undo", default=""); d.add_argument("--boards", default="")
    sub.add_parser("list")
    a = ap.parse_args()
    if a.cmd == "save":
        save(a)
    elif a.cmd == "done":
        done(a)
    else:
        print("\n".join(l[3:] for l in open(LOG).read().splitlines() if l.startswith("## ")))


if __name__ == "__main__":
    main()
