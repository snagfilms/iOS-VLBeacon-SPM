#!/usr/bin/env python3
"""
risk_scan.py — repository-wide risks a per-hunk review misses. Generic (any stack); read-only on git.
Run after collect_changes.py + classify_items.py, before the AI review. Writes analysis.json:
  repo_risks[]        {level: block|warn|info, code, message, items?}   (shown at the top of report.html)
  item flags          reverted_in_target, secret, generated, tooling — and categories GENERATED / TOOLING / JUNK

Checks
  REVERT_REINTRODUCED  target reverted a change after the merge base; the source branch still carries it, so git
                       would silently bring it back → item needs a person (auto_decide escalates it)
  SECRET               source adds something that looks like a credential (API key, private key, token)
  GENERATED            item is in generated code (GraphQL/Apollo, protobuf, R.swift, SwiftGen, Sourcery, build/generated,
                       .merge-guard.json "generated") → keep target and REGENERATE after the merge, never hand-merge
  TOOLING / JUNK       AI-agent / editor config (.cursor, .claude, .windsurf, AGENTS.md, CLAUDE.md …) and junk
                       (.DS_Store, xcuserdata, *.xcuserstate) → kept apart from product decisions
  CASE                 paths that differ only in letter case (collisions, case-only renames between branches)
  BUILD_SETTINGS       minimum OS / Swift / SDK settings that differ between base, source and target
                       (Xcode pbxproj, Package.swift, Gradle, package.json engines)
  DEPENDENCIES         branch-pinned packages (builds not reproducible), packages source adds/removes, manifests that
                       ship the same library two ways (Package.swift + .podspec) changed on one side only
  APP_SCHEMES          Xcode app / extension targets without a shared scheme → a "build every scheme" gate can skip them
  CORE_DATA            edits to an existing Core Data model version (needs a new version + migration)
  UTF16_STRINGS        UTF-16 .strings files (git shows them as binary → merge by key, not by line)
  MERGE_BASES          more than one merge base (criss-cross) — the analysis base may hide changes
  DUPLICATE_SUBJECTS   commits with the same subject on both sides (squash / cherry-pick of the same fix)

Usage: risk_scan.py <report>/analysis.json
"""
import fnmatch, json, os, re, subprocess, sys, collections

GEN_DEFAULT = ["**/GraphQLGeneratedFiles/**", "**/__generated__/**", "**/*.generated.swift", "**/*.generated.*",
               "**/Generated/**", "**/R.generated.swift", "**/*.pb.swift", "**/*.pb.go", "**/*_pb2.py",
               "**/build/generated/**", "**/*.g.dart", "**/*.freezed.dart"]
TOOLING = re.compile(r"^(\.cursor/|\.claude/|\.windsurf/|\.ai-skills/|\.omc/|\.github/(copilot-instructions\.md|instructions/)|"
                     r"AGENTS\.md$|CLAUDE\.md$|\.cursorrules$|\.merge-guard\.json$)")
