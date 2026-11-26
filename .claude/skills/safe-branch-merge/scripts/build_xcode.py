#!/usr/bin/env python3
"""
build_xcode.py — resolve Swift packages once, then build every scheme ONE AT A TIME and report
an honest per-scheme result. Never runs builds in parallel (parallel xcodebuild runs into one
DerivedData give false failures: "database is locked", "has been modified since the module file
was built").

Usage (run from anywhere; macOS with Xcode):
  build_xcode.py --repo <target folder> [--workspace X.xcworkspace | --project X.xcodeproj]
                 [--scheme S ...] [--out <report folder>] [--derived-data <path>]
                 [--configuration Debug] [--skip-resolve] [--include-tests] [--timeout 1800]

  * No --scheme: every shared scheme from `xcodebuild -list` (test-only schemes skipped unless --include-tests).
  * --scheme can be repeated; use one scheme per call when your editor limits command run time.
  * DerivedData default: ~/Library/Developer/Xcode/DerivedData/merge-guard-<repo name> — separate from the
    one Xcode.app uses, so an open Xcode cannot lock it.

Steps:
  1. xcodebuild -resolvePackageDependencies (once) → logs Package.resolved changes vs HEAD
  1b. every application / app-extension target must be built by some scheme → otherwise MISSING_SCHEME (fail)
  2. for each scheme (sequential): detect platform → build for generic simulator destination
     (packages: only the revisions in Package.resolved; --allow-package-updates to let Xcode move them)
  3. failure classification:
       ENVIRONMENT  lock / stale module / resolve / destination / disk problems → one automatic retry
                    (clean build of that scheme, still sequential); still failing → ENV_FAIL
       CODE         compiler/linker errors (file:line: error, Undefined symbol, No such module …) → CODE_FAIL
  4. writes <out>/build-summary.md + build-summary.json + build-logs/<scheme>.log
Exit 0 only when every scheme ends BUILD SUCCEEDED.
"""
import argparse, datetime, glob, json, os, re, subprocess, sys, time

ENV_PATTERNS = [
    r"database is locked", r"unable to attach DB", r"has been modified since the module file",
    r"Possibly there are two concurrent builds", r"Could not resolve package dependencies",
    r"Failed to clone repository", r"Unable to find a destination matching", r"No space left on device",
    r"The operation couldn.t be completed\. \(Mach error", r"Build service could not create build operation",
    r"PCH was compiled with module cache path", r"module cache path .* not found",
]
CODE_PATTERNS = [
    r"^\S.*\.(swift|m|mm|h|c|cc|cpp|metal|storyboard|xib):\d+(:\d+)?: error: .*",
    r"^Undefined symbol: .*", r"^ld: .*error.*", r"^error: No such module .*", r".*error: no such module .*",
    r"^error: Missing package product .*", r"^\S+: error: .*",
]


def sh(cmd, cwd, timeout, log=None):
    t0 = time.time()
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        out, rc = p.stdout + p.stderr, p.returncode
    except subprocess.TimeoutExpired as e:
        out, rc = ((e.stdout or b"").decode(errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or "")) + \
                  f"\n** TIMEOUT after {timeout}s **", 124
    if log:
        with open(log, "w") as f:
            f.write(f"$ {' '.join(cmd)}\n\n{out}")
    return rc, out, round(time.time() - t0)


