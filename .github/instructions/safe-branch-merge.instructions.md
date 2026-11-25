---
applyTo: "**"
---

Skill folder: `.claude/skills/safe-branch-merge` — read `.claude/skills/safe-branch-merge/SKILL.md` before any branch merge; scripts are in `.claude/skills/safe-branch-merge/scripts/`.


# Rule: safe branch merge — never lose code, never commit

Works with the `safe-branch-merge` skill (SKILL.md next to this file, or the skill folder named at the top of this rule). Applies to any repository and any stack.

## 1. Git: the developer commits and pushes — never the AI
- **Never** run `git commit`, `git commit --amend`, `git merge --continue`, `git rebase --continue`, `git cherry-pick --continue`, `git push`, `git push --tags`, or anything that creates a commit or writes to a remote, even if a step seems to need it. This holds even when the developer says "go ahead and finish".
- Merge with `git merge --no-ff --no-commit` and leave the result staged and uncommitted.
- Don't **offer** to commit either. Not for the merge, not for the skill's own files, not "just this one file". If something needs committing first, the developer does it.
- At the end, hand over a ready commit message + description (`COMMIT_MSG.txt`) and the command the developer can run themselves.
- Allowed git writes: `fetch` (incl. the private ref `refs/merge-guard/source`), `merge --no-commit`, staging (`add`, `rm`, `mv`, `checkout --ours/--theirs -- <file>`) while resolving, and a local backup tag `merge-guard/backup/<REPORT_ID>`. A `stash` is allowed only after the developer says yes.
- Never run `reset --hard`, `checkout -- .`, `clean -fd`, `stash drop`, `branch -D`, `tag -d`, `merge --abort`, or delete files without an explicit yes.

## 2. Zero silent loss
- Every change on the source branch since the merge-base (or the agreed `--since` point) must end up **merged**, **ported** to where that logic lives now, or **dropped by a recorded decision**: an AI decision with concrete evidence, or a developer decision. Nothing else is acceptable.
- A clean git auto-merge doesn't prove the code is correct. Changes next to target edits, moved files, deleted files, project files and lockfiles are reviewed item by item.
- Never resolve with a whole-file `--ours` / `--theirs` / "accept all", except for files the developer decided that way (protected files, binaries).
- Project / solution files (`project.pbxproj`, `.csproj`, `build.gradle`, `package.json` …): never take a whole side. Start from target and re-apply source's additions. Lockfiles are regenerated, not hand-merged.
- Run `verify_coverage.py` after merging and again after build fixes. A `MISSING` line blocks hand-over until restored, or until it is confirmed (by evidence or by the developer) as an intended drop.

## 3. Autonomous by default: decide from the code, ask only when it can't be settled
- Work through analysis, review, merge, verification, build and hand-over **without stopping**. Stop only for the stop list in SKILL.md "Operating mode":
  - missing intake;
  - preflight `BLOCK`;
  - `needs_developer` file-map rows or `auto_decide.py` escalations;
  - business choices the code can't settle;
  - behaviour-changing fixes;
  - unrestorable `MISSING` code, or an `ENV_FAIL`;
  - destructive steps no decision covers.
  Ask all open points **at once**, in one compact message, then continue. Review mode (report and wait) only when the developer asks for it, or `.merge-guard.json` says `"mode": "review"`.
- **Every AI decision is reviewed from the code logic, not from snippets:**
  - read the whole function in base / source / target, plus its callers;
  - find the business rule;
  - check whether target already does it elsewhere, or removed it on purpose (`git log -S`);
  - make sure proposed code only uses identifiers that exist in target;
  - record `ai_confidence`, `ai_evidence`, and a one-line why.
