#!/usr/bin/env python3
"""
collect_changes.py — READ-ONLY analysis of everything merging SOURCE into TARGET would bring.

It never touches either working tree. When the two folders are different checkouts it fetches
the source branch into the target repo as refs/merge-guard/source (a private ref, nothing else).

Every change on the source side (since the merge-base, or since --since) becomes one or more
"items". Each item carries: file path in source, mapped path in target (handles moved/renamed/
restructured folders), base/source/target snippets with line numbers, the developers + dates of
the commits on both sides, a preliminary category, and empty AI fields the agent fills in.

Usage:
  collect_changes.py --source-folder S --source-branch Develop \
                     --target-folder T --target-branch Develop_Analytics \
                     --out ~/Downloads/merge-reports/<REPORT_ID> \
                     [--report-id ID] [--tool "Claude Code"] [--session-id X] [--resume-hint "..."] \
                     [--since <commit|YYYY-MM-DD>] [--protect GLOB ...] [--context 4]

Output: <out>/analysis.json  (+ a short summary on stdout)
"""
import argparse, datetime, fnmatch, json, os, plistlib, re, subprocess, sys
from collections import defaultdict
from difflib import SequenceMatcher
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import symbols as SYM

BINARY = object()
TRIVIAL = {"", "{", "}", "(", ")", "[", "]", "});", "})", "};", "],", "),", "} else {", "else {", "else",
           "return", "break", "default:", "#endif", "#else", "*/", "/*", "//", "end", "@end", "}()", "]", ")"}
DEFAULT_PROTECT = ["**/Package.resolved", "Package.resolved", "**/Podfile.lock", "Podfile.lock",
                   "**/*.entitlements", "**/GoogleService-Info*.plist"]
LARGE_FILE = 1_500_000
# names shared by many unrelated files: never map these by file name alone (parent folder must match too)
GENERIC_NAMES = {"Info.plist", "Contents.json", "CodeResources", "Package.swift", "Package.resolved", "README.md", "README",
                 "module.modulemap", "LICENSE", "LICENSE.md", "CHANGELOG.md", "index.js", "index.ts", "main.swift", "main.m",
                 "AppDelegate.swift", "SceneDelegate.swift", "Localizable.strings", "InfoPlist.strings", "PrivacyInfo.xcprivacy",
                 "project.pbxproj", "contents.xcworkspacedata", "IDEWorkspaceChecks.plist", "WorkspaceSettings.xcsettings",
                 "Podfile", "Podfile.lock", "build.gradle", "AndroidManifest.xml", "strings.xml", "__init__.py", "CMakeLists.txt",
                 "Makefile", "Headers", "Modules", "Constants.swift", "Extensions.swift", "Utils.swift", "Config.swift"}
# vendored binary bundles are handled as ONE unit (present / removed / replaced by a package), never file by file
BUNDLE_RE = re.compile(r"^((?:[^/]+/)*?)([^/]+\.(?:xcframework|framework|bundle))/(.+)$")
NOISE_DIRS = {"xcuserdata", "DerivedData", ".build", "Pods", "node_modules", "build"}
DECL_RE = re.compile(r"^\s*(?:@\w+\s+)*(?:(?:public|private|fileprivate|internal|open|final|static)\s+)*"
                     r"(?:class|struct|enum|protocol|actor|extension)\s+([A-Za-z_][A-Za-z0-9_]*)", re.M)
OBJC_DECL_RE = re.compile(r"^\s*@(?:interface|implementation|protocol)\s+([A-Za-z_][A-Za-z0-9_]*)", re.M)


# ----------------------------------------------------------------------------- git helpers
def run(args, cwd=None, check=True, binary=False):
    r = subprocess.run(args, cwd=cwd, capture_output=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"{' '.join(args)} failed: {r.stderr.decode(errors='replace').strip()}")
    return r.stdout if binary else r.stdout.decode("utf-8", errors="replace")


def git(repo, *args, check=True, binary=False):
    return run(["git", "-C", repo, *args], check=check, binary=binary)


def git_try(repo, *args):
    r = subprocess.run(["git", "-C", repo, *args], capture_output=True)
    return r.returncode == 0, r.stdout.decode("utf-8", errors="replace").strip()


_blob_cache = {}
def show(repo, ref, path):
    key = (repo, ref, path)
    if key in _blob_cache:
        return _blob_cache[key]
    r = subprocess.run(["git", "-C", repo, "show", f"{ref}:{path}"], capture_output=True)
    if r.returncode != 0:
        val = None
    elif b"\0" in r.stdout[:8000]:
        val = BINARY
    else:
        val = r.stdout.decode("utf-8", errors="replace")
    _blob_cache[key] = val
    return val


def blob_size(repo, ref, path):
    ok, out = git_try(repo, "cat-file", "-s", f"{ref}:{path}")
    return int(out) if ok and out.isdigit() else 0


def name_status(repo, a, b):
    out = git(repo, "diff", "-M50%", "--name-status", "-z", "--no-color", a, b)
    parts = out.split("\0")
    res, i = [], 0
    while i < len(parts) and parts[i]:
        st = parts[i]
        if st[0] in "RC":
            res.append((st[0], int(st[1:] or 100), parts[i + 1], parts[i + 2])); i += 3
        else:
            res.append((st[0], 100, parts[i + 1], parts[i + 1])); i += 2
    return res


HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
def hunks_between(repo, a_spec, b_spec):
    """Zero-context hunks between two blobs, as 0-based half-open ranges [bs,be) -> [ts,te)."""
    out = git(repo, "diff", "-U0", "--no-color", "--no-ext-diff", "--diff-algorithm=histogram",
              a_spec, b_spec, check=False)
    hs = []
    for line in out.splitlines():
        m = HUNK_RE.match(line)
        if not m:
            continue
        a, ac, b, bc = int(m.group(1)), m.group(2), int(m.group(3)), m.group(4)
        ac = 1 if ac is None else int(ac)
        bc = 1 if bc is None else int(bc)
        bs = a if ac == 0 else a - 1          # insertion after line a -> point at index a
        ts = b if bc == 0 else b - 1
        hs.append({"bs": bs, "be": bs + ac, "ts": ts, "te": ts + bc})
    return hs


def to_target(L, hunks, mode):
    off = 0
    for h in hunks:
        if h["be"] < L or (h["be"] == L and (h["bs"] < L or mode == "end")):
            off += (h["te"] - h["ts"]) - (h["be"] - h["bs"])
        elif h["bs"] <= L < h["be"] or (h["bs"] == L == h["be"]):
            return h["ts"] if mode == "start" else h["te"]
        else:
            break
    return L + off


_meta_cache = {}
def commit_meta(repo, sha):
    """Author/date/subject of a commit, plus the original author when it is a cherry-pick/port of another commit."""
    if sha in _meta_cache:
        return _meta_cache[sha]
    out = git(repo, "show", "-s", "--format=%cn%x1f%an%x1f%ae%x1f%at%x1f%s%x1f%B", sha, check=False)
    committer, _, out = out.partition("\x1f")
    p = out.split("\x1f", 4)
    m = {"sha": sha, "short": sha[:9], "name": p[0] if p else "?", "email": p[1] if len(p) > 1 else "",
         "ts": int(p[2]) if len(p) > 2 and p[2].strip().isdigit() else 0, "subject": p[3] if len(p) > 3 else ""}
    m["date"] = datetime.datetime.fromtimestamp(m["ts"]).strftime("%Y-%m-%d %H:%M")
    if committer and committer != m["name"]:
        m["committer"] = committer
    cp = re.search(r"cherry picked from commit ([0-9a-f]{7,40})", p[4] if len(p) > 4 else "")
    if cp:
        ok, o = git_try(repo, "show", "-s", "--format=%an%x1f%ae%x1f%at%x1f%s", cp.group(1))
        q = o.split("\x1f")
        if ok and len(q) == 4:
            m["ported_from"] = {"short": cp.group(1)[:9], "name": q[0], "email": q[1], "subject": q[3],
                                "date": datetime.datetime.fromtimestamp(int(q[2])).strftime("%Y-%m-%d %H:%M")}
    _meta_cache[sha] = m
    return m


