#!/usr/bin/env python3
"""
project_profile.py — work out the project-specific steps for ANY repository.

Order of precedence:
  1. <repo>/.merge-guard.json   (team-owned config; its build/post_merge/discover replace detected ones,
                                 its protect/regenerate/notes are added to detected ones)
  2. built-in profiles detected from files in the repo (AppCMS, Xcode, SwiftPM, Gradle/Android,
     Flutter, Node, Python, Go, Rust, .NET, Maven, CocoaPods ...)
  3. nothing detected → "ask_developer": true (the agent must ask for the build command)

Usage: project_profile.py <target repo folder>       → prints JSON
       project_profile.py <repo> --example-config     → prints a .merge-guard.json template

JSON fields:
  profiles[]            detected profile names
  protect[]             extra protected globs (pass to collect_changes.py --protect)
  post_merge[]          commands to run from repo root after a successful merge (before building)
  build[]               commands that must compile/build cleanly (agent may expand {scheme} etc.)
  discover[]            commands that list what to build (schemes, modules) when build needs it
  regenerate[]          lockfiles/generated files to regenerate instead of merging by hand
  notes[]               things to tell the agent
  ask_developer         true when no build command is known
"""
import glob, json, os, sys

EXAMPLE = {
    "profile": "my-project",
    "mode": "auto",                 # auto (default): AI decides from code, asks only on escalation | review: report, then wait
    "confidence_threshold": 0.8,    # AI decisions below this go to the developer
    "merge_branch": "direct",       # direct | new  (new = merge/<src>-into-<tgt>-<date>)
    "record_as_merge": True,        # restructured ports are recorded as a merge (git merge -s ours --no-commit)
    "protect": ["**/Package.resolved", "Config/*.xcconfig"],
    "post_merge": ["bash setup_environment.sh motv stage"],
    "build": ["xcodebuild -workspace App.xcworkspace -scheme App -destination 'generic/platform=iOS Simulator' build CODE_SIGNING_ALLOWED=NO"],
    "regenerate": ["Podfile.lock: pod install", "cd AppCMS && ./apollo-ios-cli generate --path apollo-codegen-config.json"],
    "generated": ["AppCMS/GraphQLGeneratedFiles/**"],      # generated output: kept as target, regenerated after merge
    "parallel_modules": ["AppCMS/ViewliftOne/"],           # folders where target re-implemented legacy code (look-alikes)
    "required_targets": ["AppCMS", "AppCMS_tvOS"],         # app/extension targets build_xcode.py must build
    "lint": ["swiftlint lint --quiet --config AppCMS/.swiftlint.yml <merged files>"],
    "test": ["xcodebuild test -workspace AppCMS/AppCMS.xcworkspace -scheme AppCMSTvTest -destination 'platform=tvOS Simulator,name=Apple TV'"],
    "notes": ["Package pins for VLPlayerLib must stay on branch Develop_Analytics"],
}


def exists(root, *pats):
    return any(glob.glob(os.path.join(root, p), recursive=True) for p in pats)


def first(root, *pats):
    for p in pats:
        g = sorted(glob.glob(os.path.join(root, p), recursive=True))
        g = [x for x in g if "/Pods/" not in x and "/.build/" not in x and "/node_modules/" not in x]
        if g:
            return os.path.relpath(g[0], root)
    return None


