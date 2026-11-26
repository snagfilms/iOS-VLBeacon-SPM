#!/usr/bin/env python3
"""
quality_scan.py — risk and quality signals for the merge report (read-only; never edits the repo).

Writes <report>/quality.json, which render_report.py shows in the "Quality & risk" section and on every card:
  files         per-file risk score 0-100 from churn (commits in the last N days on target), distinct authors,
                whether any test references the file's types/functions, how sensitive the area is (SSAI, analytics,
                DRM, payments …) and the severity/number of merge items in it
  items         per item: platform context (#if os(tvOS) / os(iOS) / targetEnvironment, *_tvOS files),
                tests that reference the changed type/function, new SwiftLint warnings on the merged lines
  lint          SwiftLint run on every changed Swift file in the merged tree vs. the same file at target HEAD;
                only warnings that are NEW after the merge are reported (and flagged when they sit on merged lines)
  periphery     unused-code scan (only with --periphery; it builds the project, so it is slow)
  dependencies  Package.resolved / Podfile.lock / Cartfile.resolved pins at base, source, target and the merged tree,
                plus modules the build logs could not resolve (build-logs/*.log "Unable to resolve module dependency")

Usage: quality_scan.py <report>/analysis.json [--tree <merged working tree>] [--days 180] [--periphery] [--no-lint]
Exit 0 always (missing tools are recorded as "not available", never guessed).
"""
import argparse, collections, datetime, glob, json, os, re, shutil, subprocess, sys, tempfile

SENSITIVE_HIGH = re.compile(r"DRM|FairPlay|Payment|Purchase|StoreKit|IAP|Subscription|Auth|Login|Token|Keychain|Entitlement|Crypto", re.I)
SENSITIVE_MED = re.compile(r"SSAI|Analytics|Tracking|Tracker|Beacon|Ads?\b|AdBreak|IMA|Subtitle|Caption|Cast|Download|Offline|Network", re.I)
TEST_PATH = re.compile(r"(^|/)[^/]*Tests?(/|\.swift$|\.m$)|(^|/)Tests?/", re.I)
GENERIC_DIRS = {"sources", "source", "src", "classes", "commonfiles", "common", "vlplayer", "vlvideoplayer", "player classes",
                "appcms", "app", "lib", "views", "view", "controllers", "controller", "models", "model", "helpers", "utils",
                "extensions", "managers", "manager", "sdkmanager"}
SEV_W = {"high": 15, "medium": 9, "low": 4, "info": 1}
IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]{3,}")
SWIFT_KW = set("""func var let if else guard return self Self true false nil class struct enum protocol extension import case switch default
for while in do try catch throw throws async await static private fileprivate internal public open override final lazy weak unowned
init deinit super where is as some any inout mutating get set willSet didSet typealias associatedtype defer break continue repeat
String Int Bool Double Float Any AnyObject Void Optional Array Dictionary Set UIView NSObject DispatchQueue main""".split())


def git(repo, *args, ok=(0,)):
    p = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, errors="replace")
    return p.stdout if p.returncode in ok else None


def show(repo, sha, path):
    if not sha or not path:
        return None
    return git(repo, "show", f"{sha}:{path}")


# ---------------------------------------------------------------- platform context
DIRECTIVE = re.compile(r"^\s*#\s*(if|elseif|else|endif)\b\s*(.*)$")
PLATFORM = re.compile(r"os\(\s*(\w+)\s*\)|targetEnvironment\(\s*(\w+)\s*\)|canImport\(\s*(\w+)\s*\)")


def platform_stack(text, line_no):
    """Active #if conditions (outermost first) at 1-based line_no."""
    stack = []
    for i, raw in enumerate((text or "").splitlines(), 1):
        if i >= line_no:
            break
        m = DIRECTIVE.match(raw)
        if not m:
            continue
        kw, cond = m.group(1), m.group(2).split("//")[0].strip()
        if kw == "if":
            stack.append(cond)
        elif kw == "elseif" and stack:
            stack[-1] = cond
        elif kw == "else" and stack:
            stack[-1] = "!(" + stack[-1] + ")" if not stack[-1].startswith("!(") else stack[-1][2:-1]
        elif kw == "endif" and stack:
            stack.pop()
    return [c for c in stack if PLATFORM.search(c)]