def blame(repo, ref, path, start, end, commit_filter, since_ts=None, role="wrote"):
    """Who wrote lines [start,end) (0-based) at ref:path — line-exact, limited to commits in commit_filter.
    Each entry: name, email, date, short, subject, role, line_numbers (1-based, in ref:path)."""
    if end <= start:
        return []
    found = {}
    for ws_flag in (["-w"], []):            # -w ignores whitespace-only edits; retry without it if nothing found
        out = git(repo, "blame", "--line-porcelain", *ws_flag, "-L", f"{start + 1},{end}", ref, "--", path, check=False)
        cur = None
        for line in out.splitlines():
            m = re.match(r"^([0-9a-f]{40}) \d+ (\d+)", line)
            if m:
                cur = {"sha": m.group(1), "final": int(m.group(2))}
            elif cur is None:
                continue
            elif line.startswith("author-time "):
                cur["ts"] = int(line[12:])
            elif line.startswith("\t"):
                sha = cur["sha"]
                keep = commit_filter is None or sha in commit_filter
                if since_ts is not None and cur.get("ts", 0) < since_ts:
                    keep = False
                if keep:
                    found.setdefault(sha, []).append(cur["final"])
                cur = None
        if found:
            break
    res = []
    for sha, lns in found.items():
        e = dict(commit_meta(repo, sha)); e.update(role=role, line_numbers=sorted(lns), lines=len(lns))
        res.append(e)
    return sorted(res, key=lambda x: -x["ts"])


def deleters(repo, rng, paths, numbered_lines, role="deleted"):
    """Who removed these lines (exact): first commit in rng whose diff deletes each line.
    numbered_lines: [(1-based line number in the base file, text)]."""
    want = defaultdict(list)
    for ln, txt in numbered_lines:
        n = norm(txt)
        if n and n not in TRIVIAL:
            want[n].append(ln)
    if not want:
        return []
    paths = [p for p in dict.fromkeys(paths) if p]
    shas = git(repo, "log", "--reverse", "--no-merges", "--format=%H", rng, "--", *paths, check=False).split()
    found = defaultdict(list)
    for sha in shas:
        if not want:
            break
        diff = git(repo, "show", "--format=", "-U0", "--no-color", sha, "--", *paths, check=False)
        for l in diff.splitlines():
            if l.startswith("-") and not l.startswith("---"):
                n = norm(l[1:])
                if n in want:
                    found[sha] += want.pop(n)
    res = []
    for sha, lns in found.items():
        e = dict(commit_meta(repo, sha)); e.update(role=role, line_numbers=sorted(lns), lines=len(lns))
        res.append(e)
    return sorted(res, key=lambda x: -x["ts"])


def combine(wrote, removed, side):
    """One entry per commit: line_numbers = lines it wrote (in the branch file), base_line_numbers = base lines it removed."""
    by = {}
    for e in wrote:
        x = by.setdefault(e["sha"], dict(e, line_numbers=[], base_line_numbers=[]))
        x["line_numbers"] = sorted(set(x["line_numbers"] + e["line_numbers"]))
    for e in removed:
        x = by.setdefault(e["sha"], dict(e, line_numbers=[], base_line_numbers=[]))
        x["base_line_numbers"] = sorted(set(x["base_line_numbers"] + e["line_numbers"]))
    for x in by.values():
        x["role"] = (f"changed {side} lines" if x["line_numbers"] and x["base_line_numbers"] else
                     f"added {side} lines" if x["line_numbers"] else f"removed base lines in {side}")
        x["lines"] = len(x["line_numbers"]) or len(x["base_line_numbers"])
    return sorted(by.values(), key=lambda x: -x["ts"])


def gutter(snip, authors, key="line_numbers"):
    """Attach author names to the snippet lines they own (shown next to the code in the report)."""
    if not snip:
        return snip
    g = {}
    for a in authors:
        for ln in a.get(key, []):
            i = ln - snip["start"]
            if 0 <= i < len(snip["lines"]):
                g[str(i)] = a["name"]
    snip["authors"] = g
    return snip


def file_commits(repo, rng, path, limit=5, note="commit touching this file (exact line author not tracked)"):
    out = git(repo, "log", "--no-merges", f"-{limit}", "--format=%H%x1f%an%x1f%ae%x1f%at%x1f%s", rng, "--", path, check=False)
    res = []
    for line in out.splitlines():
        p = line.split("\x1f")
        if len(p) == 5:
            res.append({"sha": p[0], "short": p[0][:9], "name": p[1], "email": p[2], "ts": int(p[3]),
                        "date": datetime.datetime.fromtimestamp(int(p[3])).strftime("%Y-%m-%d %H:%M"),
                        "subject": p[4], "lines": None, "note": note})
    return res


# ----------------------------------------------------------------------------- text helpers
def norm(s):
    return re.sub(r"\s+", " ", s.strip())


def nontrivial(lines):
    res = []
    for l in lines:
        n = norm(l)
        if n in TRIVIAL or len(n) < 4 or re.fullmatch(r"[\W_]+", n):
            continue
        res.append(n)
    return res


def kind_of(path):
    p = path.lower()
    if p.endswith("project.pbxproj"): return "pbxproj"
    if p.endswith("package.resolved"): return "package-resolved"
    for ext, k in ((".swift", "swift"), (".m", "objc"), (".mm", "objc"), (".h", "objc-header"), (".plist", "plist"),
                   (".strings", "strings"), (".xcconfig", "xcconfig"), (".storyboard", "interface"), (".xib", "interface"),
                   (".json", "json"), (".entitlements", "entitlements"), (".sh", "script"), (".rb", "script"),
                   (".kt", "kotlin"), (".java", "java"), (".ts", "ts"), (".js", "js"), (".py", "python")):
        if p.endswith(ext): return k
    return "other"


def snippet(lines, start, end, ctx, marks):
    """lines[start-ctx:end+ctx] with 1-based numbering and marked (changed) line indices."""
    s, e = max(0, start - ctx), min(len(lines), end + ctx)
    return {"start": s + 1, "lines": lines[s:e], "marked": [i - s for i in marks if s <= i < e]}


def protected(path, globs):
    return any(fnmatch.fnmatch(path, g) or fnmatch.fnmatch(os.path.basename(path), g) for g in globs)


def similarity(a, b):
    if a is None or b is None or a is BINARY or b is BINARY:
        return 0.0
    al, bl = a.splitlines(), b.splitlines()
    sm = SequenceMatcher(None, al, bl, autojunk=False)
    if len(al) + len(bl) > 8000:
        return sm.quick_ratio()
    return sm.ratio()


# ----------------------------------------------------------------------------- pbxproj / Package.resolved summaries
PBX_FILEREF_RE = re.compile(r"/\* ([^*]+?) \*/ = \{isa = PBXFileReference;[^}]*?path = \"?([^;\"]+)\"?;")
PBX_PKG_RE = re.compile(r"XCRemoteSwiftPackageReference \"([^\"]+)\" \*/ = \{\s*isa = XCRemoteSwiftPackageReference;\s*"
                        r"repositoryURL = \"?([^;\"]+)\"?;\s*requirement = \{([^}]*)\}", re.S)
PBX_BUILDFILE_RE = re.compile(r"/\* (\S[^*]*?) in (Sources|Resources|Frameworks|Embed[^*]*|CopyFiles) \*/ = \{isa = PBXBuildFile;")
PBX_TARGET_RE = re.compile(r"/\* ([^*]+?) \*/ = \{\s*isa = PBXNativeTarget;")


def pbx_summary(text):
    if not text or text is BINARY:
        return {"files": set(), "packages": {}, "buildfiles": defaultdict(int), "targets": set()}
    pk = {}
    for m in PBX_PKG_RE.finditer(text):
        req = " ".join(norm(x) for x in m.group(3).split(";") if x.strip())
        pk[m.group(1)] = f"{m.group(2)} [{req}]"
    bf = defaultdict(int)
    for m in PBX_BUILDFILE_RE.finditer(text):
        bf[f"{m.group(1)} ({m.group(2)})"] += 1
    return {"files": {m.group(2) for m in PBX_FILEREF_RE.finditer(text)}, "packages": pk, "buildfiles": bf,
            "targets": {m.group(1) for m in PBX_TARGET_RE.finditer(text)}}


def resolved_pins(text):
    try:
        d = json.loads(text)
    except Exception:
        return {}
    pins = d.get("pins") or d.get("object", {}).get("pins") or []
    res = {}
    for p in pins:
        name = p.get("identity") or p.get("package")
        st = p.get("state", {})
        res[name] = " ".join(f"{k}={st[k]}" for k in ("branch", "version", "revision") if st.get(k))
    return res


