#!/usr/bin/env python3
"""
classify_items.py — rule-based second pass over analysis.json, run after every collect_changes.py run
(before the AI review). Read-only on git; writes analysis.json.

1. IB_METADATA — Interface Builder files (.xib / .storyboard) whose changed lines differ ONLY in tool metadata:
   customModule="<client>" when the line also has customModuleProvider="target" (the module is picked per build
   target at runtime), toolsVersion / version / systemVersion attributes. These carry no runtime behaviour, so they
   are decided the same way everywhere: keep target (decision TARGET, rule-based evidence). This stops sibling
   hunks in one file from being handled inconsistently (one kept, the next applied by git).

2. Parallel implementations ("look-alikes") — the folder structure can be "same" while target has rebuilt a screen
   or service in a new module (e.g. ViewliftOne: AppCMS/ViewliftOne/…/VLOneMonetizationBadgeView.swift next to the
   legacy AppCMS/…/VLMonetizationBadgeView.swift). A source fix that lands only in the legacy file never reaches the
   new one. For every code item outside those modules, files with the same base name inside them are recorded in
   `counterparts`, with which key identifiers / string keys from the source change each counterpart already uses.
   The AI must then set `counterpart_verdict` (port | not-needed) + `counterpart_note` (auto_decide.py enforces it).

   Parallel modules come from <target>/.merge-guard.json → "parallel_modules": ["AppCMS/ViewliftOne/"].
   Without that key they are detected: folders present on target but absent on the merge base, holding ≥ 25 files.

Usage: classify_items.py <report>/analysis.json [--parallel AppCMS/ViewliftOne/ ...] [--no-counterparts]
"""
import argparse, json, os, re, subprocess, collections

IB_EXT = (".xib", ".storyboard")
CODE_SKIP = {"ALREADY_PRESENT", "COSMETIC", "IB_METADATA", "BINARY", "LARGE_FILE", "VENDORED_BUNDLE"}
GENERIC = {"view", "views", "cell", "controller", "viewcontroller", "model", "viewmodel", "manager", "helper",
           "service", "extension", "extensions", "constants", "utils", "utility", "protocol", "delegate", "base"}


def git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True).stdout


def ib_norm(line):
    l = line
    if 'customModuleProvider="target"' in l:
        l = re.sub(r'\scustomModule="[^"]*"', "", l)
    l = re.sub(r'\s(toolsVersion|version|systemVersion)="[^"]*"', "", l)
    return l.strip()


def marked(snip):
    if not snip:
        return []
    return [snip["lines"][n] for n in snip.get("marked", []) if n < len(snip.get("lines", []))]


def stem(path):
    b = os.path.basename(path)
    b = re.sub(r"\.(swift|m|mm|h|xib|storyboard|kt|java|ts|tsx|js)$", "", b)
    b = re.sub(r"(_tvOS|_iOS|\+[A-Za-z]+)$", "", b)
    b = re.sub(r"^(VLOne|VL)", "", b)
    return b


SUFFIXES = ("", "view", "viewcontroller", "controller", "screen", "viewmodel", "service", "manager")


def same_thing(a, b):
    """same base name, allowing one role suffix on either side (CreateAccount ~ CreateAccountView)."""
    return any(a + x == b or b + x == a for x in SUFFIXES)


def key_tokens(lines):
    """identifiers / string keys worth checking in a counterpart (kSomething, VLKeys.x, "literal", func calls)."""
    toks = set()
    for l in lines:
        toks |= set(re.findall(r"\bk[A-Z][A-Za-z0-9_]{4,}\b", l))
        toks |= set(re.findall(r"\.([a-z][A-Za-z0-9_]{5,})\s*\(", l))
        toks |= set(re.findall(r'"([A-Za-z_][A-Za-z0-9_\-]{5,})"', l))
    common = {"lowercased", "uppercased", "contains", "append", "remove", "removeAll", "configure", "decode", "encode",
              "addingTimeInterval", "beginUpdates", "endUpdates", "reloadData", "dismiss", "present", "first", "filter",
              "forEach", "compactMap", "replacingOccurrences", "components", "addSubview", "layoutIfNeeded", "isEmpty"}
    return sorted(t for t in toks if t not in common)[:8]


