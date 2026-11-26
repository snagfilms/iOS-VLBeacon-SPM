#!/usr/bin/env python3
"""
verify_coverage.py — prove that no source code was silently lost in the merged working tree.

For every item in analysis.json it checks the merged files on disk (target folder working tree):
  * every non-trivial line the source ADDED must exist — in the item's final/target path, or at
    least somewhere in the tree (reported as MOVED) — unless the decision was TARGET (keep current)
    or the item is ALREADY_PRESENT / COSMETIC;
  * every line the source REMOVED should be gone when the decision was SOURCE (reported as
    STILL_PRESENT warnings, because target may legitimately use the same line elsewhere);
  * every NEW_FILE that was to be added exists (at final_path / suggested path / source path);
  * no conflict markers remain anywhere.

Usage: verify_coverage.py <report_folder>/analysis.json [--tree <target folder>]
Writes <report_folder>/verification.md and verification.json.
Exit 1 when anything is MISSING or conflict markers remain; 0 otherwise.
"""
import argparse, json, os, re, subprocess, sys
from collections import defaultdict

SKIP_DIRS = {".git", "Pods", "build", "DerivedData", ".build", "node_modules", "Carthage", ".swiftpm", "SourcePackages"}
TEXT_EXT = {".swift", ".m", ".mm", ".h", ".c", ".cpp", ".plist", ".strings", ".json", ".xcconfig", ".kt", ".java", ".js", ".ts",
            ".py", ".rb", ".sh", ".storyboard", ".xib", ".entitlements", ".md", ".yml", ".yaml", ".gradle", ".xml", ".pbxproj"}
MARKER = re.compile(r"^(<<<<<<< |>>>>>>> |=======$)", re.M)


def norm(s):
    return re.sub(r"\s+", " ", s.strip())


def read(p):
    try:
        with open(p, encoding="utf-8", errors="replace") as f:
            return f.read()
    except (FileNotFoundError, IsADirectoryError):
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("analysis")
    ap.add_argument("--tree")
    a = ap.parse_args()
    d = json.load(open(a.analysis))
    folder = os.path.dirname(os.path.abspath(a.analysis))
    root = a.tree or d["target"]["repo_root"]

    # index of every normalized line in the tree, by file
    tree_index = defaultdict(set)
    markers = []
    for dp, dns, fns in os.walk(root):
        dns[:] = [x for x in dns if x not in SKIP_DIRS and not x.endswith(".xcassets")]
        for fn in fns:
            if os.path.splitext(fn)[1].lower() not in TEXT_EXT:
                continue
            p = os.path.join(dp, fn)
            txt = read(p)
            if txt is None:
                continue
            rel = os.path.relpath(p, root)
            if MARKER.search(txt) and not fn.endswith(".md"):
                markers.append(rel)
            for l in txt.splitlines():
                n = norm(l)
                if n:
                    tree_index[n].add(rel)

    def file_lines(rel):
        txt = read(os.path.join(root, rel)) if rel else None
        return None if txt is None else {norm(l) for l in txt.splitlines()}

    results, missing_total, moved_total, still_total = [], 0, 0, 0
    for it in d["items"]:
        cat, dec = it["category"], it.get("decision")
        r = {"id": it["id"], "category": cat, "decision": dec, "file": it["file"], "status": "OK", "missing": [], "moved": [], "still_present": []}
        if cat in ("ALREADY_PRESENT", "COSMETIC"):
            r["status"] = "SKIPPED (already present / cosmetic)"; results.append(r); continue
        if dec == "TARGET":
            r["status"] = "SKIPPED (decision: keep target)"; results.append(r); continue
        if cat == "NEW_FILE":
            cands = [x for x in (it.get("final_path"), it.get("suggested_target_path"), it["file"]) if x]
            if not any(os.path.exists(os.path.join(root, c)) for c in cands):
                r["status"] = "MISSING"; r["missing"] = [f"file not found at any of: {cands}"]; missing_total += 1
            results.append(r); continue
        if cat == "DELETED_IN_SOURCE":
            tp = it.get("final_path") or it.get("target_path")
            if dec == "SOURCE" and tp and os.path.exists(os.path.join(root, tp)):
                r["status"] = "WARN"; r["still_present"] = [f"{tp} still exists although decision was delete"]; still_total += 1
            results.append(r); continue
        added, removed = it.get("added_norm") or [], it.get("removed_norm") or []
        if not added and not removed:
            r["status"] = "MANUAL (no line data — check by hand: " + cat + ")"; results.append(r); continue
        tp = it.get("final_path") or it.get("target_path") or it["file"]
        fl = file_lines(tp)
        for line in added:
            if fl is not None and line in fl:
                continue
            elsewhere = sorted(tree_index.get(line, set()))
            if elsewhere:
                r["moved"].append(f"{line[:120]}   → found in {', '.join(elsewhere[:3])}")
            else:
                r["missing"].append(line[:160])
        if dec in (None, "SOURCE", "AI") and fl is not None:
            for line in removed:
                if line in fl and line not in set(added):
                    r["still_present"].append(line[:160])
        if r["missing"]:
            if dec in ("AI", "CUSTOM", "BOTH"):
                r["status"] = "CHECK (decision " + dec + " — lines rewritten? confirm business logic kept)"
            else:
                r["status"] = "MISSING"; missing_total += 1
        elif r["moved"]:
            r["status"] = "MOVED"; moved_total += 1
        elif r["still_present"]:
            r["status"] = "WARN"; still_total += 1
        results.append(r)

    ok = missing_total == 0 and not markers
    out = {"report_id": d["report_id"], "tree": root, "ok": ok, "missing_items": missing_total, "moved_items": moved_total,
           "still_present_items": still_total, "conflict_markers": markers, "results": results}
    json.dump(out, open(os.path.join(folder, "verification.json"), "w"), indent=1)
    md = [f"# Coverage verification — {d['report_id']}", "", f"Tree: `{root}`", "",
          f"**Result: {'PASS' if ok else 'FAIL'}** — missing: {missing_total}, moved: {moved_total}, removed-but-still-present: {still_total}, "
          f"files with conflict markers: {len(markers)}", ""]
    for m in markers:
        md.append(f"- ❌ conflict markers in `{m}`")
    for r in results:
        if r["status"] == "OK" or r["status"].startswith("SKIPPED"):
            continue
        md.append(f"## {r['id']} — {r['status']} — `{r['file']}` ({r['category']}, decision {r['decision']})")
        for x in r["missing"]:
            md.append(f"- MISSING: `{x}`")
        for x in r["moved"]:
            md.append(f"- moved: `{x}`")
        for x in r["still_present"]:
            md.append(f"- still present: `{x}`")
        md.append("")
    open(os.path.join(folder, "verification.md"), "w").write("\n".join(md) + "\n")
    print("\n".join(md[:6]))
    for r in results:
        if r["status"] not in ("OK",) and not r["status"].startswith("SKIPPED"):
            print(f"{r['id']:7s} {r['status'][:60]:60s} {r['file']}")
    print(f"written: {os.path.join(folder, 'verification.md')}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