def detect(root):
    prof = {"profiles": [], "protect": [], "post_merge": [], "build": [], "discover": [], "regenerate": [], "notes": [], "lint": [], "test": [],
            "ask_developer": False, "mode": "auto", "confidence_threshold": 0.8, "merge_branch": "direct", "record_as_merge": True}
    add = lambda k, *v: prof[k].extend(x for x in v if x not in prof[k])

    ws = first(root, "*.xcworkspace", "*/*.xcworkspace")
    pj = first(root, "*.xcodeproj", "*/*.xcodeproj")
    if ws and ws.endswith("project.xcworkspace"):
        ws = None

    # --- AppCMS (ViewLift) ---------------------------------------------------------------
    setup = first(root, "setup_environment.sh", "*/setup_environment.sh")
    if setup:
        sdir = os.path.dirname(setup) or "."
        cmd = f"cd '{sdir}' && bash setup_environment.sh" if sdir != "." else "bash setup_environment.sh"
        if exists(root, "AppCMS.xcodeproj", "*/AppCMS.xcodeproj", "AppCMS.xcworkspace", "*/AppCMS.xcworkspace"):
            add("profiles", "appcms")
            add("post_merge", cmd + " motv stage")
            add("notes", "AppCMS: setup_environment.sh takes <client> <env> (default here: motv stage) — confirm with the developer; it rewrites "
                         "project.pbxproj / Pods / SiteConfig.plist, so run it through run_post_merge.py.")
        else:
            add("post_merge", cmd); prof["ask_developer"] = True
            add("notes", f"Environment script {setup} found — ask the developer for its arguments before running it.")
    if setup and exists(root, "AppCMS.xcodeproj", "*/AppCMS.xcodeproj", "AppCMS.xcworkspace", "*/AppCMS.xcworkspace"):
        add("notes",
            "AppCMS: build both AppCMS (iOS) and AppCMS_tvOS plus extensions; respect #if os(iOS) / #if os(tvOS).",
            "AppCMS: branch-specific SPM pins are protected (see reference.md). Target Develop_ViewLiftOne keeps VLAnalytics, VLAuthentication, "
            "VLBeaconLib, VLNotificationServiceLib, VLPlayerLib on Develop_Analytics, VLStoreKit on Develop_StorekitV2, VisualEffectView on master.")
    # --- Apple ---------------------------------------------------------------------------
    if ws or pj:
        add("profiles", "xcode")
        flag = f"-workspace '{ws}'" if ws else f"-project '{pj}'"
        here = os.path.dirname(os.path.abspath(__file__))
        add("discover", f"xcodebuild -list -json {flag}")
        add("build", f"python3 '{here}/build_xcode.py' --repo . {'--workspace' if ws else '--project'} '{ws or pj}' --out <report folder>")
        add("notes", "Xcode: build with build_xcode.py — it resolves Swift packages once, then builds every scheme ONE AT A TIME in its own "
                     "DerivedData and separates environment failures (locked build.db, stale module cache) from real code errors. "
                     "Never start xcodebuild runs in parallel or in the background. If the editor limits command time, call it once per scheme with --scheme.")
        add("protect", "**/Package.resolved", "**/*.entitlements", "**/GoogleService-Info*.plist")
    if os.path.exists(os.path.join(root, "Podfile")):
        add("profiles", "cocoapods"); add("regenerate", "Podfile.lock: run `pod install` after merging Podfile (keep target's lock otherwise)")
    if os.path.exists(os.path.join(root, "Package.swift")):
        add("profiles", "swiftpm"); add("build", "swift build")
    # --- Android / JVM -------------------------------------------------------------------
    if os.path.exists(os.path.join(root, "gradlew")):
        add("profiles", "gradle")
        add("build", "./gradlew assembleDebug", "./gradlew compileDebugUnitTestSources")
        add("notes", "Gradle: if assembleDebug fails because of flavours, run `./gradlew tasks --all | grep -i assemble` and build each flavour's Debug.")
        add("protect", "**/google-services.json", "**/*.keystore", "local.properties")
    elif os.path.exists(os.path.join(root, "pom.xml")):
        add("profiles", "maven"); add("build", "mvn -q -DskipTests compile")
    # --- Flutter / Node / others --------------------------------------------------------
    if os.path.exists(os.path.join(root, "pubspec.yaml")):
        add("profiles", "flutter"); add("build", "flutter pub get", "flutter analyze")
        add("regenerate", "pubspec.lock: flutter pub get")
    if os.path.exists(os.path.join(root, "package.json")):
        add("profiles", "node")
        pm = "pnpm" if os.path.exists(os.path.join(root, "pnpm-lock.yaml")) else "yarn" if os.path.exists(os.path.join(root, "yarn.lock")) else "npm"
        try:
            scripts = json.load(open(os.path.join(root, "package.json"))).get("scripts", {})
        except Exception:
            scripts = {}
        add("build", f"{pm} install")
        for s in ("typecheck", "lint", "build"):
            if s in scripts:
                add("build", f"{pm} run {s}")
        if not any(s in scripts for s in ("typecheck", "build")) and os.path.exists(os.path.join(root, "tsconfig.json")):
            add("build", "npx tsc --noEmit")
        add("regenerate", f"lockfile: run `{pm} install` after merging package.json — do not hand-merge the lockfile")
        if os.path.isdir(os.path.join(root, "ios")) and os.path.exists(os.path.join(root, "ios", "Podfile")):
            add("notes", "React Native: also `cd ios && pod install`, then build the iOS workspace in ios/.")
    if os.path.exists(os.path.join(root, "go.mod")):
        add("profiles", "go"); add("build", "go build ./...", "go vet ./...")
    if os.path.exists(os.path.join(root, "Cargo.toml")):
        add("profiles", "rust"); add("build", "cargo build")
    if exists(root, "*.sln", "*.csproj"):
        add("profiles", "dotnet"); add("build", "dotnet build")
    if exists(root, "pyproject.toml", "setup.py", "requirements.txt"):
        add("profiles", "python"); add("build", "python3 -m compileall -q .")

    # --- lint / generated code / tests (any stack) ------------------------------------------
    lint = first(root, ".swiftlint.yml", "*/.swiftlint.yml")
    if lint:
        add("lint", f"swiftlint lint --quiet --config '{lint}' <merged files>")
    for f, how in ((first(root, "apollo-codegen-config.json", "*/apollo-codegen-config.json"), "apollo-ios-cli generate --path {f}"),
                   (first(root, "swiftgen.yml", "*/swiftgen.yml"), "swiftgen config run --config {f}"),
                   (first(root, ".sourcery.yml", "*/.sourcery.yml"), "sourcery --config {f}"),
                   (first(root, "buf.gen.yaml", "*/buf.gen.yaml"), "buf generate")):
        if f:
            add("regenerate", "generated code: " + how.format(f=f) + "  (confirm the exact command with the developer)")
    if os.path.exists(os.path.join(root, ".eslintrc.json")) or os.path.exists(os.path.join(root, ".eslintrc.js")):
        add("lint", "npx eslint <merged files>")

    if not prof["build"]:
        prof["ask_developer"] = True
        add("notes", "No build system detected — ask the developer for the build/compile command (and offer to save it in .merge-guard.json).")
    return prof


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    root = os.path.abspath(os.path.expanduser(sys.argv[1]))
    if "--example-config" in sys.argv:
        print(json.dumps(EXAMPLE, indent=2)); return
    prof = detect(root)
    cfg_path = os.path.join(root, ".merge-guard.json")
    if os.path.exists(cfg_path):
        try:
            cfg = json.load(open(cfg_path))
        except ValueError as e:
            sys.exit(f"{cfg_path} is not valid JSON ({e}) — fix it or remove it")
        prof["profiles"].insert(0, f"config:{cfg.get('profile', '.merge-guard.json')}")
        for k in ("post_merge", "build", "discover", "lint", "test"):      # team config replaces detected commands
            if k in cfg:
                if not cfg[k] and prof[k]:
                    prof["notes"].append(f".merge-guard.json sets \"{k}\": [] but the repo suggests {prof[k]} — confirm with the developer "
                                         "that skipping it is intended.")
                prof[k] = list(cfg[k])
        for k in ("protect", "regenerate", "notes"):         # lists are combined
            if k in cfg:
                prof[k] = list(cfg[k]) + [x for x in prof[k] if x not in cfg[k]]
        for k in ("mode", "confidence_threshold", "merge_branch", "record_as_merge", "generated", "parallel_modules", "required_targets"):
            if k in cfg:
                prof[k] = cfg[k]
        prof["ask_developer"] = not prof["build"]
        prof["config_file"] = cfg_path
    print(json.dumps(prof, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
