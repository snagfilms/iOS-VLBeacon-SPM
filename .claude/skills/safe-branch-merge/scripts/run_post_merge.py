#!/usr/bin/env python3
"""
run_post_merge.py — run the post-merge steps (environment setup, codegen, pod install …) and record exactly which
files each one changed. Setup scripts often rewrite tracked files (project.pbxproj, Pods, plists, generated code);
without a record those edits get mixed into the merge commit, or silently undo merged lines.

For every command: snapshot (content hash of every modified / untracked / deleted path) → run → snapshot → diff.
Files the command changed that are also MERGED files (items' target_path / final_path) are flagged: re-run
verify_coverage.py, and ask the developer whether the command's edit belongs in the commit.

Usage: run_post_merge.py <report>/analysis.json --tree <target folder> [--cmd "cd AppCMS && bash setup_environment.sh motv stage" ...]
       (without --cmd: post_merge from project_profile.py / .merge-guard.json)
Writes <report>/post-merge.md + post-merge.json. Exit 1 if a command failed, 2 if merged files were changed.
"""
import argparse, hashlib, json, os, subprocess, sys, datetime


def state(root):
    out = subprocess.run(["git", "-C", root, "status", "--porcelain=v1", "-z", "--untracked-files=all"], capture_output=True).stdout
    res = {}
    for e in out.split(b"\0"):
        if len(e) < 4:
            continue
        p = e[3:].decode("utf-8", "replace")
        fp = os.path.join(root, p)
        try:
            res[p] = hashlib.sha1(open(fp, "rb").read()).hexdigest() if os.path.isfile(fp) else "dir" if os.path.isdir(fp) else "deleted"
        except OSError:
            res[p] = "unreadable"
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("analysis"); ap.add_argument("--tree", required=True); ap.add_argument("--cmd", action="append", default=[])
    ap.add_argument("--timeout", type=int, default=3600)
    a = ap.parse_args()
    d = json.load(open(a.analysis)); root = os.path.abspath(a.tree); folder = os.path.dirname(os.path.abspath(a.analysis))
    cmds = a.cmd
    if not cmds:
        here = os.path.dirname(os.path.abspath(__file__))
        prof = json.loads(subprocess.run([sys.executable, os.path.join(here, "project_profile.py"), root], capture_output=True, text=True).stdout)
        cmds = prof.get("post_merge") or []
    merged = {it.get("final_path") or it.get("target_path") or it["file"] for it in d["items"] if it.get("category") not in ("ALREADY_PRESENT",)}
    results, failed, touched_merged = [], False, []
    for c in cmds:
        before = state(root)
        print(f"→ {c}", flush=True)
        t0 = datetime.datetime.now()
        r = subprocess.run(c, shell=True, cwd=root, capture_output=True, text=True, timeout=a.timeout)
        after = state(root)
        changed = sorted(p for p in set(before) | set(after) if before.get(p) != after.get(p))
        hit = sorted(p for p in changed if p in merged)
        touched_merged += hit
        failed |= r.returncode != 0
        results.append({"command": c, "exit": r.returncode, "seconds": (datetime.datetime.now() - t0).seconds,
                        "changed": changed, "changed_merged_files": hit, "output_tail": (r.stdout + r.stderr)[-3000:]})
        print(f"  exit {r.returncode} · {len(changed)} file(s) changed" + (f" · {len(hit)} MERGED file(s) changed: {', '.join(hit[:5])}" if hit else ""))
    json.dump(results, open(os.path.join(folder, "post-merge.json"), "w"), indent=1)
    md = ["# Post-merge steps", ""]
    for x in results:
        md += [f"## `{x['command']}` — exit {x['exit']} ({x['seconds']}s)", "", f"Files changed by this command: {len(x['changed'])}"]
        md += [f"- `{p}`" + (" ⚠ **merged file**" if p in x["changed_merged_files"] else "") for p in x["changed"][:200]]
        if x["exit"] != 0:
            md += ["", "```", x["output_tail"][-1500:], "```"]
        md.append("")
    if touched_merged:
        md += ["**Merged files were changed by a post-merge command.** Re-run verify_coverage.py and ask the developer whether these edits belong in the merge commit."]
    open(os.path.join(folder, "post-merge.md"), "w").write("\n".join(md) + "\n")
    print(f"written: {os.path.join(folder, 'post-merge.md')}")
    sys.exit(1 if failed else 2 if touched_merged else 0)


if __name__ == "__main__":
    main()