def label_platform(conds):
    out = []
    for c in conds:
        neg = c.startswith("!(")
        names = [a or b or k for a, b, k in PLATFORM.findall(c)]
        if not names:
            continue
        out.append(("not " if neg else "") + " / ".join(names))
    return out


def snippet_line(snip):
    if not snip:
        return None
    mk = snip.get("marked") or []
    return snip["start"] + (mk[0] if mk else 0)


def platform_for(item, repo, shas, cache):
    found = []
    path_l = (item.get("target_path") or item["file"])
    if re.search(r"_tvOS|tvOS/|/tvos/", path_l, re.I):
        found.append("tvOS file")
    elif re.search(r"_iOS\b|iOS/", path_l):
        found.append("iOS file")
    for side, sha, path in (("target", shas["target"], item.get("target_path")), ("source", shas["source"], item["file"])):
        ln = snippet_line(item.get(side))
        if not ln or not path:
            continue
        key = (sha, path)
        if key not in cache:
            cache[key] = show(repo, sha, path)
        for lab in label_platform(platform_stack(cache[key], ln)):
            tag = f"#if {lab}"
            if tag not in found:
                found.append(tag)
        for raw in (item.get(side) or {}).get("lines", []):        # the change itself adds/edits a platform branch
            if DIRECTIVE.match(raw) and PLATFORM.search(raw):
                tag = "edits " + raw.strip()[:60]
                if tag not in found:
                    found.append(tag)
    return found


# ---------------------------------------------------------------- symbols + tests
def symbols_of(item):
    names = []
    for k in ("source_symbol", "target_symbol"):
        v = item.get(k)
        if v:
            names += re.findall(r"[A-Za-z_]\w+", v.split("(")[0])
    for side in ("source", "target", "base"):
        snip = item.get(side) or {}
        lines = snip.get("lines") or []
        mk = snip.get("marked") or []
        upto = (max(mk) if mk else len(lines) - 1)
        for raw in reversed(lines[:upto + 1]):                     # enclosing function
            m = re.search(r"\bfunc\s+([A-Za-z_]\w*)", raw)
            if m:
                names.append(m.group(1)); break
    base = os.path.splitext(os.path.basename(item.get("target_path") or item["file"]))[0]
    names.append(base.split("+")[0])
    return [n for n in dict.fromkeys(names) if len(n) > 3 and n not in SWIFT_KW]


def test_refs(repo, sha, names, test_files, cache, type_name):
    """{test file: [matched names]} — a match on a function name is stronger than on the type name alone."""
    hits = collections.defaultdict(list)
    for n in names:
        if n not in cache:
            out = git(repo, "grep", "-l", "-w", "-F", "-e", n, sha, "--", *test_files, ok=(0, 1)) if test_files else ""
            cache[n] = sorted({l.split(":", 1)[1] for l in (out or "").splitlines() if ":" in l})
        for f in cache[n]:
            hits[f].append(n)
    return [{"file": f, "names": ns, "kind": "type only" if ns == [type_name] else "function"} for f, ns in sorted(hits.items())]


# ---------------------------------------------------------------- swiftlint
def swiftlint_version():
    exe = shutil.which("swiftlint")
    if not exe:
        return None
    p = subprocess.run([exe, "version"], capture_output=True, text=True)
    return p.stdout.strip() or "unknown"