- **Independent check:** high-severity items and anything that drops source code get a second review. That's a separate sub-agent when the editor has them, otherwise a deliberate second pass that tries to prove the opposite. A disagreement is escalated, never averaged.
- **The AI never drops source code or behaviour without evidence** (target already does it, removed on purpose by commit X, no callers). Without evidence it escalates. It never replaces branch-specific values with source's on its own. `CUSTOM` and business choices go to the developer.
- Always ask for the source branch, target branch, source folder and target folder if the request doesn't name them. Never guess them.
- Escalations show the **developer name, date, commit and old/new snippet** of the conflicting lines.
- **Developer names are line-exact.** Name only the people who wrote (or removed) the exact conflicting lines on each side, using line-level `git blame` and the commit that deleted the line. Never name someone just because they touched the same file or made the latest commit on it. Show their line numbers. If a line came from a cherry-pick or port, also name the original author. If the exact author can't be found, say so instead of guessing.
- If one side refactored or optimised code the other side changed, flag it (`OPTIMIZED_IN_TARGET` / `OPTIMIZED_IN_SOURCE`) with a recommended merged snippet. Keep the better structure **and** every business rule from both sides.
- **Different folder structure:** compare a source file only with the target file that really holds the same code. Confirmed means: same path, git rename, a folder move backed by other files, or confirmed by the developer in `path-map.json`. A shared file name alone is never enough, especially for common names like `Info.plist`, `CodeResources`, `Contents.json`, `Package.swift`. If unsure, don't compare or label anything: ask, record the answer in `path-map.json`, and re-run the analysis.
- **The AI builds the file map, not the developer.** When structure differs, run `propose_file_map.py`, verify every entry by reading the code, and write `file-map.json` with `decided_by: "ai"`, confidence and a reason. Map at **function** level when logic was split or optimised into other files. For files only in source, choose the owning module, the folder and the build targets (Xcode targets / SPM target). Ask the developer only about rows you can't verify (`needs_developer`), in one compact table; never ask them to confirm everything.
- When the structure differs, don't run a plain `git merge`; port each change into its mapped target file.
- Vendored `.xcframework` / `.framework` / `.bundle` folders are handled as one unit (keep, take whole, or replaced by a package with a pin), never file by file. User state (`xcuserdata`, `.xcuserstate`, `.DS_Store`, DerivedData) is ignored.
- Unknown build command, post-merge step or protected file → ask, and offer to save the answer in `<repo>/.merge-guard.json`.
- When the structure differs, record the port as a merge by default (`git merge --no-commit -s ours` + port every item, after coverage passes) unless `.merge-guard.json` says `"record_as_merge": false`. In the summary, tell the developer that `git merge --quit` drops the merge record but keeps the changes.

## 4. Protect local work
- Analysis (phase 1) is read-only.
- Uncommitted changes in the target folder → stop. Show the files and ask the developer to commit or stash them themselves (offer the stash command).
- Files installed by this skill (`.claude/skills/safe-branch-merge/`, `.cursor/rules/safe-branch-merge.mdc`, `.merge-guard.json`, …) are not local work: ignore them in preflight.
- Protected files (dependency pins, entitlements, signing, environment/client config, Firebase/Google service files and anything in `.merge-guard.json` → `protect`) keep target's values unless a decision says otherwise.

## 5. Report (always), for the record and for overrides
- Phase 1 always writes `~/Downloads/merge-reports/<REPORT_ID>/report.html`, `report.md` and `analysis.json`. In autonomous mode the agent continues afterwards; in review mode it stops for decisions.
- The report separates "Needs you" (escalated), "Decided by AI" (each with confidence, evidence and the independent check) and "Decided by developer". The developer can override any AI decision before committing.
- The report header shows: Report ID, AI tool/editor used, chat/session id (or `unknown`), both folder paths, both branches with head commits, merge-base, and how to resume.
- Every decision item shows the developers on each side, dates, commits, base / source / target snippets, AI analysis, AI recommendation and proposed code.

## 6. Resume safely
- On "resume merge report <ID>", reload the decisions and re-run preflight. Check both folders are still on the recorded branches and clean (ask to stash otherwise). Compare heads with the report; new commits → analyse the delta and get decisions first.
- Missing, ambiguous, or CUSTOM-without-notes decisions → ask before touching code.
- A developer answer must be explicit for the item it answers. A name, "ok" or "proceed" doesn't answer a specific question — ask again. AI decisions stand unless the developer overrides them.

## 7. After the merge
- Run the project's post-merge steps from `project_profile.py` / `.merge-guard.json` (for AppCMS: `bash setup_environment.sh motv stage`). List the files they changed for the developer.
- **Builds run one at a time, in the foreground — never in parallel or in the background** (parallel xcodebuild into one DerivedData gives false "database is locked" / "modified since the module file was built" failures). Resolve packages first (Xcode: `build_xcode.py` does both).
- Every scheme/target/module must show `BUILD SUCCEEDED` in the **last** sequential run, after the last package change and the last code fix. Environment failures are reported as such, never counted as success. Only then say "it compiles"; otherwise list the failing schemes with their first error.
- Fix compile errors autonomously, without removing business logic or stubbing, and keep platform conditionals intact. Behaviour-changing fixes need a yes.
- Xcode "Skipping duplicate build file" warnings: compare with the target branch (`pbx_targets.py --duplicates`); remove duplicates the merge introduced.
- Re-run the coverage check, then generate `COMMIT_MSG.txt`: a subject line, then for each developer: `developer -- file -- merged line numbers -- item/decision -- developer notes`, plus what was intentionally not merged.
- Final summary: build table, coverage result, counts (AI / developer / auto-merged), every AI decision that dropped or rewrote source code (one line + evidence), files changed by post-merge steps, report path, the commit command.
- Stop there. The developer reviews, commits and pushes.
