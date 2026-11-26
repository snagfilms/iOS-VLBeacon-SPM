#!/usr/bin/env python3
"""
commit_message.py — write the commit message + description for the finished merge.
It NEVER runs git commit / push. The developer commits with:  git commit -F <report>/COMMIT_MSG.txt

For every source change that is in the merged tree it lists
    developer -- file -- line numbers (in the merged file) -- item, category, decision, developer notes
grouped by developer, then the changes intentionally NOT merged (with who decided and why),
then verification / build results.

Usage:
  commit_message.py <report_folder>/analysis.json [--tree <target folder>]
                    [--build "AppCMS iOS ✔, AppCMS_tvOS ✔"] [--post-merge "bash setup_environment.sh motv stage ✔"]
                    [--subject "custom subject"]
Writes <report_folder>/COMMIT_MSG.txt and prints it.
"""
import argparse, json, os, re, sys
from collections import defaultdict, OrderedDict


def norm(s):
    return re.sub(r"\s+", " ", s.strip())


def ranges(nums):
    nums = sorted(set(nums))
    out, start, prev = [], None, None
    for n in nums:
        if start is None:
            start = prev = n
        elif n == prev + 1:
            prev = n
        else:
            out.append((start, prev)); start = prev = n
    if start is not None:
        out.append((start, prev))
    return ", ".join(f"L{a}" if a == b else f"L{a}-{b}" for a, b in out)