def lint_text(text, name, config, tmpdir):
    d = tempfile.mkdtemp(dir=tmpdir)
    fp = os.path.join(d, os.path.basename(name))
    with open(fp, "w") as f:
        f.write(text)
    cmd = ["swiftlint", "lint", "--quiet", "--reporter", "json"] + (["--config", config] if config else []) + [fp]
    p = subprocess.run(cmd, capture_output=True, text=True, cwd=d)
    try:
        res = json.loads(p.stdout or "[]")
    except json.JSONDecodeError:
        res = []
    lines = text.splitlines()
    out = []
    for v in res:
        ln = v.get("line") or 0
        out.append({"line": ln, "rule": v.get("rule_id"), "severity": (v.get("severity") or "").lower(),
                    "reason": v.get("reason"), "text": lines[ln - 1].strip() if 0 < ln <= len(lines) else ""})
    return out


def merged_lines(item, tree_lines):
    """1-based line numbers in the merged file that carry the item's source (incoming) changed lines."""
    snip = item.get("source") or {}
    want = [snip["lines"][i].strip() for i in (snip.get("marked") or []) if i < len(snip.get("lines", []))]
    want = [w for w in want if len(w) > 3 and w not in ("}", "{", "})", "]")]
    idx = collections.defaultdict(list)
    for n, l in enumerate(tree_lines, 1):
        idx[l.strip()].append(n)
    hint = snippet_line(snip) or 0
    got = []
    for w in want:
        c = idx.get(w)
        if c:
            got.append(min(c, key=lambda n: abs(n - hint)))
    return sorted(set(got))


# ---------------------------------------------------------------- dependencies
def parse_resolved(text):
    try:
        j = json.loads(text)
    except Exception:
        return {}
    pins = j.get("pins") or (j.get("object") or {}).get("pins") or []
    out = {}
    for p in pins:
        name = p.get("identity") or p.get("package") or p.get("location") or p.get("repositoryURL")
        st = p.get("state") or {}
        out[name] = st.get("version") or (st.get("branch") and f"branch {st['branch']}") or (st.get("revision") or "")[:10]
    return out


def parse_podlock(text):
    out, inpods = {}, False
    for l in (text or "").splitlines():
        if l.startswith("PODS:"):
            inpods = True; continue
        if inpods and l and not l.startswith(" "):
            break
        m = re.match(r"^  - \"?([^\s(\"]+) \(([^)]+)\)", l)
        if inpods and m:
            out[m.group(1)] = m.group(2)
    return out


def parse_cartfile(text):
    out = {}
    for l in (text or "").splitlines():
        m = re.match(r'^\s*(\w+)\s+"([^"]+)"\s+"([^"]+)"', l)
        if m:
            out[m.group(2)] = m.group(3)
    return out


DEP_FILES = [(re.compile(r"(^|/)Package\.resolved$"), parse_resolved, "SwiftPM"),
             (re.compile(r"(^|/)Podfile\.lock$"), parse_podlock, "CocoaPods"),
             (re.compile(r"(^|/)Cartfile\.resolved$"), parse_cartfile, "Carthage")]


def dependency_diff(repo, shas, tree):
    files = set()
    for sha in shas.values():
        for p in (git(repo, "ls-tree", "-r", "--name-only", sha) or "").splitlines():
            if any(rx.search(p) for rx, _, _ in DEP_FILES):
                files.add(p)
    out = []
    for path in sorted(files):
        parser, kind = next((fn, k) for rx, fn, k in DEP_FILES if rx.search(path))
        ver = {side: parser(show(repo, sha, path) or "") for side, sha in shas.items()}
        tp = os.path.join(tree, path) if tree else None
        ver["merged"] = parser(open(tp).read()) if tp and os.path.exists(tp) else {}
        rows = []
        for name in sorted(set().union(*ver.values()), key=str.lower):
            b, s, t, m = (ver[k].get(name) for k in ("base", "source", "target", "merged"))
            if b == s == t == m:
                continue
            if s != b and t != b and s != t:
                change = "both changed — differ"
            elif s != b and t == b:
                change = "source changed"
            elif t != b and s == b:
                change = "target changed"
            elif s == t != b:
                change = "both changed — same"
            else:
                change = "merged tree differs"
            if tree and ver["merged"] and m not in (s, t):
                change += " · merged tree has neither side"
            rows.append({"name": name, "base": b, "source": s, "target": t, "merged": m, "change": change})
        out.append({"file": path, "kind": kind, "rows": rows})
    return out