# ----------------------------------------------------------------------------- main analysis
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source-folder", required=True)
    ap.add_argument("--source-branch", required=True)
    ap.add_argument("--target-folder", required=True)
    ap.add_argument("--target-branch", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--report-id")
    ap.add_argument("--tool", default="unknown")
    ap.add_argument("--session-id", default="")
    ap.add_argument("--resume-hint", default="")
    ap.add_argument("--since", help="baseline commit or date on the source branch (required when histories are unrelated; "
                                    "older than the merge-base = deep audit for previously lost code)")
    ap.add_argument("--protect", nargs="*", default=[])
    ap.add_argument("--ignore", nargs="*", default=[], help="extra globs to leave out (noise)")
    ap.add_argument("--map-file", help="JSON {source path or folder/: target path or folder/ (null = not in target)} "
                                      "confirmed by the developer/agent; overrides automatic mapping")
    ap.add_argument("--context", type=int, default=4)
    ap.add_argument("--near", type=int, default=15, help="lines: target change this close = review flag")
    a = ap.parse_args()

    src_dir = os.path.abspath(os.path.expanduser(a.source_folder))
    tgt_dir = os.path.abspath(os.path.expanduser(a.target_folder))
    out_dir = os.path.abspath(os.path.expanduser(a.out))
    os.makedirs(out_dir, exist_ok=True)
    repo = git(tgt_dir, "rev-parse", "--show-toplevel").strip()
    src_top = git(src_dir, "rev-parse", "--show-toplevel").strip()
    same_checkout = os.path.realpath(repo) == os.path.realpath(src_top)

    tgt_ref = f"refs/heads/{a.target_branch}"
    if same_checkout:
        src_ref = f"refs/heads/{a.source_branch}"
    else:
        git(repo, "fetch", "--no-tags", "--quiet", src_top, f"+refs/heads/{a.source_branch}:refs/merge-guard/source")
        src_ref = "refs/merge-guard/source"
    src_head = git(repo, "rev-parse", src_ref).strip()
    tgt_head = git(repo, "rev-parse", tgt_ref).strip()

    ok, mb = git_try(repo, "merge-base", src_ref, tgt_ref)
    mode = "shared-history" if ok else "unrelated-history"
    base, since_ts, base_note = (mb if ok else None), None, "merge-base"
    if a.since:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}.*", a.since):
            base = git(repo, "rev-list", "-1", f"--before={a.since}", src_ref).strip()
            since_ts = int(datetime.datetime.fromisoformat(a.since[:10]).timestamp())
        else:
            base = git(repo, "rev-parse", a.since).strip()
            since_ts = int(git(repo, "show", "-s", "--format=%at", base).strip())
        base_note = f"--since {a.since}"
        if not base:
            sys.exit(f"Could not resolve --since {a.since} on {a.source_branch}")
    if base is None:
        sys.exit("Histories are unrelated (no merge-base). Re-run with --since <commit|YYYY-MM-DD> on the source branch.")

    src_set = set(git(repo, "rev-list", f"{base}..{src_ref}").split())
    tgt_set = set(git(repo, "rev-list", f"{base}..{tgt_ref}").split()) if mode == "shared-history" else None
    if mode == "shared-history" and a.since and base != mb:
        tgt_set = set(git(repo, "rev-list", f"{mb}..{tgt_ref}").split())

    # commits (with patch-equivalence check: '-' means an equivalent change already exists in target)
    commits = []
    cherry = {}
    if mode == "shared-history":
        for line in git(repo, "cherry", tgt_ref, src_ref, base, check=False).splitlines():
            if len(line) > 2:
                cherry[line[2:].strip()] = line[0]
    for line in git(repo, "log", "--no-merges", "--format=%H%x1f%an%x1f%ae%x1f%at%x1f%s", f"{base}..{src_ref}").splitlines():
        p = line.split("\x1f")
        if len(p) == 5:
            commits.append({"sha": p[0], "short": p[0][:9], "name": p[1], "email": p[2],
                            "date": datetime.datetime.fromtimestamp(int(p[3])).strftime("%Y-%m-%d %H:%M"),
                            "subject": p[4], "already_in_target": cherry.get(p[0]) == "-"})

    src_changes = name_status(repo, base, src_ref)
    tgt_changes = name_status(repo, base, tgt_ref) if mode == "shared-history" else []
    tgt_rename = {old: (new, score) for (st, score, old, new) in tgt_changes if st == "R"}
    tgt_deleted = {old for (st, _, old, _) in tgt_changes if st == "D"}
    tgt_tree = [p for p in git(repo, "ls-tree", "-r", "--name-only", "-z", tgt_ref).split("\0") if p]
    tgt_tree_set = set(tgt_tree)
    by_base = defaultdict(list)
    for p in tgt_tree:
        by_base[os.path.basename(p)].append(p)
    tgt_dirs = set()
    for p in tgt_tree:
        d = os.path.dirname(p)
        while d and d not in tgt_dirs:
            tgt_dirs.add(d); d = os.path.dirname(d)
    globs = DEFAULT_PROTECT + (a.protect or [])

    # ---------------- structure awareness ----------------
    base_tree = [p for p in git(repo, "ls-tree", "-r", "--name-only", "-z", base).split("\0") if p]
    base_by_name = defaultdict(list)
    for p in base_tree:
        base_by_name[os.path.basename(p)].append(p)

    def is_generic(name):
        return name in GENERIC_NAMES or name.startswith(".") or len(by_base.get(name, [])) >= 3

    def is_noise(path):
        parts = path.split("/")
        return (any(x in NOISE_DIRS for x in parts[:-1]) or parts[-1] == ".DS_Store" or path.endswith(".xcuserstate")
                or any(fnmatch.fnmatch(path, g) for g in a.ignore))

    # --map-file accepts a simple path map {path: path|null} or the AI-built file map (schema "file-map/1")
    overrides, symbol_map, placements, fmap_meta = {}, {}, {}, {}
    if a.map_file:
        raw_map = json.load(open(os.path.expanduser(a.map_file)))
        if isinstance(raw_map, dict) and "files" in raw_map:
            for k, v in (raw_map.get("folders") or {}).items():
                overrides[k if k.endswith("/") else k + "/"] = (v if v is None or v.endswith("/") else v + "/")
            for src_f, e in (raw_map.get("files") or {}).items():
                stt = e.get("status")
                fmap_meta[src_f] = e
                if stt == "mapped" and e.get("target"):
                    overrides[src_f] = e["target"]
                elif stt == "not-in-target":
                    overrides[src_f] = None
                elif stt == "split":
                    syms_ = {q: (x.get("target") if isinstance(x, dict) else x) for q, x in (e.get("symbols") or {}).items()}
                    symbol_map[src_f] = syms_
                    prim = e.get("target") or (max(set(syms_.values()), key=list(syms_.values()).count) if syms_ else None)
                    if prim:
                        overrides[src_f] = prim
                elif stt == "new" and e.get("placement"):
                    placements[src_f] = e["placement"]
        else:
            overrides = raw_map

    # folder moves: files that kept their (non-generic, unique) name but live in another folder in target.
    # Only folders that matter (those holding source changes, and their parents) are examined; a name-only pair
    # counts as evidence only if the content is still at least 50% similar.
    rel_dirs = set()
    for (_, _, o_, n_) in src_changes:
        for d_ in (os.path.dirname(o_), os.path.dirname(n_)):
            while True:
                rel_dirs.add(d_)
                if not d_:
                    break
                d_ = os.path.dirname(d_)
    pair_set = {(old, new) for (st, _, old, new) in tgt_changes if st == "R"}
    for p in base_tree:
        n = os.path.basename(p)
        if os.path.dirname(p) not in rel_dirs or p in tgt_tree_set or BUNDLE_RE.match(p) or is_noise(p) or is_generic(n):
            continue
        if len(base_by_name[n]) == 1 and len(by_base.get(n, [])) == 1 and (p, by_base[n][0]) not in pair_set:
            if similarity(show(repo, base, p), show(repo, tgt_ref, by_base[n][0])) >= 0.5:
                pair_set.add((p, by_base[n][0]))
    dir_votes = defaultdict(lambda: defaultdict(int))
    for old, new in pair_set:
        if os.path.basename(old) == os.path.basename(new) and not BUNDLE_RE.match(old):
            do, dn = os.path.dirname(old), os.path.dirname(new)
            if do != dn:
                dir_votes[do][dn] += 1
    dir_map = {}
    for do, c in dir_votes.items():
        dn, v = max(c.items(), key=lambda kv: kv[1])
        if do == "" and v < 3:
            continue
        dir_map[do] = {"source_dir": do, "target_dir": dn, "votes": v, "agreement": round(v / sum(c.values()), 2), "used_by": 0}
    for k, v in overrides.items():
        if k.endswith("/"):
            dir_map[k.rstrip("/")] = {"source_dir": k.rstrip("/"), "target_dir": (v or "").rstrip("/"), "votes": 0,
                                      "agreement": 1.0, "used_by": 0, "confirmed": True, "absent": v is None}

    def map_dir(d):
        cur = d
        while True:
            if cur in dir_map:
                rest = d[len(cur):].lstrip("/")
                tgt = dir_map[cur]["target_dir"]
                return "/".join(x for x in (tgt, rest) if x), dir_map[cur]
            if not cur:
                return None, None
            cur = os.path.dirname(cur)

    def map_path(src_path, base_path, ref_content):
        """Where does this file live in the target branch? Never guess from a shared file name alone."""
        for key in (src_path, base_path):
            if key in overrides:
                t = overrides[key]
                return (t or None), {"method": "confirmed" if t else "confirmed-not-in-target",
                                     "confidence": 1.0, "candidates": []}
        if src_path in tgt_tree_set:
            return src_path, {"method": "same-path", "confidence": 1.0, "candidates": []}
        if base_path in tgt_tree_set:
            return base_path, {"method": "same-path(base)", "confidence": 1.0, "candidates": []}
        if base_path in tgt_rename:
            new, score = tgt_rename[base_path]
            return new, {"method": "git-rename-in-target", "confidence": max(0.86, round(score / 100, 2)), "candidates": []}
        name = os.path.basename(src_path)
        d, info = map_dir(os.path.dirname(base_path or src_path))
        if d is not None and info is not None:
            if info.get("absent"):
                return None, {"method": "confirmed-folder-not-in-target", "confidence": 1.0, "candidates": []}
            cand = "/".join(x for x in (d, name) if x)
            if cand in tgt_tree_set:
                v_eff = info["votes"] - (1 if (base_path, cand) in pair_set else 0)   # a file is no evidence for itself
                unique = len(base_by_name.get(name, [])) <= 1 and len(by_base.get(name, [])) == 1 and not is_generic(name)
                conf = None
                if info.get("confirmed"):
                    conf = 1.0
                elif v_eff >= 2:
                    conf = round(min(0.97, 0.85 + 0.03 * v_eff) * info["agreement"], 2)
                elif v_eff == 1 and unique:
                    conf = round(0.9 * info["agreement"], 2)
                if conf is not None:
                    info["used_by"] += 1
                    return cand, {"method": "folder-moved", "confidence": conf, "candidates": [],
                                  "note": f"folder '{info['source_dir'] or '/'}' → '{info['target_dir'] or '/'}' "
                                          f"({v_eff} other file(s) moved the same way)"}
        cands = [c for c in by_base.get(name, []) if not is_noise(c)]
        if cands:
            sdirs = [x for x in os.path.dirname(base_path or src_path).split("/") if x]
            scored = []
            for c in cands[:40]:
                cdirs = [x for x in os.path.dirname(c).split("/") if x]
                suf = 0
                while suf < min(len(sdirs), len(cdirs)) and sdirs[-1 - suf] == cdirs[-1 - suf]:
                    suf += 1
                scored.append((suf, similarity(ref_content, show(repo, tgt_ref, c)), c))
            generic = is_generic(name)
            if generic:
                scored = [x for x in scored if x[0] >= 1]      # same parent folder required
            if scored:
                scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
                suf, sim, best = scored[0]
                if len(cands) == 1 and not generic:
                    conf = 0.5 + 0.5 * sim
                else:
                    conf = 0.2 + 0.35 * sim + 0.35 * min(1.0, suf / 2)
                return best, {"method": "same-filename" + ("+folder" if suf else ""), "confidence": round(conf, 2),
                              "candidates": [{"path": c, "similarity": round(si, 2), "matching_folders": su} for su, si, c in scored[:5]]}
        if isinstance(ref_content, str):
            names = DECL_RE.findall(ref_content) + OBJC_DECL_RE.findall(ref_content)
            names = [n for n in dict.fromkeys(names) if len(n) >= 3][:6]
            hits = defaultdict(int)
            for n in names:
                ok2, outp = git_try(repo, "grep", "-l", "-E",
                                    rf"(class|struct|enum|protocol|actor|extension|@interface|@implementation)\s+{n}\b",
                                    tgt_ref, "--")
                for h in outp.splitlines():
                    hits[h.split(":", 1)[1] if ":" in h else h] += 1
            if hits:
                ranked = sorted(hits.items(), key=lambda kv: -kv[1])
                best = ranked[0][0]
                conf = round(min(0.75, 0.35 + 0.1 * ranked[0][1]), 2)
                return best, {"method": "declared-type-search", "confidence": conf,
                              "candidates": [{"path": p, "matches": c} for p, c in ranked[:5]]}
        return None, {"method": "not-found", "confidence": 0.0, "candidates": []}

    def suggest_new_path(src_path):
        d = os.path.dirname(src_path)
        if d in tgt_dirs or d == "":
            return src_path, "same folder exists in target"
        md, info = map_dir(d)
        if md is not None and info is not None and not info.get("absent"):
            info["used_by"] += 1
            return "/".join(x for x in (md, os.path.basename(src_path)) if x), \
                   f"folder '{info['source_dir']}' moved to '{info['target_dir']}' in target"
        # where did this file's siblings end up in target?
        votes = defaultdict(int)
        ok3, sib = git_try(repo, "ls-tree", "--name-only", f"{src_ref}:{d}")
        for s in (sib.splitlines() if ok3 else []):
            if s == os.path.basename(src_path) or is_generic(s) or len(by_base.get(s, [])) != 1:
                continue                      # shared names say nothing about where a folder went
            for c in by_base.get(s, []):
                votes[os.path.dirname(c)] += 1
        if votes and max(votes.values()) >= 2:
            best = max(votes.items(), key=lambda kv: kv[1])[0]
            return os.path.join(best, os.path.basename(src_path)), f"{votes[best]} sibling file(s) of this folder live in '{best}' in target"
        if os.path.dirname(d) in tgt_dirs or os.path.dirname(d) == "":
            return src_path, "new folder introduced by source; its parent folder exists in target"
        # walk up until a parent folder exists in target
        parts = d.split("/")
        while parts and "/".join(parts) not in tgt_dirs:
            parts.pop()
        return src_path, ("STRUCTURE MISSING in target; nearest existing parent: '" + "/".join(parts) + "'") if parts else "STRUCTURE MISSING in target"

    items, file_index, counter = [], [], [0]

    def new_item(**kw):
        counter[0] += 1
        base_item = {"id": f"M-{counter[0]:04d}", "needs_decision": False, "severity": "low", "signals": [],
                     "ai_category": "", "ai_analysis": "", "ai_recommendation": "", "recommended_option": "",
                     "proposed_code": "", "proposed_language": "", "decision": None, "decision_notes": "",
                     "final_path": None}
        base_item.update(kw)
        items.append(base_item)
        return base_item

    rng_src = f"{base}..{src_ref}"
    ignored, bundles = [], defaultdict(list)
    _idx_cache = {}

    def sym_index(ref, path, text=None):
        key_ = (ref, path)
        if key_ not in _idx_cache:
            t_ = text if text is not None else show(repo, ref, path)
            _idx_cache[key_] = (t_ if isinstance(t_, str) else "", SYM.index(t_ if isinstance(t_, str) else "", SYM.lang_of(path)))
        return _idx_cache[key_]

    def search_symbol(ref_sym, lang, exclude=None):
        """Find a function/type in the whole target branch by its name, then confirm by signature."""
        if not ref_sym or len(ref_sym.name) < 3:
            return []
        name = re.escape(ref_sym.name)
        pat = {"objc": rf"[-+]\s*\([^)]*\)\s*{name}\b|@(interface|implementation)\s+{name}\b"}.get(
            lang, rf"\b(func|fun|function|def|var|let|val|case|class|struct|enum|protocol|actor|interface|object|extension|type)\s+{name}\b")
        ext = {"swift": "*.swift", "objc": "*.m", "kotlin": "*.kt", "java": "*.java", "js": "*.[jt]s*", "csharp": "*.cs", "go": "*.go"}.get(lang, "*")
        ok_, outp = git_try(repo, "grep", "-l", "-E", pat, tgt_ref, "--", ext)
        found = []
        for h_ in outp.splitlines()[:30]:
            f_ = h_.split(":", 1)[1] if ":" in h_ else h_
            if f_ == exclude or is_noise(f_):
                continue
            t_, idx_ = sym_index(tgt_ref, f_)
            m_ = SYM.find(idx_, ref_sym)
            if m_:
                found.append((f_, m_))
        return found

    def symbol_compare(src_path, base_path, tpath, base_content, src_content, tgt_content, s_hunks, mapping, k, prot,
                       file_rec, authors_file, lang):
        """Compare changes function-by-function: base fn vs source fn vs the same fn wherever it lives in target."""
        bl_, sl_ = base_content.splitlines(), src_content.splitlines()
        _, b_idx = sym_index(base, base_path, base_content)
        _, s_idx = sym_index(src_ref, src_path, src_content)
        groups = {}
        def grp(ref, fallback_line):
            key_ = ref.qual if ref else f"(top level of file, near L{fallback_line + 1})"
            if ref is None:   # merge consecutive top-level lines into one group
                key_ = next((k_ for k_ in groups if k_.startswith("(top level") and groups[k_]["ref"] is None), key_)
            return groups.setdefault(key_, {"ref": ref, "s": [], "b": []})
        for h in s_hunks:     # assign every changed (non-blank) line to its own innermost function
            for ln in range(h["ts"], h["te"]):
                if sl_[ln].strip():
                    grp(SYM.enclosing(s_idx, ln), ln)["s"].append(ln)
            for ln in range(h["bs"], h["be"]):
                if bl_[ln].strip():
                    grp(SYM.enclosing(b_idx, ln), ln)["b"].append(ln)
        # a type-level group only keeps lines that are not inside one of its functions
        smap = symbol_map.get(src_path, {})

        def runs(nums):
            nums = sorted(set(nums)); out_ = []
            for n_ in nums:
                if out_ and n_ == out_[-1][1]:
                    out_[-1][1] = n_ + 1
                else:
                    out_.append([n_, n_ + 1])
            return out_
        for key_, g in groups.items():
            ref = g["ref"]
            added_n = nontrivial([sl_[i] for i in sorted(g["s"])])
            removed_n = nontrivial([bl_[i] for i in sorted(g["b"])])
            if not added_n and not removed_n and all(norm(sl_[i]) in ("}", "{", "})") for i in g["s"]) and \
               all(norm(bl_[i]) in ("}", "{", "})") for i in g["b"]):
                continue   # only braces moved around — nothing to merge
            s_marks, b_marks = sorted(g["s"]), sorted(g["b"])
            sa = []
            for r0, r1 in runs(g["s"]):
                sa += blame(repo, src_ref, src_path, r0, r1, src_set, role="wrote incoming lines")
            sd = deleters(repo, rng_src, [base_path, src_path], [(i + 1, bl_[i]) for i in sorted(g["b"])],
                          role="removed base lines") if g["b"] else []
            src_auth = combine(sa, sd, "incoming")
            common = dict(file=src_path, base_path=base_path, mapping=mapping, kind=k, compare="symbol",
                          source_symbol=key_, added_norm=added_n, removed_norm=removed_n, source_authors=src_auth)
            if ref is None:
                tl_ = (tgt_content or "").splitlines()
                tset = {norm(x) for x in tl_}
                present = bool(added_n) and all(x in tset for x in added_n)
                f0 = (s_marks or [0])[0]
                it = new_item(**common, target_path=tpath, category="ALREADY_PRESENT" if present else "RESTRUCTURED",
                              title="Top-level change (imports / globals) " + ("already in target" if present else f"— port into {tpath}"),
                              needs_decision=False, severity="info" if present else "low",
                              source=snippet(sl_, f0, (s_marks or [0])[-1] + 1, a.context, s_marks), target_authors=[], signals=[])
                file_rec["items"].append(it["id"]); continue
            sym_b = SYM.find(b_idx, ref)
            sym_s = SYM.find(s_idx, ref)
            tfile = smap.get(ref.qual) or smap.get(ref.key) or tpath
            t_text, t_idx = sym_index(tgt_ref, tfile) if tfile else ("", [])
            sym_t = SYM.find(t_idx, ref) if t_idx else None
            how = "same function in the mapped file"
            if sym_t is None:
                found = search_symbol(ref, lang)
                if len(found) == 1:
                    tfile, sym_t = found[0]
                    t_text, t_idx = sym_index(tgt_ref, tfile)
                    how = "found by name+signature elsewhere in target"
                elif len(found) > 1:
                    how = "several target files define it: " + ", ".join(f for f, _ in found[:5])
            def body_n(text, sym):
                return [norm(x) for x in SYM.body(text, sym) if norm(x)] if sym else []
            bb, sb, tb = body_n(base_content, sym_b), body_n(src_content, sym_s), body_n(t_text, sym_t)
            signals = [f"compared {ref.kind} {ref.qual} — {how}"]
            t_snip, ta = None, []
            if sym_t is not None:
                tl_ = t_text.splitlines()
                bset = set(bb)
                t_marks = [i for i in range(sym_t.start, sym_t.end + 1) if norm(tl_[i]) and norm(tl_[i]) not in bset]
                t_snip = snippet(tl_, sym_t.start, sym_t.end + 1, 1, t_marks) if sym_t.end - sym_t.start < 70 else \
                         snippet(tl_, (t_marks or [sym_t.start])[0], (t_marks or [sym_t.start])[-1] + 1, a.context, t_marks)
                ta = combine(blame(repo, tgt_ref, tfile, sym_t.start, sym_t.end + 1, tgt_set,
                                   None if tgt_set is not None else since_ts, role="wrote current lines"), [], "current")
            def sym_snip(lines_, sym, marks):
                if not sym:
                    return None
                if sym.end - sym.start < 70:
                    return snippet(lines_, sym.start, sym.end + 1, 1, marks)
                return snippet(lines_, (marks or [sym.start])[0], (marks or [sym.start])[-1] + 1, a.context, marks)
            b_snip, s_snip = sym_snip(bl_, sym_b, b_marks), sym_snip(sl_, sym_s, s_marks)
            if sym_t is None:
                if sym_b is None:
                    cat, need, sev = "NEW_SYMBOL", bool(not tfile), "medium"
                    title = f"New {ref.kind} {ref.qual} in source — add it to {tfile or '(choose a file)'}"
                    if ref.container:
                        cont = [x for x in t_idx if x.kind == "type" and x.name == ref.container.split('.')[-1]]
                        if cont:
                            signals.append(f"target declares {ref.container} at {tfile}:{cont[0].start + 1} — add it there or in an extension next to it")
                else:
                    cat, need, sev = "SYMBOL_NOT_FOUND", True, "high"
                    title = f"Source changed {ref.kind} {ref.qual}, but target has no such {ref.kind} (removed, renamed or rewritten)"
                    signals.append("find where this behaviour lives now (calls, strings, notification names) and port it there — or confirm it is obsolete")
            elif sym_s is None:
                cat, need, sev = ("CLEAN", False, "low") if tb == bb else ("DELETED_IN_SOURCE", True, "high")
                title = f"Source removed {ref.kind} {ref.qual}" + ("" if tb == bb else " — target changed it meanwhile")
            elif tb == sb or (added_n and all(x in set(tb) for x in added_n) and not any(x in set(tb) for x in removed_n if x not in added_n)):
                cat, need, sev, title = "ALREADY_PRESENT", False, "info", f"{ref.qual}: target already has this change"
            elif tb == bb:
                cat, need, sev = "RESTRUCTURED", False, "low"
                title = f"{ref.qual}: target still has the old version — port the source change into {tfile}"
            else:
                cat, need, sev = "CONFLICT", True, "high"
                title = f"Both branches changed {ref.kind} {ref.qual}"
                if len(tb) > 1.5 * max(1, len(sb)) or len(tb) < 0.6 * max(1, len(sb)):
                    signals.append("target's version is much " + ("longer" if len(tb) > len(sb) else "shorter") +
                                   " than source's — probably refactored/optimised in target; port the source behaviour into it")
            if prot:
                need, sev = True, "high"; signals.append("protected file")
            it = new_item(**common, target_path=tfile, target_symbol=sym_t.qual if sym_t else None, category=cat, title=title,
                          needs_decision=need, severity=sev, signals=signals,
                          base=gutter(b_snip, src_auth, "base_line_numbers") if b_snip else None,
                          source=gutter(s_snip, src_auth) if s_snip else None,
                          target=gutter(t_snip, ta) if t_snip else None, target_authors=ta)
            file_rec["items"].append(it["id"])

    for st, score, old, new in src_changes:
        src_path, base_path = new, old
        if is_noise(src_path):
            ignored.append({"status": st, "path": src_path})
            continue
        bm = BUNDLE_RE.match(src_path) or BUNDLE_RE.match(base_path)
        if bm:
            bundles[bm.group(1) + bm.group(2)].append((st, src_path, base_path, bm.group(3)))
            continue
        k = kind_of(src_path)
        prot = protected(src_path, globs)
        src_content = show(repo, src_ref, src_path) if st != "D" else None
        base_content = show(repo, base, base_path) if st != "A" else None
        ref_content = base_content if base_content is not None else src_content
        tpath, mapping = map_path(src_path, base_path, ref_content)
        if st == "A" and tpath and mapping["confidence"] < 0.85:
            # new in source, only a weak name match in target: treat as a new file, never compare with that file
            mapping = dict(mapping, method="weak-match-ignored", note=f"weak match {tpath} ({mapping['confidence']}) not used")
            tpath = None
        tgt_content = show(repo, tgt_ref, tpath) if tpath else None
        if mode == "shared-history" and base_path in tgt_deleted and tpath in (None, base_path):
            mapping["note"] = "deleted in target since merge-base"
        file_rec = {"source_path": src_path, "base_path": base_path, "source_status": st, "rename_score": score,
                    "target_path": tpath, "mapping": mapping, "kind": k, "protected": prot, "items": []}
        file_index.append(file_rec)
        authors_file = [dict(x, role="changed this file") for x in file_commits(repo, rng_src, src_path, 5, "")]

        def add(**kw):
            kw.setdefault("target_path", tpath)
            it = new_item(file=src_path, base_path=base_path, mapping=mapping, kind=k, **kw)
            if prot and it["category"] not in ("ALREADY_PRESENT",):
                it["needs_decision"] = True; it["severity"] = "high"; it["signals"].append("protected file")
            file_rec["items"].append(it["id"])
            return it

        # ---- uncertain mapping: do NOT compare with a file that may be unrelated
        if tpath and mapping["confidence"] < 0.85 and st != "A":
            bl_ = (base_content or "").splitlines() if isinstance(base_content, str) else []
            sl_ = (src_content or "").splitlines() if isinstance(src_content, str) else []
            hs_ = hunks_between(repo, f"{base}:{base_path}", f"{src_ref}:{src_path}") if st != "D" and bl_ else []
            added_u = [x for h in hs_ for x in nontrivial(sl_[h["ts"]:h["te"]])]
            removed_u = [x for h in hs_ for x in nontrivial(bl_[h["bs"]:h["be"]])]
            first = hs_[0] if hs_ else {"bs": 0, "be": 0, "ts": 0, "te": min(30, len(sl_))}
            add(category="MAPPING_UNCERTAIN",
                title=f"Can't tell which target file this is ({mapping['method']}, confidence {mapping['confidence']}) — confirm before comparing",
                needs_decision=True, severity="high", target_path=None,
                signals=[f"best guess: {tpath} — NOT compared; {len(hs_)} source change(s) in this file wait for the confirmed path",
                         "confirm the real target file (or 'not in target') → it goes into path-map.json and the analysis is re-run"],
                guessed_target_path=tpath,
                base=snippet(bl_, first["bs"], first["be"], a.context, range(first["bs"], first["be"])) if bl_ else None,
                source=snippet(sl_, first["ts"], first["te"], a.context, range(first["ts"], first["te"])) if sl_ else None,
                source_authors=authors_file, target_authors=[], added_norm=added_u, removed_norm=removed_u,
                hunk_count=len(hs_))
            continue

        # ---- binary / large / special kinds
        if src_content is BINARY or base_content is BINARY or tgt_content is BINARY:
            add(category="BINARY", title=f"Binary file {('added' if st == 'A' else 'deleted' if st == 'D' else 'changed')} in source",
                needs_decision=tgt_content is not None and st != "A" and show(repo, base, base_path) != tgt_content,
                severity="medium", source_authors=authors_file, target_authors=[],
                signals=["binary — git cannot merge it; pick one side"])
            continue
        if k == "pbxproj":
            b, s, t = pbx_summary(base_content), pbx_summary(src_content), pbx_summary(tgt_content)
            lines = []
            for f in sorted(s["files"] - b["files"]):
                lines.append(f"+ file reference added in source: {f}" + ("   (already in target)" if f in t["files"] else ""))
            for f in sorted(b["files"] - s["files"]):
                lines.append(f"- file reference removed in source: {f}" + ("   (target still has it)" if f in t["files"] else ""))
            for n in sorted(set(s["packages"]) | set(b["packages"])):
                sv, bv, tv = s["packages"].get(n), b["packages"].get(n), t["packages"].get(n)
                if sv != bv:
                    lines.append(f"~ package {n}: base={bv}  source={sv}  target={tv}")
            for bfk in sorted(set(s["buildfiles"]) | set(b["buildfiles"])):
                d = s["buildfiles"].get(bfk, 0) - b["buildfiles"].get(bfk, 0)
                if d:
                    lines.append(f"{'+' if d > 0 else '-'} target membership {bfk}: {d:+d} build file entr(y/ies)")
            for tn in sorted(s["targets"] - b["targets"]):
                lines.append(f"+ NEW TARGET in source: {tn}")
            add(category="PROJECT_FILE", title="Xcode project file changed in source — re-apply membership, never pick a whole side",
                needs_decision=any(l.startswith("~ package") or "NEW TARGET" in l or l.startswith("-") for l in lines),
                severity="high" if lines else "low", summary_lines=lines or ["(only ordering / metadata changes)"],
                source_authors=authors_file, target_authors=[],
                signals=["resolve by starting from TARGET's project file and re-adding source's file refs/memberships"])
            continue
        if k == "package-resolved":
            b, s, t = (resolved_pins(x) if isinstance(x, str) else {} for x in (base_content, src_content, tgt_content))
            lines = []
            for n in sorted(set(b) | set(s) | set(t)):
                if s.get(n) != b.get(n) or s.get(n) != t.get(n):
                    lines.append(f"{n}: base={b.get(n)} | source={s.get(n)} | target={t.get(n)}")
            add(category="PROTECTED", title="Swift package pins differ (Package.resolved)", needs_decision=True, severity="high",
                summary_lines=lines, source_authors=authors_file, target_authors=[],
                signals=["branch-specific package pins must normally stay as in TARGET"])
            continue
        if max(len(src_content or ""), len(base_content or ""), len(tgt_content or "")) > LARGE_FILE:
            add(category="LARGE_FILE", title="Very large text file — review with a diff tool", needs_decision=True,
                severity="medium", source_authors=authors_file, target_authors=[])
            continue

        # ---- whole-file situations
        if st == "A" and tpath and mapping["confidence"] < 0.85:
            mapping["note"] = f"a file with the same name exists at {tpath} — not compared (confidence {mapping['confidence']})"
            tpath, tgt_content = None, None
        if st == "A":
            if tpath and tgt_content == src_content:
                add(category="ALREADY_PRESENT", title="New file already exists in target with identical content",
                    severity="info", source_authors=authors_file, target_authors=[])
                continue
            if tpath:
                hs = hunks_between(repo, f"{tgt_ref}:{tpath}", f"{src_ref}:{src_path}")
                add(category="CONFLICT" if hs else "ALREADY_PRESENT",
                    title="File added on BOTH branches with different content" if hs else "Same file added on both branches",
                    needs_decision=bool(hs), severity="high" if hs else "info",
                    source=snippet(src_content.splitlines(), 0, min(60, len(src_content.splitlines())), 0, []),
                    target=snippet(tgt_content.splitlines(), 0, min(60, len(tgt_content.splitlines())), 0, []),
                    source_authors=authors_file, target_authors=[])
                continue
            sugg, why = suggest_new_path(src_path)
            plc = placements.get(src_path)
            if plc and plc.get("path"):
                sugg, why = plc["path"], "file map: " + (plc.get("why") or "placement decided in file-map.json")
            sl = src_content.splitlines()
            authors_file = blame(repo, src_ref, src_path, 0, len(sl), src_set, role="wrote lines of the new file") or authors_file
            add(category="NEW_FILE", title="New file in source — must be added to target (folder + Xcode targets)",
                xcode_targets=(plc or {}).get("xcode_targets"), spm_target=(plc or {}).get("spm_target"),
                needs_decision=("MISSING" in why or (sugg != src_path and "moved to" not in why and not why.startswith("file map")))
                               or bool((fmap_meta.get(src_path) or {}).get("needs_developer")),
                severity="medium" if sugg != src_path or "MISSING" in why else "low",
                suggested_target_path=sugg, suggestion_reason=why, line_count=len(sl),
                source=snippet(sl, 0, min(40, len(sl)), 0, list(range(min(40, len(sl))))),
                source_authors=authors_file, target_authors=[])
            continue
        if st == "D":
            if tpath is None or tgt_content is None:
                add(category="ALREADY_PRESENT", title="File deleted in source and already absent in target", severity="info",
                    source_authors=authors_file, target_authors=[])
                continue
            changed_in_tgt = show(repo, base, base_path) != tgt_content
            killer = git(repo, "log", "--diff-filter=D", "--format=%H", "-1", rng_src, "--", base_path, check=False).split()
            if killer:
                authors_file = [dict(commit_meta(repo, killer[0]), role="deleted the file", lines=None, line_numbers=[])]
            bl = (base_content or "").splitlines()
            add(category="DELETED_IN_SOURCE",
                title="Source DELETED this file" + (" but target changed it since" if changed_in_tgt else ""),
                needs_decision=True, severity="high" if changed_in_tgt else "medium",
                base=snippet(bl, 0, min(30, len(bl)), 0, []),
                target=snippet(tgt_content.splitlines(), 0, min(30, len(tgt_content.splitlines())), 0, []),
                source_authors=authors_file, target_authors=[],
                signals=["check that nothing in target still references the deleted types/functions"])
            continue

        # ---- modified / renamed in source: hunk level
        bl, sl = base_content.splitlines(), src_content.splitlines()
        s_hunks = hunks_between(repo, f"{base}:{base_path}", f"{src_ref}:{src_path}")
        if st == "R" and not s_hunks:
            add(category="RESTRUCTURED", title=f"Source only moved/renamed the file ({base_path} → {src_path})",
                needs_decision=False, severity="low", source_authors=authors_file, target_authors=[],
                signals=["keep target's location unless the team wants the new structure"])
            continue
        if tgt_content is None:
            remover = []
            if mode == "shared-history":
                k = git(repo, "log", "--diff-filter=D", "-M50%", "--format=%H", "-1", f"{base}..{tgt_ref}", "--", base_path, check=False).split()
                remover = [dict(commit_meta(repo, k[0]), role="deleted/moved this file in target", lines=None,
                                line_numbers=[], base_line_numbers=[])] if k else \
                          [dict(x, role="changed this file in target") for x in file_commits(repo, f"{base}..{tgt_ref}", base_path, 3, "")]
            for h in s_hunks:
                add(category="DELETED_IN_TARGET", title="Source changed code in a file that no longer exists in target",
                    needs_decision=True, severity="high",
                    base=snippet(bl, h["bs"], h["be"], a.context, range(h["bs"], h["be"])),
                    source=snippet(sl, h["ts"], h["te"], a.context, range(h["ts"], h["te"])),
                    source_authors=combine(blame(repo, src_ref, src_path, h["ts"], h["te"], src_set),
                                           deleters(repo, rng_src, [base_path, src_path], [(i + 1, bl[i]) for i in range(h["bs"], h["be"])]),
                                           "incoming"),
                    target_authors=remover, added_norm=nontrivial(sl[h["ts"]:h["te"]]), removed_norm=nontrivial(bl[h["bs"]:h["be"]]),
                    signals=["find where this logic lives in target now (declared-type search found nothing)"])
            continue
        tl = tgt_content.splitlines()
        lang = SYM.lang_of(src_path)
        moved_file = mapping["method"] not in ("same-path", "same-path(base)")
        if lang and (src_path in symbol_map or (moved_file and similarity(base_content, tgt_content) < 0.6)):
            symbol_compare(src_path, base_path, tpath, base_content, src_content, tgt_content, s_hunks, mapping, k, prot,
                           file_rec, authors_file, lang)
            continue
        t_hunks = hunks_between(repo, f"{base}:{base_path}", f"{tgt_ref}:{tpath}") if base_content is not None else []
        tgt_norm_set = set(norm(x) for x in tl)
        restructured = mapping["method"] not in ("same-path", "same-path(base)")
        for h in s_hunks:
            added = sl[h["ts"]:h["te"]]
            removed = bl[h["bs"]:h["be"]]
            added_n, removed_n = nontrivial(added), nontrivial(removed)
            # git conflicts when the two changes overlap or touch (no unchanged line between them)
            overl = [t for t in t_hunks if t["bs"] <= h["be"] and h["bs"] <= t["be"]]
            near = [t for t in t_hunks if t not in overl and t["bs"] - a.near < h["be"] and h["bs"] < t["be"] + a.near]
            ub_s = min([h["bs"]] + [t["bs"] for t in overl]); ub_e = max([h["be"]] + [t["be"] for t in overl])
            ts_ = min([to_target(ub_s, t_hunks, "start")] + [t["ts"] for t in overl])
            te_ = max([to_target(ub_e, t_hunks, "end")] + [t["te"] for t in overl])
            tmarks = [i for t in overl for i in range(t["ts"], t["te"])]
            signals = []
            present = sum(1 for x in added_n if x in tgt_norm_set)
            removed_still = sum(1 for x in removed_n if x in tgt_norm_set)
            whitespace_only = norm("\n".join(added)).replace(" ", "") == norm("\n".join(removed)).replace(" ", "")
            if whitespace_only:
                cat, need, sev, title = "COSMETIC", False, "info", "Whitespace / formatting-only change"
            elif added_n and present == len(added_n) and (not removed_n or removed_still == 0):
                cat, need, sev, title = "ALREADY_PRESENT", False, "info", "Change already present in target"
            elif not added_n and removed_n and removed_still == 0:
                cat, need, sev, title = "ALREADY_PRESENT", False, "info", "Removed code is already absent in target"
            elif overl:
                identical = any(tl[t["ts"]:t["te"]] == added for t in overl)
                if identical:
                    cat, need, sev, title = "ALREADY_PRESENT", False, "info", "Identical change made on both branches"
                else:
                    cat, need, sev, title = "CONFLICT", True, "high", "Both branches changed the same code"
                    if added_n and present:
                        signals.append(f"{present}/{len(added_n)} added source lines already appear in target (partial/duplicate fix?)")
                    tgt_size = sum(t["te"] - t["ts"] + t["be"] - t["bs"] for t in overl)
                    if tgt_size > 2 * max(1, len(added) + len(removed)):
                        signals.append("target rewrote a much larger region here — possibly refactored/optimised in target; port source logic into target's version")
                    elif len(added) + len(removed) > 2 * max(1, tgt_size):
                        signals.append("source rewrote a much larger region — possibly refactored/optimised in source")
            elif restructured:
                cat = "RESTRUCTURED"
                need = mapping["confidence"] < 0.85
                sev = "medium"
                title = f"File lives at a different path in target ({mapping['method']}, confidence {mapping['confidence']})"
            else:
                cat, need, sev, title = "CLEAN", False, "low", "Source-only change (target untouched here)"
            if near and cat in ("CLEAN", "RESTRUCTURED"):
                cat = "NEAR_CHANGE" if cat == "CLEAN" else cat
                signals.append(f"target also changed code {min(abs(t['bs'] - h['bs']) for t in near)} line(s) away — verify both logics still fit together")
                sev = "medium"
            if added_n and 0 < present < len(added_n) and cat in ("CLEAN", "NEAR_CHANGE", "RESTRUCTURED"):
                signals.append(f"{present}/{len(added_n)} added lines already exist elsewhere in target file — duplicate risk")
                sev = "medium"
            # ---- exact, line-level attribution: who wrote / removed THESE lines (never "who touched the file")
            sa = blame(repo, src_ref, src_path, h["ts"], h["te"], src_set, role="wrote incoming lines")
            sd = deleters(repo, rng_src, [base_path, src_path], [(i + 1, bl[i]) for i in range(h["bs"], h["be"])],
                          role="removed base lines") if h["be"] > h["bs"] else []
            src_auth = combine(sa, sd, "incoming")
            if not src_auth:
                signals.append("exact author of these lines not found in the source range (whitespace-only, or changed inside a merge commit)")
            # target side: only the hunks that actually collide (CONFLICT) — near hunks only for NEAR_CHANGE
            relevant = overl if overl else (near if cat in ("NEAR_CHANGE", "RESTRUCTURED") else [])
            ta, td = [], []
            rng_tgt = f"{mb}..{tgt_ref}" if mode == "shared-history" else None
            for t in relevant:
                ta += blame(repo, tgt_ref, tpath, t["ts"], t["te"], tgt_set, None if tgt_set is not None else since_ts,
                            role="wrote current lines")
                if t["be"] > t["bs"] and rng_tgt:
                    td += deleters(repo, rng_tgt, [base_path, tpath], [(i + 1, bl[i]) for i in range(t["bs"], t["be"])],
                                   role="removed base lines in target")
            tgt_auth = combine(ta, td, "current")
            if relevant and not tgt_auth:
                signals.append("exact author of the target lines not found (changed inside a merge commit?)")
            base_snip = gutter(snippet(bl, h["bs"], h["be"], a.context, range(h["bs"], h["be"])), src_auth, "base_line_numbers")
            src_snip = gutter(snippet(sl, h["ts"], h["te"], a.context, range(h["ts"], h["te"])), src_auth)
            tgt_snip = gutter(snippet(tl, ts_, te_ if te_ > ts_ else ts_, a.context, tmarks), tgt_auth) if tpath else None
            add(category=cat, title=title, needs_decision=need, severity=sev, signals=signals,
                base=base_snip, source=src_snip, target=tgt_snip,
                source_authors=src_auth, target_authors=tgt_auth, added_norm=added_n, removed_norm=removed_n)

    # ---- vendored bundles (.xcframework / .framework / .bundle): one item per bundle
    def blob_bytes(ref, path):
        r = subprocess.run(["git", "-C", repo, "show", f"{ref}:{path}"], capture_output=True)
        return r.stdout if r.returncode == 0 else None

    def bundle_version(ref, root):
        ok_, lst = git_try(repo, "ls-tree", "-r", "--name-only", ref, "--", root)
        for pth in (lst.splitlines() if ok_ else []):
            if pth.endswith("Info.plist"):
                b = blob_bytes(ref, pth)
                try:
                    pl = plistlib.loads(b) if b else {}
                except Exception:
                    continue
                v = pl.get("CFBundleShortVersionString") or pl.get("CFBundleVersion")
                if v:
                    return str(v)
        return None

    for root, files in sorted(bundles.items()):
        bname = os.path.basename(root)
        stem = re.sub(r"\.(xcframework|framework|bundle)$", "", bname)
        if root in tgt_dirs:
            troot = root
        else:
            hits = sorted(d for d in tgt_dirs if d.endswith("/" + bname) or d == bname)
            troot = hits[0] if hits else None
        changed_in_tgt = bool(troot) and mode == "shared-history" and any(
            (n.startswith(troot + "/") or o.startswith(root + "/")) for (_, _, o, n) in tgt_changes)
        refs = []
        toks = [t.lower() for t in re.findall(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+", stem) if len(t) > 1]
        grep_args = ["grep", "-il"]
        for n_, t in enumerate(toks or [stem.lower()]):
            grep_args += (["--and"] if n_ else []) + ["-e", t]
        ok_, outp = git_try(repo, *grep_args, tgt_ref, "--", "*Package.resolved", "*Package.swift", "*.pbxproj", "Podfile", "*.podspec")
        refs = sorted({h.split(":", 1)[1] for h in outp.splitlines() if ":" in h})
        vb, vs, vt = bundle_version(base, root), bundle_version(src_ref, root), bundle_version(tgt_ref, troot) if troot else None
        lines = [f"bundle: {root}  →  target: {troot or 'NOT PRESENT in target'}",
                 f"version: base={vb}  source={vs}  target={vt}",
                 f"{len(files)} file(s) changed inside the bundle in source:"]
        lines += [f"  {st} {rel}" for st, _, _, rel in files[:40]] + ([f"  … +{len(files) - 40} more"] if len(files) > 40 else [])
        if refs:
            lines.append("target references it in: " + ", ".join(refs) + " (maybe replaced by a package — check the pin)")
        auth = []
        for sha in git(repo, "log", "--no-merges", "--format=%H", "-5", rng_src, "--", root, check=False).split():
            auth.append(dict(commit_meta(repo, sha), role="changed the bundle", line_numbers=[], base_line_numbers=[], lines=None))
        it = new_item(file=root, base_path=root, target_path=troot,
                      mapping={"method": "bundle" if troot else "bundle-missing", "confidence": 1.0 if troot else 0.0, "candidates": []},
                      kind="bundle", category="VENDORED_BUNDLE",
                      title=("Vendored bundle updated in source, but target no longer has it" if not troot else
                             "Vendored bundle changed on both branches" if changed_in_tgt else "Vendored bundle updated in source"),
                      needs_decision=(not troot) or changed_in_tgt, severity="high" if (not troot or changed_in_tgt) else "low",
                      summary_lines=lines, source_authors=auth, target_authors=[],
                      signals=["handled as one unit — copy the whole bundle or keep target's; never merge files inside it"])
        file_index.append({"source_path": root, "base_path": root, "source_status": "bundle", "rename_score": 100,
                           "target_path": troot, "mapping": it["mapping"], "kind": "bundle", "protected": False, "items": [it["id"]]})

    # ---- files changed only in target (context for developers, never touched by the merge)
    tgt_only = []
    src_paths = {o for (_, _, o, _) in src_changes} | {n for (_, _, _, n) in src_changes}
    for st, _, old, new in tgt_changes:
        if old not in src_paths and new not in src_paths:
            tgt_only.append({"status": st, "path": new, "old_path": old})

    moved = [f for f in file_index if f["target_path"] and f["target_path"] not in (f["source_path"], f["base_path"])]
    uncertain = [i for i in items if i["category"] == "MAPPING_UNCERTAIN"]
    used_dirs = [dict(v) for v in dir_map.values() if v["used_by"] or v.get("confirmed")]
    # git merge follows plain renames itself; only moves git cannot see make a plain merge unsafe
    hard_moves = [f for f in moved if f["mapping"]["method"] not in ("git-rename-in-target", "same-path(base)")]
    restructured = (mode == "unrelated-history" or bool(used_dirs) or len(hard_moves) >= 2 or bool(uncertain)
                    or any(i.get("compare") == "symbol" for i in items)
                    or (len(moved) >= 5 and len(file_index) and len(moved) / len(file_index) >= 0.3))
    structure = {"restructured": restructured, "moved_files": len(moved), "uncertain_files": len(uncertain),
                 "missing_in_target": sum(1 for f in file_index if not f["target_path"] and f["source_status"] != "A"),
                 "folder_map": sorted(used_dirs, key=lambda v: -v["used_by"]),
                 "folder_map_unused": len(dir_map) - len(used_dirs),
                 "strategy": "port-per-file" if restructured else "git-merge",
                 "why": ("no shared history — port each change by hand" if mode == "unrelated-history" else
                         "folder structure differs between the branches — git merge would bring back source paths; "
                         "port each change into the mapped target file instead") if restructured else
                        ("same structure" + (f" ({len(moved)} renamed file(s) — git merge follows them)" if moved else ""))}
    cats = defaultdict(int)
    for it in items:
        cats[it["category"]] += 1
    devs = defaultdict(lambda: {"items": 0, "email": ""})
    for it in items:
        for au in it.get("source_authors", []):
            d = devs[au.get("name", "?")]; d["items"] += 1; d["email"] = au.get("email", "")

    now = datetime.datetime.now()
    rid = a.report_id or f"MRG-{now:%Y%m%d-%H%M}-{re.sub(r'[^A-Za-z0-9]+', '_', a.source_branch)}-into-{re.sub(r'[^A-Za-z0-9]+', '_', a.target_branch)}"
    analysis = {
        "schema": 1, "report_id": rid, "generated_at": now.isoformat(timespec="seconds"), "status": "AWAITING_DECISIONS",
        "generator": {"tool": a.tool, "session_id": a.session_id, "resume_hint": a.resume_hint},
        "source": {"branch": a.source_branch, "folder": src_dir, "repo_root": src_top, "ref": src_ref, "head": src_head},
        "target": {"branch": a.target_branch, "folder": tgt_dir, "repo_root": repo, "ref": tgt_ref, "head": tgt_head},
        "same_checkout": same_checkout, "mode": mode, "merge_base": mb if ok else None, "analysis_base": base,
        "base_note": base_note, "protected_globs": globs,
        "summary": {"items": len(items), "needs_decision": sum(1 for i in items if i["needs_decision"]),
                    "by_category": dict(cats), "source_commits": len(commits),
                    "files_changed_in_source": len(src_changes), "files_changed_only_in_target": len(tgt_only)},
        "developers": dict(devs), "commits": commits, "files": file_index, "target_only_changes": tgt_only, "items": items,
        "ignored_files": ignored, "structure": structure,
    }
    with open(os.path.join(out_dir, "analysis.json"), "w") as f:
        json.dump(analysis, f, indent=1)
    print(f"REPORT_ID {rid}")
    print(f"mode={mode} base={base[:9]} ({base_note}) source={src_head[:9]} target={tgt_head[:9]}")
    print(f"source commits: {len(commits)}  files changed in source: {len(src_changes)}  items: {len(items)}  "
          f"needs decision: {analysis['summary']['needs_decision']}")
    for c, n in sorted(cats.items(), key=lambda kv: -kv[1]):
        print(f"  {c:18s} {n}")
    print(f"structure: {'RESTRUCTURED → port per file (no plain git merge)' if restructured else 'same → git merge'}; "
          f"moved files {len(moved)}, uncertain {len(uncertain)}, folder moves {len(used_dirs)}, ignored noise {len(ignored)}")
    for v in structure["folder_map"][:15]:
        print(f"  {v['source_dir'] or '/'}  →  {v['target_dir'] or '/'}   ({v['votes']} files, used by {v['used_by']})")
    print(f"written: {os.path.join(out_dir, 'analysis.json')}")


if __name__ == "__main__":
    main()