def first_sentence(s, n=140):
    s = (s or "").strip().replace("\n", " ")
    m = re.match(r"(.+?[.!?])(\s|$)", s)
    s = m.group(1) if m else s
    return s if len(s) <= n else s[:n - 1] + "…"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("analysis")
    ap.add_argument("--tree")
    ap.add_argument("--build", default="")
    ap.add_argument("--post-merge", default="")
    ap.add_argument("--subject", default="")
    a = ap.parse_args()
    d = json.load(open(a.analysis))
    folder = os.path.dirname(os.path.abspath(a.analysis))
    root = a.tree or d["target"]["repo_root"]
    s, t, g = d["source"], d["target"], d["generator"]

    cache = {}
    def lines_of(rel):
        if rel not in cache:
            try:
                with open(os.path.join(root, rel), encoding="utf-8", errors="replace") as f:
                    cache[rel] = [norm(x) for x in f.read().splitlines()]
            except (FileNotFoundError, IsADirectoryError, TypeError):
                cache[rel] = None
        return cache[rel]

    by_dev = OrderedDict()
    dropped, unresolved = [], []
    for it in d["items"]:
        cat = it.get("ai_category") or it["category"]
        dec = it.get("decision")
        if cat in ("ALREADY_PRESENT", "COSMETIC", "IB_METADATA"):
            continue
        devs = it.get("source_authors") or [{"name": "unknown", "email": "", "date": ""}]
        note = it.get("decision_notes") or ""
        if dec == "AI" and it.get("ai_recommendation") and "AI" not in note[:20]:
            note = (note + " | " if note else "") + "AI: " + first_sentence(it["ai_recommendation"])
        who_dec = {"ai": " (AI)", "developer": " (dev)"}.get(it.get("decided_by"), " (dev)" if dec else "")
        tag = f"{it['id']} {cat}" + (f" → {dec}{who_dec}" if dec else "")
        if it.get("source_symbol") and not str(it["source_symbol"]).startswith("("):
            tag += f" [{it['source_symbol']}]"
        if dec == "TARGET":
            who = ", ".join(f"{x.get('name')} {x.get('date', '')[:10]}" for x in devs[:2])
            dropped.append(f"- {it['file']} -- {tag} -- by {who}" + (f" -- note: {note}" if note else ""))
            continue
        if it["needs_decision"] and not dec:
            unresolved.append(f"- {it['id']} {it['file']}")
        path = it.get("final_path") or (it.get("suggested_target_path") if cat == "NEW_FILE" else None) or it.get("target_path") or it["file"]
        merged = lines_of(path)
        where = ""
        if cat == "NEW_FILE" and merged is not None:
            where = f"new file, {len(merged)} lines"
        elif cat == "DELETED_IN_SOURCE":
            where = "file deleted" if merged is None else "file kept"
        elif merged is not None:
            want = it.get("added_norm") or []
            look = set(want)
            if dec in ("AI", "BOTH", "CUSTOM"):
                # the merged block may be rewritten: also look for the proposed code and target's changed lines
                look |= {norm(x) for x in (it.get("proposed_code") or "").splitlines() if len(norm(x)) > 3}
                tg = it.get("target") or {}
                look |= {norm(tg["lines"][m]) for m in tg.get("marked", []) if m < len(tg.get("lines", [])) and len(norm(tg["lines"][m])) > 3}
            hits = [i + 1 for i, x in enumerate(merged) if x in look]
            if hits and it.get("target"):
                # keep hits near the item (a common line may also appear elsewhere in the file)
                centre = (it["target"].get("start") or hits[0]) + len(it["target"].get("lines", [])) // 2
                hits = [h for h in hits if abs(h - centre) <= 40 + len(want)] or hits
            # close 1-line gaps so a rewritten block reads as one range
            hits = sorted(set(hits)); hits += [h + 1 for h, n in zip(hits, hits[1:]) if n - h == 2]
            if hits:
                where = ranges(hits)
                missing = len(set(want) - set(merged))
                if missing:
                    where += f" ({missing} line(s) rewritten in merge)"
            elif want:
                src = it.get("source") or {}
                if src.get("marked"):
                    where = "rewritten in merge; source " + ranges(src["start"] + m for m in src["marked"])
            else:
                where = "removal" + (f" near {ranges([((it.get('target') or {}).get('start') or 0) + 1])}" if it.get("target") else "")
        else:
            where = "file not found in merged tree — check"
        moved = f" (from {it['file']})" if path != it["file"] else ""
        conflict_with = ""
        if it.get("target_authors") and cat in ("CONFLICT", "OPTIMIZED_IN_TARGET", "OPTIMIZED_IN_SOURCE", "NEAR_CHANGE", "DELETED_IN_TARGET"):
            ta = it["target_authors"][0]
            conflict_with = f"; target side: {ta.get('name')} {ta.get('date', '')[:10]}"
        for dv in devs[:3]:
            key = f"{dv.get('name')} <{dv.get('email')}>"
            by_dev.setdefault(key, []).append(
                f"  - {dv.get('name')} -- {path}{moved} -- {where or 'n/a'} -- {tag} ({dv.get('date', '')[:10]} {dv.get('short', '')}{conflict_with})"
                + (f" -- note: {note}" if note else ""))

    ver = {}
    vp = os.path.join(folder, "verification.json")
    if os.path.exists(vp):
        ver = json.load(open(vp))
    subject = a.subject or f"Merge {s['branch']} into {t['branch']}"
    if len(subject) > 72:
        subject = subject[:71] + "…"
    body = [
        f"Merged {s['branch']}@{s['head'][:9]} into {t['branch']}@{t['head'][:9]} "
        f"(base {(d.get('analysis_base') or '')[:9]}, {d['mode']}).",
        f"Merge report: {d['report_id']} | generated with {g.get('tool')} | chat/session: {g.get('session_id') or 'n/a'}",
        f"Decisions: {sum(1 for i in d['items'] if i.get('decided_by') == 'ai')} by AI (code review + independent check), "
        f"{sum(1 for i in d['items'] if i.get('decision') and i.get('decided_by') != 'ai')} by "
        f"{(d.get('decisions_meta') or {}).get('decided_by') or 'developer'}",
    ]
    if ver:
        body.append(f"Coverage check: {'PASS' if ver.get('ok') else 'FAIL'} (missing {ver.get('missing_items')}, moved {ver.get('moved_items')})")
    if a.post_merge:
        body.append(f"Post-merge: {a.post_merge}")
    if a.build:
        body.append(f"Build: {a.build}")
    body += ["", "Changes merged, by developer (developer -- file -- merged line numbers -- item):"]
    for dev, rows in by_dev.items():
        body.append(f"{dev}")
        body += rows
    if dropped:
        body += ["", "Intentionally NOT merged (developer decision):"] + dropped
    if unresolved:
        body += ["", "WARNING — items without a decision (resolve before committing):"] + unresolved
    msg = subject + "\n\n" + "\n".join(body) + "\n"
    out = os.path.join(folder, "COMMIT_MSG.txt")
    with open(out, "w") as f:
        f.write(msg)
    print(msg)
    print(f"written: {out}")
    print(f"Developer commits it (this skill never does):  git -C \"{root}\" commit -F \"{out}\"")
    # ---- hand-over snapshot: the exact staged tree; verify_commit.py compares the developer's commit with it
    import subprocess
    tree = subprocess.run(["git", "-C", root, "write-tree"], capture_output=True, text=True).stdout.strip()
    if tree:
        d["handover"] = {"tree": tree, "head": subprocess.run(["git", "-C", root, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip(),
                         "unstaged": subprocess.run(["git", "-C", root, "diff", "--name-only"], capture_output=True, text=True).stdout.split()}
        json.dump(d, open(a.analysis, "w"), indent=1)
        if d["handover"]["unstaged"]:
            print("NOTE: unstaged changes are NOT in the hand-over (git add them or tell the developer): " + ", ".join(d["handover"]["unstaged"][:10]))
    # ---- merge record: without MERGE_HEAD the commit is a plain commit and git forgets the source branch was merged
    gd = subprocess.run(["git", "-C", root, "rev-parse", "--git-dir"], capture_output=True, text=True).stdout.strip()
    gd = gd if os.path.isabs(gd) else os.path.join(root, gd)
    src = d["source"].get("head") or d["source"].get("ref")
    want_record = (d.get("structure") or {}).get("strategy", "git-merge") == "git-merge" or d.get("record_as_merge", True)
    merged = subprocess.run(["git", "-C", root, "merge-base", "--is-ancestor", src, "HEAD"]).returncode == 0
    if want_record and not merged and not os.path.exists(os.path.join(gd, "MERGE_HEAD")):
        print("\nWARNING: no merge is in progress (MERGE_HEAD missing), so this commit would NOT record "
              f"{d['source']['branch']} as merged. The next merge would show the same changes again.\n"
              "Fix before committing: do not commit yet — tell the developer, or (after their commit) record it with\n"
              f"  git -C \"{root}\" merge -s ours {src[:12]} -m \"Record merge of {d['source']['branch']} (changes already ported)\"")
        sys.exit(4)


if __name__ == "__main__":
    main()