def build_missing_modules(folder):
    mods = collections.defaultdict(set)
    for fp in glob.glob(os.path.join(folder, "build-logs", "*.log")):
        try:
            txt = open(fp, errors="replace").read()
        except OSError:
            continue
        for m in re.finditer(r"[Uu]nable to resolve module dependency: '([^']+)'|no such module '([^']+)'", txt):
            mods[m.group(1) or m.group(2)].add(os.path.basename(fp)[:-4])
    return [{"module": k, "logs": sorted(v)} for k, v in sorted(mods.items())]


# ---------------------------------------------------------------- main
def area_of(path):
    parts = [p for p in os.path.dirname(path).split("/") if p]
    keep = [p for p in parts if p.lower() not in GENERIC_DIRS]
    return keep[-1] if keep else (parts[-1] if parts else "(root)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("analysis")
    ap.add_argument("--tree", help="merged working tree (default: target folder)")
    ap.add_argument("--days", type=int, default=180)
    ap.add_argument("--periphery", action="store_true", help="also run `periphery scan` (builds the project; slow)")
    ap.add_argument("--no-lint", action="store_true")
    a = ap.parse_args()
    d = json.load(open(a.analysis))
    folder = os.path.dirname(os.path.abspath(a.analysis))
    repo = d["target"]["repo_root"] if d["target"].get("repo_root") else d["target"]["folder"]
    tree = a.tree or d["target"]["folder"]
    shas = {"base": d.get("analysis_base") or d.get("merge_base"), "source": d["source"]["head"], "target": d["target"]["head"]}
    if not git(repo, "cat-file", "-t", shas["source"]):
        shas["source"] = d["source"].get("ref") or shas["source"]
    items = d["items"]

    all_files = (git(repo, "ls-tree", "-r", "--name-only", shas["target"]) or "").splitlines()
    test_files = [p for p in all_files if TEST_PATH.search(p) and p.endswith((".swift", ".m", ".mm"))]

    file_cache, test_cache = {}, {}
    q_items = {}
    by_file = collections.defaultdict(list)
    for it in items:
        fpath = it.get("target_path") or it["file"]
        by_file[fpath].append(it)
        syms = symbols_of(it)
        q_items[it["id"]] = {"platform": platform_for(it, repo, shas, file_cache), "symbols": syms,
                             "tests": test_refs(repo, shas["target"], syms, test_files, test_cache,
                                               os.path.splitext(os.path.basename(fpath))[0].split("+")[0]),
                             "area": area_of(fpath), "lint": []}

    # ---- per-file risk
    since = f"--since={a.days}.days"
    files = {}
    for fpath, its in by_file.items():
        log = git(repo, "log", since, "--format=%an", shas["target"], "--", fpath) or ""
        names = [l for l in log.splitlines() if l]
        commits, authors = len(names), len(set(names))
        tested = any(t["kind"] == "function" for i in its for t in q_items[i["id"]]["tests"]) and "function" or \
            any(q_items[i["id"]]["tests"] for i in its) and "type only" or ""
        sens = "high" if SENSITIVE_HIGH.search(fpath) else "medium" if SENSITIVE_MED.search(fpath) else "low"
        maxsev = min((i.get("severity") or "info" for i in its), key=lambda s: list(SEV_W).index(s) if s in SEV_W else 9)
        f = {"churn": round(min(commits, 20) / 20 * 20), "authors": round(min(authors, 5) / 5 * 15),
             "tests": {"function": 0, "type only": 12}.get(tested, 20), "sensitive": {"high": 20, "medium": 10, "low": 0}[sens],
             "severity": SEV_W.get(maxsev, 1), "items": round(min(len(its), 6) / 6 * 10)}
        score = min(100, sum(f.values()))
        files[fpath] = {"score": score, "level": "high" if score >= 60 else "medium" if score >= 35 else "low",
                        "commits": commits, "authors": authors, "days": a.days, "tested": tested, "sensitive": sens,
                        "max_severity": maxsev, "items": [i["id"] for i in its], "parts": f, "area": area_of(fpath)}

    # ---- swiftlint: new warnings after the merge, per changed Swift file
    lint = {"tool": None, "status": "skipped (--no-lint)" if a.no_lint else "", "files": {}, "new_total": 0, "on_merged_lines": 0}
    if not a.no_lint:
        lint["tool"] = swiftlint_version()
        if not lint["tool"]:
            lint["status"] = "not available — install with `brew install swiftlint`"
        else:
            cfg = next((os.path.join(tree, n) for n in (".swiftlint.yml", ".swiftlint.yaml") if os.path.exists(os.path.join(tree, n))), None)
            lint["config"] = os.path.relpath(cfg, tree) if cfg else "SwiftLint defaults (no .swiftlint.yml in repo)"
            tmp = tempfile.mkdtemp(prefix="merge-quality-")
            try:
                for fpath, its in by_file.items():
                    tp = os.path.join(tree, fpath)
                    if not fpath.endswith(".swift") or not os.path.exists(tp):
                        continue
                    now_text = open(tp, errors="replace").read()
                    head_text = show(repo, shas["target"], fpath) or ""
                    before = collections.Counter((v["rule"], v["text"]) for v in lint_text(head_text, fpath, cfg, tmp))
                    after = lint_text(now_text, fpath, cfg, tmp)
                    tree_lines = now_text.splitlines()
                    mline = {i["id"]: set(merged_lines(i, tree_lines)) for i in its}
                    new = []
                    for v in after:
                        k = (v["rule"], v["text"])
                        if before[k] > 0:
                            before[k] -= 1; continue
                        v["items"] = [iid for iid, ls in mline.items() if v["line"] in ls]
                        new.append(v)
                        for iid in v["items"]:
                            q_items[iid]["lint"].append(v)
                    lint["files"][fpath] = {"new": new, "total_after": len(after)}
                    lint["new_total"] += len(new)
                    lint["on_merged_lines"] += sum(1 for v in new if v["items"])
                lint["status"] = "ok"
            finally:
                shutil.rmtree(tmp, ignore_errors=True)

    # ---- periphery (opt-in)
    peri = {"status": "not run — pass --periphery (it builds the project, several minutes)"}
    if a.periphery:
        if not shutil.which("periphery"):
            peri = {"status": "not available — install with `brew install peripheryapp/periphery/periphery`"}
        else:
            p = subprocess.run(["periphery", "scan", "--format", "json", "--quiet"], capture_output=True, text=True, cwd=tree)
            try:
                res = json.loads(p.stdout or "[]")
                changed = set(by_file)
                hits = [{"file": os.path.relpath(r.get("location", "").split(":")[0], tree), "line": r.get("location", "").split(":")[1:2],
                         "kind": r.get("kind"), "name": r.get("name"), "hint": r.get("hints")} for r in res]
                peri = {"status": "ok", "unused_in_changed_files": [h for h in hits if h["file"] in changed], "total": len(hits)}
            except json.JSONDecodeError:
                peri = {"status": "failed — " + (p.stderr or p.stdout)[-400:]}

    out = {"schema": "quality/1", "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
           "tree": tree, "shas": shas, "test_files": len(test_files),
           "files": files, "items": q_items, "lint": lint, "periphery": peri,
           "dependencies": dependency_diff(repo, shas, tree), "build_missing_modules": build_missing_modules(folder)}
    dst = os.path.join(folder, "quality.json")
    with open(dst, "w") as f:
        json.dump(out, f, indent=1)
    hi = sum(1 for v in files.values() if v["level"] == "high")
    print(f"written: {dst}")
    print(f"files: {len(files)} ({hi} high risk) · test files scanned: {len(test_files)} · "
          f"lint: {lint['status']} ({lint['new_total']} new, {lint['on_merged_lines']} on merged lines) · "
          f"dependency files: {len(out['dependencies'])} · unresolved build modules: {len(out['build_missing_modules'])}")


if __name__ == "__main__":
    main()