def classify(out):
    code = []
    for line in out.splitlines():
        if any(re.search(p, line) for p in CODE_PATTERNS) and not any(re.search(p, line) for p in ENV_PATTERNS):
            if "warning:" not in line:
                code.append(line.strip())
    env = [l.strip() for l in out.splitlines() if any(re.search(p, l) for p in ENV_PATTERNS)]
    return list(dict.fromkeys(code))[:15], list(dict.fromkeys(env))[:5]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--workspace"); ap.add_argument("--project")
    ap.add_argument("--scheme", action="append", default=[])
    ap.add_argument("--out")
    ap.add_argument("--derived-data")
    ap.add_argument("--configuration", default="Debug")
    ap.add_argument("--skip-resolve", action="store_true")
    ap.add_argument("--include-tests", action="store_true")
    ap.add_argument("--timeout", type=int, default=1800)
    ap.add_argument("--allow-package-updates", action="store_true",
                    help="let Xcode update packages; default builds ONLY the revisions in Package.resolved (branch pins move)")
    ap.add_argument("--require-target", action="append", default=[],
                    help="app/extension targets that must be built (default: every application/app-extension target in the project)")
    a = ap.parse_args()

    repo = os.path.abspath(os.path.expanduser(a.repo))
    out_dir = os.path.abspath(os.path.expanduser(a.out or os.path.join(repo, ".merge-guard-build")))
    logs = os.path.join(out_dir, "build-logs"); os.makedirs(logs, exist_ok=True)
    dd = os.path.expanduser(a.derived_data or f"~/Library/Developer/Xcode/DerivedData/merge-guard-{os.path.basename(repo)}")

    def find(pattern):
        hits = [h for h in sorted(glob.glob(os.path.join(repo, pattern))) if "/Pods/" not in h and not h.endswith("project.xcworkspace")]
        return os.path.relpath(hits[0], repo) if hits else None
    ws = a.workspace or (None if a.project else (find("*.xcworkspace") or find("*/*.xcworkspace")))
    pj = a.project or (None if ws else (find("*.xcodeproj") or find("*/*.xcodeproj")))
    if not ws and not pj:
        sys.exit("No .xcworkspace or .xcodeproj found — pass --workspace/--project")
    container = ["-workspace", ws] if ws else ["-project", pj]
    print(f"container: {ws or pj}\nDerivedData: {dd}\nlogs: {logs}")

    results, started = [], datetime.datetime.now().isoformat(timespec="seconds")
    # build exactly the package revisions recorded in Package.resolved (branch-pinned packages move otherwise)
    pkg_flags = [] if a.allow_package_updates else ["-onlyUsePackageVersionsFromResolvedFile", "-disableAutomaticPackageResolution"]
    # 1. resolve packages once
    resolve = {"status": "SKIPPED"}
    if not a.skip_resolve:
        rc, out, secs = sh(["xcodebuild", "-resolvePackageDependencies", *container, "-derivedDataPath", dd, *pkg_flags],
                           repo, a.timeout, os.path.join(logs, "_resolvePackageDependencies.log"))
        resolve = {"status": "OK" if rc == 0 else "FAILED", "seconds": secs,
                   "errors": [l for l in out.splitlines() if "error" in l.lower()][:10]}
        diff = subprocess.run(["git", "-C", repo, "diff", "--stat", "--", "*Package.resolved"], capture_output=True, text=True).stdout.strip()
        resolve["package_resolved_changes"] = diff or "none"
        print(f"resolve packages: {resolve['status']} ({secs}s); Package.resolved changes: {resolve['package_resolved_changes']}")
        if rc != 0:
            print("\n".join(resolve["errors"]))

    # 2. schemes — and every app / extension target must be covered by one of them
    schemes = a.scheme
    if not schemes:
        rc, out, _ = sh(["xcodebuild", "-list", "-json", *container], repo, 300)
        try:
            j = json.loads(out[out.index("{"):])
            schemes = (j.get("workspace") or j.get("project") or {}).get("schemes", [])
        except Exception:
            sys.exit("Could not list schemes:\n" + out[-2000:])
        if not a.include_tests:
            schemes = [s for s in schemes if not re.search(r"(Tests?|UITests?)$", s)]
    apps = list(a.require_target)
    if not apps:
        for pbx in glob.glob(os.path.join(repo, "**", "*.xcodeproj", "project.pbxproj"), recursive=True):
            if "/Pods/" in pbx or "/.build/" in pbx or "/SourcePackages/" in pbx:
                continue
            t = open(pbx, encoding="utf-8", errors="replace").read()
            for blk in re.findall(r"=\s*\{\s*isa = PBXNativeTarget;(.*?)\n\t*\};", t, re.S):
                nm = re.search(r'\n\s*name = "?([^";]+)"?;', blk)
                pt = re.search(r'productType = "com\.apple\.product-type\.([^"]+)"', blk)
                if nm and pt and pt.group(1).split(".")[0] in ("application", "app-extension", "tv-app-extension"):
                    apps.append(nm.group(1))
    built_targets = set(schemes)
    for s in schemes:
        for f in glob.glob(os.path.join(repo, "**", f"{s}.xcscheme"), recursive=True):
            built_targets |= set(re.findall(r'BlueprintName = "([^"]+)"', open(f, errors="replace").read()))
    uncovered = sorted(set(apps) - built_targets)
    print("schemes (sequential): " + ", ".join(schemes))
    if uncovered:
        print("REQUIRED targets with no scheme in this list: " + ", ".join(uncovered))

    for s in schemes:
        rc, out, _ = sh(["xcodebuild", "-showBuildSettings", "-json", *container, "-scheme", s,
                         "-configuration", a.configuration, "-derivedDataPath", dd], repo, 600)
        plat = "iOS"
        try:
            bs = json.loads(out[out.index("["):])[0]["buildSettings"]
            pn = bs.get("PLATFORM_NAME", "") + " " + bs.get("SUPPORTED_PLATFORMS", "")
            plat = "tvOS" if "appletv" in pn else "watchOS" if "watch" in pn else "visionOS" if "xr" in pn else \
                   "macOS" if pn.strip().startswith("macosx") else "iOS"
        except Exception:
            plat = "tvOS" if re.search(r"tv", s, re.I) else "iOS"
        dest = "generic/platform=macOS" if plat == "macOS" else f"generic/platform={plat} Simulator"
        base_cmd = ["xcodebuild", *container, "-scheme", s, "-configuration", a.configuration, "-destination", dest,
                    "-derivedDataPath", dd, *pkg_flags, "CODE_SIGNING_ALLOWED=NO", "-skipPackagePluginValidation", "-skipMacroValidation"]
        log = os.path.join(logs, f"{s}.log")
        print(f"→ {s} ({plat}) …", flush=True)
        rc, out, secs = sh(base_cmd + ["build"], repo, a.timeout, log)
        attempts = 1
        code, env = classify(out)
        if rc != 0 and env and not code:
            print(f"  environment failure ({env[0][:100]}) → one clean retry", flush=True)
            rc, out, secs2 = sh(base_cmd + ["clean", "build"], repo, a.timeout, log.replace(".log", ".retry.log"))
            secs += secs2; attempts = 2
            code, env = classify(out)
        ok = rc == 0 and "** BUILD SUCCEEDED **" in out
        status = "SUCCEEDED" if ok else ("CODE_FAIL" if code else "ENV_FAIL" if env else "FAILED")
        dup = sorted(set(re.findall(r"Skipping duplicate build file in [^:]+: (.+?) \(in target '([^']+)'", out)))
        results.append({"scheme": s, "platform": plat, "status": status, "seconds": secs, "attempts": attempts,
                        "code_errors": code, "env_errors": env, "duplicate_build_files": [f"{t}: {f}" for f, t in dup],
                        "log": log})
        print(f"  {status} in {secs}s" + (f" — {code[0][:160]}" if code else f" — {env[0][:160]}" if env and not ok else ""), flush=True)

    for t in uncovered:
        results.append({"scheme": f"(target {t})", "platform": "?", "status": "MISSING_SCHEME", "seconds": 0, "attempts": 0,
                        "code_errors": [], "env_errors": [f"app/extension target '{t}' is not built by any scheme here — share its scheme "
                                                         "in Xcode (Manage Schemes → Shared) or pass --scheme / --require-target"],
                        "duplicate_build_files": [], "log": ""})
    allok = all(r["status"] == "SUCCEEDED" for r in results) and resolve.get("status") in ("OK", "SKIPPED")
    summary = {"started": started, "finished": datetime.datetime.now().isoformat(timespec="seconds"), "repo": repo,
               "container": ws or pj, "derived_data": dd, "resolve": resolve, "results": results, "all_succeeded": allok}
    json.dump(summary, open(os.path.join(out_dir, "build-summary.json"), "w"), indent=1)
    md = [f"# Build summary — {'ALL SUCCEEDED' if allok else 'NOT ALL SUCCEEDED'}", "",
          f"Container `{ws or pj}` · DerivedData `{dd}` · sequential builds · {summary['finished']}", "",
          f"Packages: {resolve.get('status')} — Package.resolved changes: {resolve.get('package_resolved_changes', 'n/a')}"
          + ("" if a.allow_package_updates else " · built with the Package.resolved revisions only"), "",
          "| Scheme | Platform | Result | Time | Attempts | First error |", "|---|---|---|---|---|---|"]
    for r in results:
        first = (r["code_errors"] or r["env_errors"] or [""])[0].replace("|", "\\|")[:180] if r["status"] != "SUCCEEDED" else ""
        md.append(f"| {r['scheme']} | {r['platform']} | {r['status']} | {r['seconds']}s | {r['attempts']} | {first} |")
    dups = [d for r in results for d in r["duplicate_build_files"]]
    if dups:
        md += ["", "**Duplicate build files reported by Xcode (check whether the merge added them — compare with the target branch):**"]
        md += [f"- {d}" for d in sorted(set(dups))]
    open(os.path.join(out_dir, "build-summary.md"), "w").write("\n".join(md) + "\n")
    print("\n".join(md))
    print(f"\nwritten: {os.path.join(out_dir, 'build-summary.md')}")
    sys.exit(0 if allok else 1)


if __name__ == "__main__":
    main()