def detect_parallel(repo, base, target_ref):
    tgt = git(repo, "ls-tree", "-r", "--name-only", target_ref).splitlines()
    base_files = set(git(repo, "ls-tree", "-r", "--name-only", base).splitlines()) if base else set()
    code = re.compile(r"\.(swift|m|mm|kt|java|ts|tsx|js|jsx|cs|go|dart)$")
    skip = re.compile(r"(^|/)\.|\.(xcframework|framework|bundle|xcassets)/|test|mock|preview", re.I)
    new = [f for f in tgt if f not in base_files and code.search(f) and not skip.search(f)]
    base_dirs = {os.path.dirname(f) for f in base_files}
    cnt = collections.Counter()
    for f in new:
        parts = f.split("/")
        for depth in range(1, min(len(parts), 4)):
            d = "/".join(parts[:depth]) + "/"
            if d.rstrip("/") not in base_dirs:
                cnt[d] += 1
                break
    return sorted(d for d, n in cnt.items() if n >= 25), tgt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("analysis")
    ap.add_argument("--parallel", nargs="*", default=None)
    ap.add_argument("--no-counterparts", action="store_true")
    a = ap.parse_args()
    d = json.load(open(a.analysis))
    repo = d["target"].get("repo_root") or d["target"]["folder"]
    tref = d["target"]["ref"]

    # ---- 1. IB metadata
    ib = []
    for it in d["items"]:
        if not it["file"].endswith(IB_EXT) or it.get("decided_by") == "developer":
            continue
        sm, bm, tm = marked(it.get("source")), marked(it.get("base")), marked(it.get("target"))
        if not sm or not bm:
            continue
        if sorted(map(ib_norm, sm)) == sorted(map(ib_norm, bm)):
            it["ai_category"] = "IB_METADATA"
            it["needs_decision"] = False
            it["severity"] = "info"
            it["recommended_option"] = "TARGET"
            it["ai_confidence"] = 0.99
            it["ai_analysis"] = ("Only Interface Builder metadata differs (client module name with customModuleProvider=\"target\", "
                                 "toolsVersion / plugIn version). No runtime behaviour changes.")
            it["ai_recommendation"] = "Keep target's metadata lines; take every other change in this file normally."
            it["ai_evidence"] = "rule: changed lines are identical after removing customModule (provider=target) / toolsVersion / version attributes"
            it["check_verdict"] = "agree"
            it["check_note"] = "rule-based (classify_items.py): metadata-only diff, verified line by line against base"
            it["check_by"] = "rule"
            ib.append(it["id"])

    # ---- 2. counterparts in parallel modules
    cp_items = []
    if not a.no_counterparts:
        cfg = {}
        try:
            cfg = json.load(open(os.path.join(d["target"]["folder"], ".merge-guard.json")))
        except Exception:
            pass
        par = a.parallel if a.parallel is not None else cfg.get("parallel_modules")
        par_auto, tfiles = detect_parallel(repo, d.get("analysis_base") or d.get("merge_base"), tref)
        if par is None:
            par = par_auto
        par = [p if p.endswith("/") else p + "/" for p in par]
        d["parallel_modules"] = par
        pfiles = [f for f in tfiles if any(f.startswith(p) for p in par)]
        index = collections.defaultdict(list)
        for f in pfiles:
            index[stem(f).lower()].append(f)
        for it in d["items"]:
            cat = it.get("ai_category") or it["category"]
            path = it.get("target_path") or it["file"]
            if cat in CODE_SKIP or any(path.startswith(p) for p in par):
                continue
            s = stem(path).lower()
            if len(s) < 6 or s in GENERIC:
                continue
            hits = sorted({f for k, fs in index.items() if same_thing(s, k) for f in fs})[:4]
            if not hits:
                continue
            toks = key_tokens(marked(it.get("source")))
            cps = []
            for f in hits:
                txt = git(repo, "show", f"{tref}:{f}")
                cps.append({"path": f, "uses": [t for t in toks if t in txt], "missing": [t for t in toks if t not in txt]})
            it["counterparts"] = cps
            sig = "parallel implementation in target: " + ", ".join(
                os.path.basename(c["path"]) + (f" (does not use {', '.join(c['missing'][:3])})" if c["missing"] else "") for c in cps)
            it.setdefault("signals", [])
            it["signals"] = [x for x in it["signals"] if not x.startswith("parallel implementation in target:")] + [sig]
            cp_items.append(it["id"])

    d["classify"] = {"ib_metadata": ib, "counterparts": cp_items, "parallel_modules": d.get("parallel_modules", [])}
    json.dump(d, open(a.analysis, "w"), indent=1)
    print(f"IB metadata-only items (kept as target): {len(ib)}")
    print(f"parallel modules: {', '.join(d.get('parallel_modules') or []) or 'none'}")
    print(f"items with a look-alike in a parallel module: {len(cp_items)}")
    for it in d["items"]:
        if it["id"] in cp_items:
            print(f"  {it['id']} {it.get('ai_category') or it['category']} {it['file']} → " +
                  "; ".join(c["path"] + (f" (missing: {', '.join(c['missing'])})" if c["missing"] else "") for c in it["counterparts"]))
    if cp_items:
        print("Next: for each item above, read the counterpart and set counterpart_verdict = port | not-needed and counterpart_note.")


if __name__ == "__main__":
    main()
