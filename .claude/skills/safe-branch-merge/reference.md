# safe-branch-merge — reference

## Report folder
```
~/Downloads/merge-reports/<REPORT_ID>/
  analysis.json            single source of truth (items, AI fields, decisions, status)
  report.html              discussion page for developers (Export decisions button)
  report.md                same content; tick [x] boxes by hand if preferred
  decisions-<ID>.json      exported from report.html (developers save it here)
  verification.md / .json  written by verify_coverage.py in phase 2
  build-summary.md / .json per-scheme results from build_xcode.py (+ build-logs/<scheme>.log)
  COMMIT_MSG.txt           commit message + description for the developer (git commit -F …)
  merge-result.md          written at the end of phase 2
```
`status` in analysis.json: `AWAITING_DECISIONS` → `NEEDS_DEVELOPER` / `AUTO_DECIDED` (auto_decide.py) or `DECISIONS_PARTIAL` / `DECISIONS_RECEIVED` (parse_decisions.py) → `MERGED_UNCOMMITTED`.
The skill never commits or pushes; after the developer commits, the status can be left as is.

## Autonomous mode (default) and escalation
`auto_decide.py` turns the AI review into decisions. Fields the agent fills per decision item:
| field | meaning |
|---|---|
| `recommended_option` | SOURCE / TARGET / BOTH / AI (CUSTOM always escalates) |
| `ai_confidence` | 0.9+ proven by code or history · 0.8–0.9 strong reading · < 0.8 escalates (threshold: `.merge-guard.json → confidence_threshold`) |
| `ai_evidence` | concrete proof; **required** when the choice drops source code/behaviour |
| `escalate`, `escalate_reason` | business choice the code can't settle |
| `check_verdict`, `check_note` | independent second review (`agree` / `disagree`); **required** for high severity |
Result per item: `decision` + `decided_by: "ai"`, or `escalated: true` + `escalation_reasons` (shown under "Needs you").
Hard escalation rules (no confidence overrides them): missing review · `escalate` · low confidence · check disagrees or is missing on high severity · drops source code without evidence · source values into a protected file · AI/BOTH without `proposed_code` · CUSTOM.
Developer answers/overrides: `decided_by: "developer"`. `parse_decisions.py` marks any exported choice that differs from the AI decision as a developer override.

`.merge-guard.json` mode keys: `"mode": "auto" | "review"`, `"confidence_threshold": 0.8`, `"merge_branch": "direct" | "new"`, `"record_as_merge": true`.

