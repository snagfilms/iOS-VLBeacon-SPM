#!/usr/bin/env python3
"""
verify_commit.py — after the developer commits (and again after the PR lands), prove the merge really landed.

Checks
  1. the source head is an ancestor of <ref>           → git knows the source branch was merged
  2. <ref> (or the commit that brought source in) has 2+ parents → it is a real merge commit, not a plain commit
  3. the committed tree equals the hand-over tree saved by commit_message.py → nothing changed between hand-over
     and commit (commit hooks, formatters, a last-minute edit). Differences are listed per file.
  4. --ref origin/<branch> after the PR merged: the merged files still have the merged content; later changes to
     them are listed (they may have dropped merged lines → re-run verify_coverage.py on a checkout of that ref).

Usage: verify_commit.py <report>/analysis.json --tree <target folder> [--ref HEAD | origin/<target branch>]
Exit 0 = all good · 1 = merge not recorded · 2 = content differs from the hand-over / changed after landing
"""
import argparse, json, os, subprocess, sys


def git(root, *a):
    r = subprocess.run(["git", "-C", root, *a], capture_output=True, text=True)
    return r.returncode, r.stdout.strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("analysis"); ap.add_argument("--tree", required=True); ap.add_argument("--ref", default="HEAD")
    a = ap.parse_args()
    d = json.load(open(a.analysis)); root = a.tree
    src = d["source"]["head"]; rc_code = 0
    ok_anc = git(root, "merge-base", "--is-ancestor", src, a.ref)[0] == 0
    print(("OK    " if ok_anc else "FAIL  ") + f"{d['source']['branch']}@{src[:9]} is {'an' if ok_anc else 'NOT an'} ancestor of {a.ref}")
    if not ok_anc:
        print(f"      → record it: git -C \"{root}\" merge -s ours {src[:12]} -m \"Record merge of {d['source']['branch']}\" (code unchanged)")
        rc_code = 1
    _, mc = git(root, "rev-list", "--ancestry-path", "--merges", "--reverse", f"{src}..{a.ref}")
    first_merge = mc.split()[0] if mc else ""
    if ok_anc:
        print(("OK    " if first_merge else "WARN  ") + (f"merge commit {first_merge[:10]} brought it in" if first_merge else "source reached via fast-forward / no merge commit"))
    ho = d.get("handover") or {}
    if ho.get("tree") and a.ref == "HEAD":
        _, t = git(root, "rev-parse", "HEAD^{tree}")
        if t == ho["tree"]:
            print("OK    committed tree is exactly the hand-over tree")
        else:
            _, diff = git(root, "diff", "--name-status", ho["tree"], t)
            print("WARN  committed content differs from the hand-over (commit hooks / formatter / manual edit):")
            print("\n".join("      " + l for l in diff.splitlines()[:40]))
            print("      → re-run verify_coverage.py --tree on this checkout, and review these files")
            rc_code = rc_code or 2
        d.setdefault("landed", {})["merge_commit"] = git(root, "rev-parse", "HEAD")[1]
        json.dump(d, open(a.analysis, "w"), indent=1)
    elif a.ref != "HEAD":
        mc_saved = (d.get("landed") or {}).get("merge_commit")
        if mc_saved:
            files = sorted({it.get("final_path") or it.get("target_path") or it["file"] for it in d["items"]})
            _, diff = git(root, "diff", "--stat", mc_saved, a.ref, "--", *files)
            if diff:
                print(f"WARN  merged files changed between the merge commit {mc_saved[:10]} and {a.ref}:\n" + "\n".join("      " + l for l in diff.splitlines()[-25:]))
                print("      → check these did not drop merged lines (verify_coverage.py on a checkout of that ref)")
                rc_code = rc_code or 2
            else:
                print(f"OK    merged files are unchanged from the merge commit on {a.ref}")
        else:
            print("INFO  no merge commit recorded yet — run once with --ref HEAD right after the developer's commit")
    sys.exit(rc_code)


if __name__ == "__main__":
    main()