JUNK = re.compile(r"(^|/)(\.DS_Store|Thumbs\.db)$|/xcuserdata/|\.xcuserstate$|\.idea/workspace\.xml$")
SECRET = [("AWS access key", r"AKIA[0-9A-Z]{16}"), ("private key", r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
          ("GitHub token", r"gh[pousr]_[A-Za-z0-9]{30,}"), ("Slack token", r"xox[baprs]-[A-Za-z0-9-]{10,}"),
          ("Google API key", r"AIza[0-9A-Za-z_\-]{35}"), ("Stripe key", r"[rs]k_live_[0-9A-Za-z]{20,}"),
          ("JWT", r"eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
          ("hard-coded secret", r"(?i)(api[_-]?key|secret|client[_-]?secret|password|access[_-]?token)\s*[:=]\s*[\"'][A-Za-z0-9_\-/+=]{16,}[\"']")]


def git(repo, *a, binary=False):
    r = subprocess.run(["git", "-C", repo, *a], capture_output=True)
    return r.stdout if binary else r.stdout.decode("utf-8", "replace")


def show(repo, ref, path):
    return git(repo, "show", f"{ref}:{path}") if ref and path else ""


def match_any(path, globs):
    return any(fnmatch.fnmatch(path, g) or fnmatch.fnmatch("/" + path, g) or fnmatch.fnmatch(path, g.lstrip("*/")) for g in globs)


def added(it):
    s = it.get("source") or {}
    return [s["lines"][n] for n in s.get("marked", []) if n < len(s.get("lines", []))]


def norm(l):
    return re.sub(r"\s+", " ", l.strip())


def main():
    path = sys.argv[1]
    d = json.load(open(path))
    repo = d["target"].get("repo_root") or d["target"]["folder"]
    base, sref, tref = d.get("analysis_base") or d.get("merge_base"), d["source"]["ref"], d["target"]["ref"]
    cfg = {}
    try:
        cfg = json.load(open(os.path.join(d["target"]["folder"], ".merge-guard.json")))
    except Exception:
        pass
    risks, items = [], d["items"]
    # idempotent: drop flags from an earlier run before scanning again
    for it in items:
        if it.pop("reverted_in_target", None) is not None or it.pop("secret", None) is not None:
            if "needs_decision_orig" in it:
                it["needs_decision"] = it["needs_decision_orig"]
        it["signals"] = [s for s in it.get("signals") or [] if not s.startswith(("target reverted this on purpose", "looks like a"))]
        it.setdefault("needs_decision_orig", it.get("needs_decision"))
    R = lambda level, code, msg, ids=None: risks.append({"level": level, "code": code, "message": msg, **({"items": ids} if ids else {})})

    # ---------- reverts in target that source would bring back
    rev = git(repo, "log", "--format=%H%x09%s", "--grep=^Revert", "--grep=This reverts commit", f"{base}..{tref}").splitlines()
    for line in rev:
        c, subj = line.split("\t", 1)
        removed = {norm(l[1:]) for l in git(repo, "show", "--format=", "-U0", c).splitlines()
                   if l.startswith("-") and not l.startswith("---") and len(norm(l[1:])) > 25}
        if not removed:
            continue
        hit = []
        for it in items:
            a = [norm(x) for x in added(it) if len(norm(x)) > 25]
            n = sum(1 for x in a if x in removed)
            if n >= 3 or (n and n >= len(a) / 2):      # 1–2 generic lines (boilerplate) are not a re-introduction
                it.setdefault("reverted_in_target", []).append({"commit": c[:10], "subject": subj, "lines": n})
                it["needs_decision"] = True
                it.setdefault("signals", []).append(f"target reverted this on purpose in {c[:10]} ('{subj[:60]}'); source would bring it back")
                hit.append(it["id"])
        if hit:
            R("block", "REVERT_REINTRODUCED", f"Target reverted '{subj[:80]}' ({c[:10]}); source still carries it in {len(hit)} item(s) — a person decides.", hit)

    # ---------- secrets added by source
    sec = []
    for it in items:
        for l in added(it):
            for name, rx in SECRET:
                if re.search(rx, l):
                    it["secret"] = name; it["needs_decision"] = True
                    it.setdefault("signals", []).append(f"looks like a {name} added by source — never merge credentials without the owner's OK")
                    sec.append(it["id"]); break
            if it.get("secret"):
                break
    if sec:
        R("block", "SECRET", f"Source adds what looks like credentials in {len(sec)} item(s).", sec)

    # ---------- generated / tooling / junk
    gen_globs = GEN_DEFAULT + list(cfg.get("generated") or [])
    gen, tool, junk = [], [], []
    for it in items:
        p = it.get("target_path") or it["file"]
        if it.get("decided_by") == "developer":
            continue
        if match_any(p, gen_globs):
            it.update(ai_category="GENERATED", generated=True, needs_decision=False, severity="info", recommended_option="TARGET",
                      ai_confidence=0.95, ai_analysis="Generated code. Merging generated output by hand produces code no generator would write.",
                      ai_recommendation="Keep target's file and run the generator after the merge (see repo risks → GENERATED).",
                      ai_evidence="rule: path matches a generated-code pattern", check_verdict="agree", check_by="rule",
                      check_note="rule-based (risk_scan.py): generated path; regenerate after merge instead of merging")
            gen.append(it["id"])
        elif JUNK.search(p):
            it.update(ai_category="JUNK", needs_decision=False, severity="info", recommended_option="TARGET", ai_confidence=0.99,
                      ai_analysis="Per-user or OS junk file.", ai_recommendation="Keep target; never merge.", ai_evidence="rule: junk path",
                      check_verdict="agree", check_by="rule", check_note="rule-based (risk_scan.py): per-user / OS file, no product code")
            junk.append(it["id"])
        elif TOOLING.search(p):
            it.update(ai_category="TOOLING", tooling=True, severity="low")
            it.setdefault("signals", []).append("AI-agent / editor configuration, not product code — decide separately from code")
            tool.append(it["id"])
    if gen:
        cmds = cfg.get("regenerate") or []
        inputs = [f for f in git(repo, "diff", "--name-only", base, sref).splitlines() if re.search(r"\.(graphql|gql|proto|xcassets|strings|json)$", f) and not match_any(f, gen_globs)]
        R("warn", "GENERATED", f"{len(gen)} item(s) are generated code — kept as target. Regenerate after the merge"
          + (f" with: {'; '.join(cmds)}" if cmds else " (set .merge-guard.json \"regenerate\" to the generator command)")
          + (f". Generator inputs changed by source: {', '.join(inputs[:6])}" if inputs else "."), gen)
    if tool:
        R("info", "TOOLING", f"{len(tool)} item(s) change AI-agent/editor config — review apart from product code.", tool)
    if junk:
        R("info", "JUNK", f"{len(junk)} item(s) are per-user/OS files — kept as target.", junk)

    # ---------- case collisions / case-only renames
    for label, ref in (("target", tref), ("source", sref)):
        seen, coll = {}, []
        for f in git(repo, "ls-tree", "-r", "--name-only", ref).splitlines():
            k = f.lower()
            if k in seen and seen[k] != f:
                coll.append(f"{seen[k]} <> {f}")
            seen[k] = f
        if coll:
            R("warn", "CASE", f"{label} has paths that differ only in letter case (a case-insensitive disk keeps one): " + "; ".join(coll[:4]))
    cr = [it["id"] for it in items if it.get("target_path") and it["target_path"] != it["file"] and it["target_path"].lower() == it["file"].lower()]
    if cr:
        R("warn", "CASE", "case-only rename between branches — git on macOS/Windows can lose one side; port by hand.", cr)

    # ---------- build settings drift
    def settings(ref):
        out = collections.Counter()
        for f in git(repo, "ls-tree", "-r", "--name-only", ref).splitlines():
            if f.endswith("project.pbxproj"):
                for m in re.findall(r"((?:IPHONEOS|TVOS|MACOSX|WATCHOS|XROS)_DEPLOYMENT_TARGET|SWIFT_VERSION) = ([0-9.]+)", show(repo, ref, f)):
                    out[f"{m[0]}={m[1]}"] += 1
            elif os.path.basename(f) == "Package.swift" and f.count("/") <= 1:
                t = show(repo, ref, f)
                m = re.search(r"swift-tools-version:\s*([0-9.]+)", t)
                if m: out[f"swift-tools-version={m.group(1)}"] += 1
                for p in re.findall(r"\.(iOS|tvOS|macOS|watchOS|visionOS)\(([^)]*)\)", t):
                    out[f"{p[0]}={p[1].strip()}"] += 1
            elif re.search(r"(^|/)build\.gradle(\.kts)?$", f):
                for m in re.findall(r"(minSdk|targetSdk|compileSdk)(?:Version)?\s*=?\s*(\d+)", show(repo, ref, f)):
                    out[f"{m[0]}={m[1]}"] += 1
        return out
    sb, ss, st = settings(base), settings(sref), settings(tref)
    keys = lambda c: {k.split("=")[0] for k in c}
    diffs = []
    for k in sorted(keys(sb) | keys(ss) | keys(st)):
        pick = lambda c: ", ".join(f"{x.split('=')[1]}×{n}" for x, n in sorted(c.items()) if x.split("=")[0] == k)
        b, s, t = pick(sb), pick(ss), pick(st)
        if not (b == s == t):
            diffs.append(f"{k}: base [{b}] · source [{s}] · target [{t}]")
    if diffs:
        R("warn", "BUILD_SETTINGS", "Build settings differ — source code may use APIs newer than target's minimum, or the merge may "
          "change a setting silently: " + " | ".join(diffs))

    # ---------- dependencies
    def pins(ref):
        res = {}
        for f in git(repo, "ls-tree", "-r", "--name-only", ref).splitlines():
            if f.endswith("Package.resolved") and "/.build/" not in f:
                try:
                    j = json.loads(show(repo, ref, f))
                    for p in (j.get("pins") or j.get("object", {}).get("pins") or []):
                        res[(p.get("identity") or p.get("package") or "").lower()] = p.get("state", {})
                except Exception:
                    pass
        return res
    pb, ps, pt = pins(base), pins(sref), pins(tref)
    br = sorted(f"{k}@{v.get('branch')}" for k, v in pt.items() if v.get("branch"))
    if br:
        R("warn", "DEPENDENCIES", "Target pins packages to a BRANCH (a rebuild may pull new commits; build with the revisions in "
          "Package.resolved only): " + ", ".join(br))
    add_s, rem_s = sorted(set(ps) - set(pb)), sorted(set(pb) - set(ps))
    if add_s or rem_s:
        R("warn", "DEPENDENCIES", "Source changed the package set — carry it over while keeping target's pins: "
          + (f"added {', '.join(add_s)}" if add_s else "") + (f" removed {', '.join(rem_s)}" if rem_s else ""))
    changed_src = set(git(repo, "diff", "--name-only", base, sref).splitlines())
    has_spm = any(os.path.basename(f) == "Package.swift" for f in changed_src | set(git(repo, "ls-tree", "--name-only", tref).splitlines()))
    podspec = [f for f in git(repo, "ls-tree", "--name-only", tref).splitlines() if f.endswith(".podspec")]
    if has_spm and podspec:
        a, b = "Package.swift" in changed_src, any(f in changed_src for f in podspec)
        if a != b:
            R("warn", "DEPENDENCIES", f"This library ships via SPM and CocoaPods; source changed {'Package.swift' if a else 'the podspec'} only — "
              "check the other manifest (dependencies, platforms, version) stays in step.")

    # ---------- Xcode app/extension targets without a shared scheme
    tree = git(repo, "ls-tree", "-r", "--name-only", tref).splitlines()
    shared = {os.path.basename(f)[:-9] for f in tree if "xcshareddata/xcschemes/" in f and f.endswith(".xcscheme")}
    shared_targets = set()
    for f in tree:
        if "xcshareddata/xcschemes/" in f and f.endswith(".xcscheme"):
            shared_targets |= set(re.findall(r'BlueprintName = "([^"]+)"', show(repo, tref, f)))
    for f in tree:
        if f.endswith("project.pbxproj"):
            t = show(repo, tref, f)
            apps = []
            for blk in re.findall(r"=\s*\{\s*isa = PBXNativeTarget;(.*?)\n\t*\};", t, re.S):
                nm = re.search(r'\n\s*name = "?([^";]+)"?;', blk)
                pt = re.search(r'productType = "com\.apple\.product-type\.([^"]+)"', blk)
                if nm and pt and pt.group(1).split(".")[0] in ("application", "app-extension", "tv-app-extension"):
                    apps.append(nm.group(1))
            missing = sorted({n for n in apps if n not in shared and n not in shared_targets})
            if missing:
                R("block", "APP_SCHEMES", f"{f}: these app/extension targets have no SHARED scheme: {', '.join(missing)}. A 'build every scheme' "
                  "gate on another machine or CI skips them — build_xcode.py now requires them (share the scheme in Xcode, or pass --scheme).")

    # ---------- Core Data, UTF-16 strings
    cd = [it["id"] for it in items if ".xcdatamodeld/" in it["file"] and it["category"] not in ("NEW_FILE",)]
    if cd:
        R("warn", "CORE_DATA", "Source edits an existing Core Data model version — needs a new model version (+ mapping) on target, "
          "never an in-place edit of a shipped version.", cd)
    u16 = []
    for f in sorted(changed_src):
        if f.endswith((".strings", ".stringsdict")):
            raw = git(repo, "show", f"{sref}:{f}", binary=True)[:4]
            if raw.startswith((b"\xff\xfe", b"\xfe\xff")) or b"\x00" in raw:
                u16.append(f)
    if u16:
        R("warn", "UTF16_STRINGS", "UTF-16 .strings changed by source (git treats them as binary) — merge by key: " + ", ".join(u16[:6]))

    # ---------- history shape
    mb = git(repo, "merge-base", "--all", sref, tref).split()
    if len(mb) > 1:
        R("warn", "MERGE_BASES", f"{len(mb)} merge bases (criss-cross). Changes may hide behind the chosen base; consider --since the last verified merge.")
    ssub = collections.Counter(git(repo, "log", "--no-merges", "--format=%s", f"{base}..{sref}").splitlines())
    tsub = set(git(repo, "log", "--no-merges", "--format=%s", f"{base}..{tref}").splitlines())
    dup = sorted(s for s in ssub if s in tsub and len(s) > 12)
    if dup:
        R("info", "DUPLICATE_SUBJECTS", f"{len(dup)} commit subject(s) exist on both sides (squash/cherry-pick of the same fix — expect "
          "ALREADY_PRESENT or near-duplicates): " + "; ".join(dup[:5]))

    d["repo_risks"] = risks
    json.dump(d, open(path, "w"), indent=1)
    order = {"block": 0, "warn": 1, "info": 2}
    for r in sorted(risks, key=lambda r: order[r["level"]]):
        print(f"{r['level'].upper():5} {r['code']}: {r['message'][:300]}" + (f"  [{', '.join(r['items'][:8])}{'…' if len(r['items']) > 8 else ''}]" if r.get("items") else ""))
    if not risks:
        print("no repository-wide risks found")


if __name__ == "__main__":
    main()