## Commit message (COMMIT_MSG.txt)
```
Merge Develop into Develop_Analytics

Merged Develop@48a4027d6 into Develop_Analytics@14ad8c909 (base 7afa09ecb, shared-history).
Merge report: MRG-20261124-1700-Develop-into-Develop_Analytics | generated with Cursor | chat/session: Merge Develop
Decisions by: Rakesh
Coverage check: PASS (missing 0, moved 0)
Post-merge: bash setup_environment.sh motv stage ✔
Build: AppCMS (iOS) ✔, AppCMS_tvOS ✔

Changes merged, by developer (developer -- file -- merged line numbers -- item):
Sam Source <sam@x.com>
  - Sam Source -- AppCMS/Core/Networking/APIClient.swift (from AppCMS/Network/API.swift) -- L3 -- M-0002 RESTRUCTURED → SOURCE (2026-10-05 48a4027d6)
  - Sam Source -- AppCMS/Player/PlayerManager.swift -- L20-22 -- M-0005 CONFLICT → BOTH (2026-10-05 48a4027d6; target side: Tara Target 2026-10-02) -- note: keep guard+analytics, add backoff

Intentionally NOT merged (developer decision):
- AppCMS/Network/Old.swift -- M-0003 DELETED_IN_TARGET → TARGET -- by Sam Source 2026-10-05 -- note: Old.swift intentionally removed (Tara)
```
Line numbers are in the **merged** file (found by locating the item's code in the working tree). "rewritten in merge" means the code was re-expressed (AI/BOTH/CUSTOM) and only part of it matches the source lines.

## Project profiles and `.merge-guard.json`
`scripts/project_profile.py <repo>` detects the stack and returns protected globs, post-merge commands, build/discover commands and lockfiles to regenerate.

| Detected by | Profile | Post-merge | Build |
|---|---|---|---|
| `setup_environment.sh` + `AppCMS.xcodeproj/.xcworkspace` | `appcms` | `bash setup_environment.sh motv stage` | every Xcode scheme, iOS + tvOS |
| `*.xcworkspace` / `*.xcodeproj` | `xcode` | — | `build_xcode.py` (resolve packages once, every scheme sequentially, env vs code errors) |
| `Podfile` / `Package.swift` | `cocoapods` / `swiftpm` | `pod install` if Podfile changed | `swift build` |
| `gradlew` / `pom.xml` | `gradle` / `maven` | — | `./gradlew assembleDebug compileDebugUnitTestSources` / `mvn compile` |
| `pubspec.yaml` | `flutter` | `flutter pub get` | `flutter analyze` |
| `package.json` | `node` (npm/yarn/pnpm by lockfile) | install | `typecheck` / `lint` / `build` scripts, else `tsc --noEmit` |
| `go.mod`, `Cargo.toml`, `*.sln`, `pyproject.toml` | `go`, `rust`, `dotnet`, `python` | — | `go build ./...`, `cargo build`, `dotnet build`, `compileall` |
| nothing | — | — | **ask the developer**, offer to save in `.merge-guard.json` |

A team can commit `<repo>/.merge-guard.json` to make the behaviour explicit for that project (its `build`, `post_merge` and `discover` replace the detected ones; `protect`, `regenerate` and `notes` are added):
```json
{
  "profile": "appcms",
  "protect": ["**/Package.resolved", "AppCMS/Config/*.xcconfig"],
  "post_merge": ["bash setup_environment.sh motv stage"],
  "discover": ["xcodebuild -list -json -workspace AppCMS.xcworkspace"],
  "build": [
    "python3 .claude/skills/safe-branch-merge/scripts/build_xcode.py --repo . --workspace AppCMS.xcworkspace --scheme AppCMS --scheme AppCMS_tvOS --out <report folder>"
  ],
  "regenerate": ["Podfile.lock: pod install"],
  "notes": ["VLPlayerLib pin stays on Develop_Analytics in Develop_ViewLiftOne"]
}
```

## Editors and installation
`bash install.sh <repo path>` (drag the folder in; or `--global`) writes the same rule for every editor, points them all at one copy of the skill, and creates `.merge-guard.json` if missing (`--no-config` to skip):

| Editor | File written | How it is picked up |
|---|---|---|
| Claude Code | `.claude/skills/safe-branch-merge/` + block in `CLAUDE.md` | skill auto-discovered; CLAUDE.md always loaded |
| Cursor | `.cursor/rules/safe-branch-merge.mdc` | agent-requested rule (by description) |
| Windsurf | `.windsurf/rules/safe-branch-merge.md` | model-decision rule |
| GitHub Copilot | `.github/instructions/safe-branch-merge.instructions.md` | repository instructions |
| Codex, Jules, Aider, Zed, others | block in `AGENTS.md` | AGENTS.md convention |
| Claude desktop | keep the folder connected, or add it to your account's skills | — |
Any other editor: point it at `SKILL.md` and `safe-branch-merge.mdc` (plain Markdown under the front matter).

## Categories (script = `category`, agent may refine in `ai_category`)

| Category | Meaning | Decision? | Default action |
|---|---|---|---|
| `CONFLICT` | Source and target changed overlapping/adjacent lines (git would conflict) or the same new file was added with different content | Yes | Per decision |
| `MAPPING_UNCERTAIN` | Source changed a file whose target counterpart can't be identified with confidence — nothing compared | Yes | Confirm the path in path-map.json, re-run |
| `VENDORED_BUNDLE` | A vendored .xcframework/.framework/.bundle changed — one item per bundle | When target lacks or changed it | Keep / take whole / package pin |
| `OPTIMIZED_IN_TARGET` *(agent)* | Target refactored/optimised the region; source changed behaviour on the old code | Yes | Keep target structure, re-express source behaviour, show proposed code |
| `OPTIMIZED_IN_SOURCE` *(agent)* | Source brings the refactored/optimised version; target changed the old one | Yes | Take source structure, re-apply target-only behaviour |
| `DELETED_IN_TARGET` | Source changed a file target deleted or moved beyond recognition | Yes | Find new home or confirm drop |
| `DELETED_IN_SOURCE` | Source deleted a file target still has | Yes | Delete only if nothing references it |
| `RESTRUCTURED` | File is at another path in target; decision needed when mapping confidence < 0.85 | Sometimes | Port hunk into mapped file |
| `NEW_FILE` | File added in source; decision needed when its folder structure is missing in target | Sometimes | Add at path + Xcode targets |
| `PROJECT_FILE` | `project.pbxproj` changed: file refs, memberships, packages, new targets (other project files — `.csproj`, `build.gradle`, `package.json` — appear as normal items; treat them the same way) | When packages/targets/removals change | Rebuild from target + re-add |
| `PROTECTED` | Package.resolved / Podfile.lock / entitlements / GoogleService-Info / user globs | Yes | Keep target |
| `NEAR_CHANGE` | Merges cleanly but target changed code within 15 lines | Review | Take source, re-read function |
| `BINARY` | Binary asset changed | When both sides changed | Pick one side |
| `LARGE_FILE` | > 1.5 MB text | Yes | Review with a diff tool |
| `CLEAN` | Only source touched this region | No | Take source |
| `ALREADY_PRESENT` | Identical/equivalent change already in target (incl. cherry-picked commits) | No | Nothing |
| `COSMETIC` | Whitespace only | No | Take source |

Signals the script adds (shown as ⚠ on cards): target/source rewrote a much larger region (optimisation hint), part of the added lines already exist (duplicate fix), target change N lines away, protected file, mapping method/confidence.

## Decision options

| Option | Code items | NEW_FILE | DELETED_IN_TARGET | DELETED_IN_SOURCE | PROTECTED / PROJECT_FILE |
|---|---|---|---|---|---|
| `SOURCE` | Take incoming | Add at suggested path | Port change into target | Delete in target too | Use source values / re-add source refs |
| `TARGET` | Keep current (source change intentionally dropped) | Don't add | Drop — removal intentional | Keep file | Keep target |
| `BOTH` | Keep both behaviours, merged without duplicates | Add at another path (notes) | Restore file + change | Keep, apply notes | Merge values |
| `AI` | Apply `proposed_code` | — | — | — | — |
| `CUSTOM` | Follow `decision_notes` exactly (notes required) | | | | |

`TARGET` is the only option that means "this source code may disappear"; verification skips those items and nothing else.

## Developer attribution (line-exact)
- **Base (common ancestor)** = the code at the last commit both branches share (the merge-base, or `--since`), before either branch changed it. Comparing each side with Base shows who changed what.
- Incoming lines: `git blame` on the source branch for exactly the changed lines, limited to commits after Base.
- Removed lines: the first commit after Base whose diff deletes that line (exact; not "someone who touched the file").
- Target side: the same, only for the target hunks that actually collide with the source hunk (`CONFLICT`). Nearby hunks are used only for `NEAR_CHANGE`.
- Each author entry has `role` (`changed / added / removed … lines`), `line_numbers` (in the branch file) and `base_line_numbers` (removed from Base). `committer` is shown if different from the author, and `ported_from` (original author) when the commit message has `(cherry picked from commit …)`.
- Snippets carry a per-line author gutter (`authors`), shown next to the code in the report.
- File-level authors are used only where the whole file is the item (deleted file → the commit that deleted it; binary/project files → the commits that changed them). New files use line-level blame of the whole file.

## How files are mapped when structure differs (collect_changes.py)
Order, first match wins:
1. `path-map.json` (`--map-file`): file or folder entries confirmed by the developer; `null` = not in target → confidence 1.0
2. Same path, or the merge-base path → 1.0
3. Git rename detection base→target → ≥ 0.86
4. **Folder move**: other files from the same source folder moved to one target folder. Evidence comes from git renames, plus unique non-generic file names whose content is still ≥ 50% similar; a file is never evidence for itself. Needs ≥ 2 other files, or 1 other file plus a unique file name → 0.85–0.97
5. Same file name: **generic names** (`Info.plist`, `CodeResources`, `Contents.json`, `Package.swift`, … or any name appearing ≥ 3 times in target) only count when the parent folder matches too. Score = content similarity + matching parent folders.
6. Declared type search (`class/struct/enum/protocol/actor/extension X`) → ≤ 0.75
7. Nothing → not found

**Confidence < 0.85 = not trusted.** A modified file becomes one `MAPPING_UNCERTAIN` item; nothing is compared, and the guess is shown as `guessed_target_path`. A file new in source is treated as new, with no comparison against a weak match.
**Vendored bundles** (`*.xcframework`, `*.framework`, `*.bundle`) are grouped into one `VENDORED_BUNDLE` item per bundle. It shows the files changed, the version (`CFBundleShortVersionString`) on base/source/target, and where target references the bundle (Package.resolved, Package.swift, pbxproj, Podfile).
**Noise** (`xcuserdata/`, `*.xcuserstate`, `.DS_Store`, `DerivedData/`, `Pods/`, `build/`, `node_modules/`, plus `--ignore` globs) is listed under `ignored_files`, never as items.
**New files**: suggested folder = the folder map, or where ≥ 2 unique sibling files of the same folder ended up; otherwise flagged "STRUCTURE MISSING".
`analysis.json → structure`: `restructured`, `strategy` (`git-merge` | `port-per-file`), `folder_map[]` (source_dir, target_dir, votes, used_by, confirmed), counts of moved, uncertain and missing files.

## File map (`file-map.json`, schema `file-map/1`)
Drafted by `propose_file_map.py`, then reviewed and decided by the AI, then passed to `collect_changes.py --map-file`.
```json
{
  "schema": "file-map/1",
  "report_id": "MRG-…",
  "folders": { "VLAnalytics/Analytics/Client/Braze/": "VLAnalytics/Sources/VLAnalyticsBraze/Client/", "VLAnalytics/ConvivaIMASDK.xcframework/": null },
  "files": {
    "Analytics/VLAnalytics.swift": {
      "status": "split",
      "target": "Sources/VLAnalyticsLib/Core/VLAnalytics.swift",
      "symbols": {
        "VLAnalytics.setAttConsent(_:)": { "target": "Sources/VLAnalyticsLib/Consent/VLAnalytics+Consent.swift", "evidence": "same name + signature" },
        "VLAnalytics.registerDeviceToken(_:)": { "target": "Sources/VLAnalyticsLib/Core/VLAnalytics.swift", "evidence": "new — next to class declaration" }
      },
      "confidence": 0.9, "decided_by": "ai", "needs_developer": false,
      "note": "Facade split: consent API moved to VLAnalytics+Consent.swift; legacyPing removed in target by Tara (dd5c809, no callers)."
    },
    "Analytics/Client/Braze/BrazePushHelper.swift": {
      "status": "new",
      "placement": { "path": "Sources/VLAnalyticsBraze/Client/BrazePushHelper.swift", "why": "imports BrazeKit like the Braze module; uses BrazeManager",
                     "xcode_targets": ["VLAnalyticsBraze", "VLAnalyticsBraze_tvOS"], "spm_target": "VLAnalyticsBraze" },
      "confidence": 0.95, "decided_by": "ai", "needs_developer": false
    },
    "Analytics/Old/Helper.swift": { "status": "not-in-target", "confidence": 0.9, "decided_by": "ai", "note": "removed with the split (commit …)" }
  }
}
```
| status | meaning | effect in collect_changes.py |
|---|---|---|
| `mapped` | whole file lives at `target` | compared with that file; **function by function** if it was heavily rewritten (similarity < 0.6) |
| `split` | functions now in several files | each changed function compared with the same function in its `symbols[...].target` file |
| `new` | only in source | `NEW_FILE` with `suggested_target_path`, `xcode_targets`, `spm_target` from `placement` |
| `not-in-target` | removed / replaced on purpose | changes are `DELETED_IN_TARGET` items to confirm as dropped |
| `unknown` | AI could not tell | stays `MAPPING_UNCERTAIN` → ask the developer |
Symbol keys: `Type.name(label:label:)` for Swift, `Class.sel:ector:` for Objective-C, `Class.name(argCount)` for Kotlin/Java/C#/JS (see `scripts/symbols.py <file>`).

Function-level categories: `NEW_SYMBOL` (new in source, add next to its type), `SYMBOL_NOT_FOUND` (target has no such function: removed, renamed or rewritten → decide), plus `RESTRUCTURED` / `CONFLICT` / `ALREADY_PRESENT` with `compare: "symbol"`, `source_symbol`, `target_symbol`.

## Edge-case catalogue (think through every one)

**Repository / working tree**
- Same folder for source and target → source read from its ref; never check it out.
- Different folder structure (monolith ↔ modules, renamed top folders, sample app moved) → `structure.strategy = port-per-file`; confirm the folder map and path-map.json first (SKILL 1.25).
- Vendored binary SDK in one branch, package dependency in the other → `VENDORED_BUNDLE`; compare versions with the package pin.
- One source file split into several target files (facade + extensions, per-vendor modules) → `split` in the file map; compared per function.
- Function renamed / merged into a helper / rewritten in target → `SYMBOL_NOT_FOUND`; search by behaviour (calls, literals), `git log -S` to find who removed it and why.
- New source file in a folder that no longer exists → `new` with module/folder/targets chosen by the AI (imports, used types, sibling modules, Xcode/SPM membership); per-platform twins (iOS/tvOS) when the module is split per platform.
- Access control after moving into another module (`internal` → `public`), and imports of the new module, must be adapted when porting.
- Two clones of the same repo → source fetched into target as `refs/merge-guard/source` (re-fetch on resume).
- Unrelated histories (copied/imported repo) → `--since` required; no `git merge`; port item by item.
- Local branch behind origin / unpushed commits / uncommitted source changes → preflight BLOCK/WARN; ask.
- Uncommitted target changes, merge/rebase/cherry-pick in progress, detached HEAD → BLOCK; ask to stash/finish.
- Existing stashes → mention, never drop. Submodules → review pointer bumps by hand. LFS → `git lfs pull` first.
- Heads moved between report and resume → delta analysis, new decisions.

**History quirks**
- Commits cherry-picked or squash-merged earlier → `git cherry` marks them "equivalent already in target"; hunks become `ALREADY_PRESENT`.
- Code lost in earlier merges (git thinks it is merged but it is gone) → audit with `--since <older date>`; `ALREADY_PRESENT` checks the actual target content, so missing code shows up as `CLEAN`/`CONFLICT` items again.
- Reverts on one side → the revert is a change too; ask whether the revert should win.
- Merge commits inside the source range → analysis is content-based (base→head), so their changes are included; authors come from blame.

**Code level**
- Same bug fixed differently on both sides → `CONFLICT` with "partially present" signal; keep one fix, not both.
- Target optimised the function, source changed behaviour in the old one (and vice versa) → `OPTIMIZED_*` with proposed code.
- Source renamed/removed a function target still calls (or target renamed one source calls) → compile errors after merge; fix by adapting the call, not by deleting it.
- Code moved within the same file → shows as delete + add; check the moved block isn't duplicated.
- Platform conditionals `#if os(iOS)` / `#if os(tvOS)` → keep them on both sides; check the merged block is in the right branch of the `#if`.
- Feature flags / remote config keys / analytics event names / notification names / UserDefaults keys / API paths → string changes are business logic; never drop.
- Localizable.strings → union of keys; same key different text → decision.
- Storyboards / xibs → XML conflicts; prefer one side + re-apply the other's change in Interface Builder; ask.
- Info.plist / entitlements / xcconfig → keys per target; usually protected.
- Generated files (R.swift, SwiftGen, GraphQL codegen) → regenerate instead of merging.
- Deleted test files / renamed tests → keep tests of both sides.

**Xcode / packages**
- New file must be added to the right targets (iOS, tvOS, extensions, test targets) — read membership from source's project with `pbx_targets.py --ref`.
- A source target that doesn't exist in target → ask (new target, or map to an existing one).
- Xcode 16 synchronized folders → membership is automatic; check exceptions.
- SPM: `Package.resolved` and `XCRemoteSwiftPackageReference` requirements are protected — branch-specific pins stay as in target.
- CocoaPods: `Podfile` merge by hand, `Podfile.lock` keep target then `pod install` if Podfile changed.

## Protected defaults
`**/Package.resolved`, `**/Podfile.lock`, `**/*.entitlements`, `**/GoogleService-Info*.plist` plus anything passed with `--protect`.

### AppCMS (iOS-ViewliftONE) known branch-specific pins
When the target is `Develop_ViewLiftOne`, these package pins belong to the target and must not be replaced by Develop's:
VLAnalytics, VLAuthentication, VLBeaconLib, VLNotificationServiceLib, VLPlayerLib → branch `Develop_Analytics`;
VLStoreKit → branch `Develop_StorekitV2`; VisualEffectView → `master`.
For other targets, ask which pins are branch-specific and pass them as `--protect` or note them in the report.

## analysis.json item fields
```
id, file, base_path, target_path, final_path (set during merge), mapping{method, confidence, candidates, note}, kind,
category, ai_category, severity(high|medium|low|info), needs_decision, title, signals[],
base/source/target {start (1-based), lines[], marked[] (indices of changed lines)},
summary_lines[] (pbxproj / Package.resolved), suggested_target_path, suggestion_reason,
source_authors[] / target_authors[] {name, email, date, sha, short, subject, role, line_numbers[], base_line_numbers[], lines, committer?, ported_from?},
added_norm[] / removed_norm[] (normalised non-trivial lines used by verify_coverage.py),
ai_analysis, ai_recommendation, recommended_option, proposed_code, proposed_language,
decision, decision_notes
```
Top level: report_id, generated_at, status, generator{tool, session_id, resume_hint}, source/target{branch, folder, repo_root, ref, head},
same_checkout, mode (shared-history | unrelated-history), merge_base, analysis_base, base_note, protected_globs, summary, developers, commits[], files[], target_only_changes[], items[], decisions_meta.

## Script exit codes
| Script | 0 | other |
|---|---|---|
| preflight.sh | always 0 — read `VERDICT:` | — |
| collect_changes.py | ok | 1 = error / unrelated history without `--since` |
| render_report.py | ok | 3 = AI fields missing on decision items (report still written) |
| parse_decisions.py | all decided | 2 = missing / ambiguous / CUSTOM without notes |
| verify_coverage.py | PASS | 1 = MISSING lines or conflict markers |
| project_profile.py | ok (read `ask_developer`) | — |
| propose_file_map.py | ok — writes file-map.draft.json | — |
| auto_decide.py | everything decided → continue | 2 = escalations listed → ask the developer once |
| build_xcode.py | every scheme SUCCEEDED | 1 = a scheme failed (`CODE_FAIL` / `ENV_FAIL` / `FAILED`) or package resolution failed |
| commit_message.py | ok — never commits | — |
| add_to_targets.rb | ok | 2 = target name not found |
