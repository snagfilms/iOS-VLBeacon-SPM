---
name: safe-branch-merge
description: >-
  Zero-loss merge of one git branch into another in any project and any stack (iOS/tvOS,
  Android, web, backend), including branches whose folder/file structure differs, e.g.
  Develop → Develop_Analytics. Use when the user asks to merge, sync, port or bring changes
  from one branch into another, says "don't miss any code", "compare branches before merging",
  "make a merge report", or "resume merge report MRG-…", or hands back a decisions file.
  Runs autonomously by default: the AI reviews every change from the code logic (with an
  independent second check), decides, merges without committing, verifies no business logic
  was lost, runs the project's post-merge steps (AppCMS: setup_environment.sh motv stage),
  builds every target, fixes compile errors and hands over a commit message + description —
  stopping only to ask the developer when something is genuinely unclear. A full report (HTML +
  Markdown, every change with developer, date, snippets, AI reasoning) is written to ~/Downloads
  for the record. It never commits or pushes.
---

# Safe branch merge (zero code loss, developer commits)

| Phase | What happens | Git writes |
|---|---|---|
| **1 · Analyse & decide** | Preflight, project profile, compare, AI file map, AI review of every change from the code + independent check, AI decisions, report in `~/Downloads/merge-reports/<REPORT_ID>/` | None (only the private ref `refs/merge-guard/source`) |
| **2 · Merge** | `merge --no-commit` or port per file, add files to targets/modules, verify coverage, post-merge steps, build all targets, fix compile errors, write `COMMIT_MSG.txt` | Working tree + index only. **No commit, no push.** |

## Operating mode: autonomous by default
**Work through both phases without stopping**, deciding everything you can prove from the code. Tell the developer what you're doing in one short line per step. Stop and ask only for the cases below, all at once and in one compact message, then continue.

**Stop and ask only when:**
1. The intake answers are missing (branches, folders), or the sync point for unrelated histories is unknown.
2. Preflight shows a `BLOCK` (local changes, behind origin, wrong branch, operation in progress).
3. File-map rows are marked `needs_developer`, or `auto_decide.py` escalates items. See its hard rules: low confidence, a second-check disagreement, dropping source code without evidence, branch-specific values, a missing proposal.
4. A **business choice** the code can't settle: both sides changed a value, flag, threshold, endpoint, analytics/event name, consent/privacy, payment, auth, DRM or security behaviour differently, with no evidence which one is intended.
5. A port or build fix would **change behaviour** beyond what the decided items say.
6. `verify_coverage.py` reports `MISSING` code you can't restore with confidence, or an `ENV_FAIL` / missing toolchain blocks the build.
7. Anything destructive that no decision covers (deleting files/folders, discarding local work).

Everything else: decide, record the evidence, continue, and list it in the final summary and the report. The developer can override any AI decision before they commit; nothing is ever committed or pushed by you.

**Review mode** (the old flow: write the report and wait for the developer to decide every item) is used only when the developer asks for it ("report first", "review mode", "don't merge yet") or `.merge-guard.json` has `"mode": "review"`.

Follow the rule [safe-branch-merge.mdc](safe-branch-merge.mdc) at all times. Categories, edge cases, config and schema: [reference.md](reference.md).
`SKILL_DIR` = the folder containing this file (wherever it was installed: `.claude/skills/…`, `.ai-skills/…`, or anywhere else).
Scripts need only `git`, `bash` and `python3` (3.8+) and run on macOS, Linux and WSL.

---

## Phase 0 — Intake

Take what the request already says. Ask in one message only for what's missing (use the editor's question UI when it has one); never guess branch names or folders:

1. **Source branch** — merge FROM (e.g. `Develop`).
2. **Target branch** — merge INTO (e.g. `Develop_Analytics`).
3. **Source folder** — local checkout to read the source branch from.
4. **Target folder** — local checkout where the merge happens. It can be the same folder as source.
5. Optional: files that are **branch-specific** in target, beyond `.merge-guard.json` and the defaults.
6. Optional: **audit window** (`--since <commit|YYYY-MM-DD>`) to also re-check older source commits whose code may have been lost in earlier merges.

Then record where this report comes from, so the conversation can be resumed:

| Editor / tool | Tool name to record | Chat / session id |
|---|---|---|
| Claude Code (CLI / IDE) | `Claude Code` | `ls -t ~/.claude/projects/$(pwd \| sed 's#[^A-Za-z0-9]#-#g')/*.jsonl \| head -1 \| xargs basename \| sed 's/.jsonl$//'` → resume hint `claude --resume <id>` |
| Claude desktop / claude.ai | `Claude (desktop)` | the session/chat URL if visible in your context |
| Cursor | `Cursor` | not exposed — ask for the chat title |
| Windsurf, Copilot, Codex, others | the product name | whatever the tool shows (chat title / thread id); otherwise ask |

If unknown, write `unknown`. The Report ID alone is enough to resume from any new chat in any editor.

## Phase 1 — Analyse and decide (read-only)

### 1.1 Preflight and project profile
```bash
bash "$SKILL_DIR/scripts/preflight.sh" "<source_folder>" "<source_branch>" "<target_folder>" "<target_branch>"
python3 "$SKILL_DIR/scripts/project_profile.py" "<target_folder>"
```
Resolve every `BLOCK` by asking the developer:
- **Local changes in the target folder** → show the list and ask them to commit or stash the changes **themselves**. Never offer to commit for them. Run `git stash push -u -m "pre-merge <date>"` only if they explicitly ask you to stash.
  Files the installer created (`.claude/skills/safe-branch-merge/`, `.cursor/rules/safe-branch-merge.mdc`, `.merge-guard.json`, etc.) are ignored by preflight. Don't ask the developer to stash or commit them before merging.
- **Branch behind origin** → ask them to pull.
- **Target folder on a different branch** → ask before switching.
- **Merge, rebase or cherry-pick in progress** → ask them to finish or abort it.

Put the `WARN` lines into your notes for the report.

The profile gives you protected globs, post-merge commands and build commands. If it says `ask_developer: true`, ask for the build command now and offer to save it in `<target>/.merge-guard.json` (template: `project_profile.py <repo> --example-config`).

### 1.2 Collect every change
```bash
python3 "$SKILL_DIR/scripts/collect_changes.py" \
  --source-folder "<source_folder>" --source-branch "<source_branch>" \
  --target-folder "<target_folder>" --target-branch "<target_branch>" \
  --out ~/Downloads/merge-reports/<REPORT_ID> --report-id <REPORT_ID> \
  --tool "<tool>" --session-id "<id>" --resume-hint "<e.g. claude --resume id>" \
  --protect <globs from the profile> [--since <commit|date>]
```
`REPORT_ID` = `MRG-<YYYYMMDD-HHMM>-<source>-into-<target>`. If `~/Downloads` is not writable (sandboxed editor), ask for access; if that's refused, use another folder and say where.

Unrelated histories (the target is a copied/re-imported repo): the script stops. Ask the developer for the last sync point (commit or date) and re-run with `--since`. Never guess it.

### 1.25 Build the file map with AI (before reviewing any item)
Do this whenever `structure.restructured` is true, or there are `MAPPING_UNCERTAIN`, `DELETED_IN_TARGET`, `NEW_FILE` or moved files. **You build and decide the map yourself, from the code.** The developer only confirms the rows you can't verify.

1. **Draft:** `python3 "$SKILL_DIR/scripts/propose_file_map.py" <report>/analysis.json` → `<report>/file-map.draft.json`. For every moved, split, missing or new source file it proposes:
   - `mapped`: the file now lives at `target`;
   - `split`: its functions/types now live in several target files (`symbols`: `Type.func(label:)` → file);
   - `new`: only in source; `placement` gives folder, reasons, Xcode `xcode_targets` and SPM `spm_target`;
   - `not-in-target` / `unknown`.
2. **Review every entry by reading the code**, not just the evidence strings:
   - **Moved file (case 2):** open the source and target functions and confirm it is the same code. If names changed, search by behaviour: API calls, string literals, notification and analytics event names, UserDefaults keys (`git grep -n -F "<literal>" <target.ref>`).
   - **Logic optimised or split into other files (case 3):** map **each changed function** to where its behaviour lives now (`symbols`). That can be another file, a renamed function, or a helper that replaced it. Check with `git log -S"<funcName>" --oneline <base>..<target.ref>` who removed or renamed it, and why.
   - **File only in source (case 1):** choose the folder by the module that owns the responsibility (what it imports, which types it uses, where similar files live), not by the old path. Check the build membership:
     - Xcode: same targets as the files already in that folder, including the tvOS/iOS twins;
     - SPM: the target owning that path;
     - Xcode 16 synchronized folders need nothing.
     If the module is split per platform, place it in every platform module that needs it.
   - **Vendored bundles:** check whether target replaced them with a package and compare versions.
3. **Write `<report>/file-map.json`** (schema `file-map/1`, plain JSON, no comments; full schema in reference.md):
   - `status`, `target`, `symbols`, `placement`, `confidence`;
   - `decided_by: "ai"` and a one-sentence `note` (why);
   - `needs_developer: true` **only** when: confidence < 0.8; several plausible homes; a changed function exists nowhere in target and you found no proof it was removed on purpose; or the owning module of a new file isn't clear.
   Folder moves go in `"folders": {"Old/Folder/": "New/Folder/"}`.
4. **Re-run** `collect_changes.py … --map-file <report>/file-map.json`. Repeat steps 2–4 until there are no `MAPPING_UNCERTAIN` items left.
5. If any rows are `needs_developer`, **ask once**, showing only those rows in one compact table, plus the count of rows you decided. Their answers go into `file-map.json` with `decided_by: "developer"`; then re-run. If there are none, **don't ask; continue.** All rows appear in the report's "File map" section.

With the file map, changed files that moved or were restructured are **compared function by function** (`compare: "symbol"`): base function vs source function vs the same function wherever it lives in target. That produces:
- `RESTRUCTURED`: target still has the old version → port the change into it;
- `CONFLICT`: both changed it;
- `ALREADY_PRESENT`;
- `NEW_SYMBOL`: new in source → add it next to its type in the shown file;
- `SYMBOL_NOT_FOUND`: target has no such function → you or the developer decide where the behaviour goes, or that it's obsolete.

Never review, recommend on, or label a change that was matched to a target file only by its name (`Info.plist`, `CodeResources`, `Contents.json`, `Package.swift` …).

### 1.3 Review every item from the code logic (this is the real work)
Review **every** item with `needs_decision: true`, and every `NEAR_CHANGE`, `RESTRUCTURED`, `NEW_SYMBOL`, `NEW_FILE`, `PROJECT_FILE` and `VENDORED_BUNDLE` item.

**Many items?** If your editor can run sub-agents (Cursor Task, Claude Code agents …), split the review into batches by module/file and give each reviewer this checklist, the item ids and `analysis.json`. Merge their results into `analysis.json` yourself and check each one for completeness.

**Checklist per item: read code, not snippets.**
1. Read the **whole function or type** in all three versions (base, source, target): `git -C <target_folder> show <ref>:<path>`. The refs are in analysis.json: `analysis_base`, `source.ref`, `target.ref`.
2. Find the **business rule** the source change adds or alters: inputs, outputs, side effects, conditions, values. Read the commit message / ticket on both sides, and look out for reverts.
3. Check the **callers and the wider effect**: `git grep -n "<name>(" <target.ref>`. Does target already implement the same behaviour somewhere else (search strings, calls, event names)? Did target remove it on purpose (`git log -S"<name>" --oneline <base>..<target.ref>` plus that commit's message)?
4. Respect target's design: locks/actors/threading, platform conditionals, access levels, renamed types. A proposal must use identifiers that **exist in target**; verify each one with `git grep`.
5. Set `ai_category` when more specific: `OPTIMIZED_IN_TARGET` (re-express source behaviour in target's version) or `OPTIMIZED_IN_SOURCE` (take source, re-apply target-only changes).
6. Fill in:
   - `ai_analysis`: 2–5 sentences on what each side does, and what breaks if either side is dropped.
   - `ai_recommendation`: what to keep and why; name the business rule that must survive.
   - `recommended_option`: `SOURCE` / `TARGET` / `BOTH` / `AI` (`CUSTOM` always goes to the developer).
   - `proposed_code` + `proposed_language`: the exact merged code. Required for `AI` and `BOTH`.
   - `ai_evidence`: the concrete proof, e.g. "target already does X at File.swift:120", "removed on purpose in abc123 by <name> ('…')", "no callers", "identical behaviour, different form". Required whenever the choice drops source code or behaviour.
   - `ai_confidence`: **0.9+** proven by code or commit history; **0.8–0.9** strong reading, consistent with callers; **< 0.8** a doubt remains → it will escalate.
   - `escalate: true` + `escalate_reason`: for any business choice the code can't settle (see the stop list), even when you lean one way.
7. For `NEW_FILE` and `NEW_SYMBOL`: confirm the folder/file, the build targets (Xcode `pbx_targets.py`, SPM target, Gradle module …), imports and access levels.
8. When you name developers, use only `source_authors` / `target_authors`. They're line-exact; if a list is empty, say the exact author wasn't found.
9. Check `CLEAN` items for dependencies on something target removed or renamed, and upgrade those to decision items.

### 1.35 Independent check (fresh eyes)
Every `high`-severity item, and every item whose choice drops source code or behaviour, gets a second review.
- **With sub-agents:** run a **separate** checker. Give it the item, the code access and the checklist, but not your conclusion. Then compare its answer with yours.
- **Without sub-agents:** do a deliberate second pass yourself: re-read the three versions and the callers from scratch, and try to prove the opposite decision.

Record `check_verdict` (`agree` / `disagree`) and `check_note`. A disagreement is escalated, never averaged.

### 1.4 Decide, render, continue
```bash
python3 "$SKILL_DIR/scripts/auto_decide.py" ~/Downloads/merge-reports/<REPORT_ID>/analysis.json   # --threshold from .merge-guard.json (default 0.8)
python3 "$SKILL_DIR/scripts/render_report.py" ~/Downloads/merge-reports/<REPORT_ID>/analysis.json
```
- `auto_decide.py` sets `decision` + `decided_by: "ai"` on everything you proved, and lists the **escalations** (exit 2).
- **Escalations:** ask the developer **once**, in one compact table: `ID | file → function | what source does | what target does | your lean + why | the question`. Mention that the full cards are in `report.html` → "Needs you". Record each answer as that item's `decision` with `decided_by: "developer"` and quote their words in `decision_notes`. A name, "ok" or "proceed" is not an answer to a specific question; ask again. Re-run `auto_decide.py` and continue.
- **No escalations:** tell the developer in 2–3 lines where the report is, how many items the AI decided and how many were auto-merged, and that you're **continuing with the merge now**. Don't wait.
- **Review mode** only: stop here and wait for `Resume merge report <REPORT_ID>`.

## Phase 2 — Merge (never commit)
Runs straight after Phase 1 in autonomous mode, or on "Resume merge report <ID>" in review mode / a new chat.

### 2.1 Reload and re-check
1. Load `~/Downloads/merge-reports/<ID>/analysis.json`. Ask for the path if it isn't there.
2. If the developer exported decisions or edited `report.md` (overrides, or review mode), run `python3 "$SKILL_DIR/scripts/parse_decisions.py" <analysis.json>`. Exit code 2 lists items still open (`MISSING` / `AMBIGUOUS` / `CUSTOM-WITHOUT-NOTES`). Ask about only those, in one message.
   - A developer decision must be explicit for that item: a name, "ok" or "proceed" doesn't answer a specific question.
   - AI decisions (`decided_by: "ai"`) stand unless the developer overrides them.
3. Re-run preflight with the recorded folders and branches.
   - Same branches and clean → continue.
   - Local changes → ask the developer to stash first.
   - Different branch → ask.
4. Compare the current heads with `source.head` / `target.head` in the report.
   - If either moved, run `collect_changes.py` into `<ID>-delta` and get decisions on the new or changed items before you merge.

### 2.2 Prepare
- Local safety point (not a commit, never pushed): `git -C <target> tag merge-guard/backup/<ID> HEAD`.
- Work directly on `<target_branch>` (nothing gets committed, and the backup tag allows a full reset). Use a new local branch `merge/<source>-into-<target>-<date>` instead if the developer asked for one or `.merge-guard.json` has `"merge_branch": "new"`. Say which one you used.

### 2.3 Merge
**Choose the strategy from `analysis.json → structure.strategy` and tell the developer which one you'll use:**
- `git-merge` (same folder structure) → the shared-history steps below.
- `port-per-file` (folder structure differs) → **don't run a plain `git merge`.** It would bring back the source's old paths next to the new ones. Port each item into its mapped target file instead (`target_path` / `final_path`), following the action table. New files go to `suggested_target_path` (confirmed). Bundles follow their `VENDORED_BUNDLE` decision.
  - **Default: record it as a merge.** Start with `git merge --no-commit -s ours <source.ref>` (brings no code in; it only records the source branch as merged), then port every item onto it. The developer's commit then marks the source branch as merged, so the next merge starts from here. `.merge-guard.json` `"record_as_merge": false` → plain port without the merge record.
  - Tell the developer in the summary that `git merge --quit` drops the merge record but keeps all ported changes, if they prefer a plain commit.

**Shared history (`git-merge` strategy):** run `git -C <target> merge --no-ff --no-commit <source.ref>`. In a separate checkout, re-fetch `refs/merge-guard/source` first. If git fast-forwards or reports "Already up to date", say so and stop.

Then go through **every item**, not only the ones git flags:

| Item | Action |
|---|---|
| `CONFLICT` | Resolve as decided. `AI` → apply `proposed_code`, adapting only names that changed. `BOTH` → keep both behaviours with no duplicate calls. |
| `OPTIMIZED_IN_TARGET` | Keep target's structure and re-express the source behaviour inside it. |
| `OPTIMIZED_IN_SOURCE` | Take source's version, then re-apply every target-only change on top. |
| `NEAR_CHANGE` / auto-merged | Re-read the whole function; a textual merge can still be wrong logic. |
| `RESTRUCTURED` | Port the hunk into `target_path`. If git brought back the old path, ask before `git rm`. |
| `DELETED_IN_TARGET` | `SOURCE` → port to where the logic lives now. `TARGET` → `git rm` the resurrected file. |
| `DELETED_IN_SOURCE` | `SOURCE` → delete only after `git grep` shows no remaining references. `TARGET` → keep. |
| `NEW_FILE` | Create it at `suggested_target_path` and add it to `xcode_targets` (with `add_to_targets.rb`); an SPM target picks it up from its folder. Adapt imports and access levels (`public`/`internal`) to the new module. |
| `PROJECT_FILE` | Never take a whole side. Start from target (`git checkout --ours -- <file>`), then re-add source's references and memberships. |
| `PROTECTED` | Keep target's version unless the decision says otherwise. |
| Lockfiles | Keep target's file, then regenerate it (see the profile's `regenerate`). |
| `BINARY` | `git checkout --ours` or `--theirs` per the decision. |
| `VENDORED_BUNDLE` | Copy or keep the **whole** bundle as decided; never merge files inside it. If target uses a package instead, apply the decided pin change. |
| `RESTRUCTURED` (compare `symbol`) | Re-apply the source change **inside the target function** shown (`target_symbol` in `target_path`), adapted to target's style. Keep target's optimisations. |
| `NEW_SYMBOL` | Add the function/type to `target_path` next to its type (same file or an extension beside it), adapted to target's style; keep platform conditionals. |
| `SYMBOL_NOT_FOUND` | Per decision: port the behaviour to where the notes/AI proposal say, or drop it as obsolete (recorded). |
| `MAPPING_UNCERTAIN` | Must be resolved in 1.25 before merging. If one is still open, stop and ask. |

Record where moved or ported code really ended up in the item's `final_path`. Verification and the commit message use it.

**Unrelated history:** don't use `git merge`. Port each item by hand following the same table (always `port-per-file`).

**Adding files to targets:**
- Xcode (macOS, needs `gem install xcodeproj`): `ruby "$SKILL_DIR/scripts/add_to_targets.rb" <Proj.xcodeproj> <rel/path/File.swift> "TargetA,TargetB" --dry-run`, then run it again without `--dry-run`. Exit 2 means a target name doesn't exist → ask. Without the gem, edit the project file following an existing sibling file, then check with `pbx_targets.py`.
- Gradle, .NET, CMake, etc.: add the file to the module or project file the same way source did.

### 2.4 Verify nothing was lost (mandatory)
```bash
git -C <target_folder> diff --name-only --diff-filter=U          # must print nothing
git -C <target_folder> grep -nE '^(<<<<<<<|>>>>>>>) ' -- . ':!*.md' # must print nothing
python3 "$SKILL_DIR/scripts/verify_coverage.py" ~/Downloads/merge-reports/<ID>/analysis.json --tree <target_folder>
```
- `MISSING` → restore the code, or ask the developer.
- `MOVED` → confirm it now lives in the right place.
- `CHECK` → you rewrote it (`AI`, `BOTH` or `CUSTOM`); confirm the business rule survived.
- `WARN` (still present) → code source deleted is still there; confirm.

Repeat until it passes, or until the developer has confirmed every remaining line.

### 2.5 Post-merge steps from the profile
Run each `post_merge` command from `project_profile.py` (or `.merge-guard.json`) at the repo root. For AppCMS projects that is:
```bash
bash setup_environment.sh motv stage
```
If a command fails, try to fix the cause from its output (missing file, path, permission); if you can't, show the error and ask. Afterwards, list the files it changed (`git status --short`) so the developer can decide whether they belong in the commit.

### 2.6 Resolve packages, build every target, fix compilation
**Never run builds in parallel or in the background.** Parallel `xcodebuild` runs into one DerivedData fail with `database is locked` / `has been modified since the module file was built`. Those are false failures that hide the real result.

**Xcode projects:** use the build script. It resolves Swift packages once, builds every scheme one at a time in its own DerivedData, retries an environment failure once (clean build), and separates real code errors from environment errors:
```bash
python3 "$SKILL_DIR/scripts/build_xcode.py" --repo <target_folder> --out ~/Downloads/merge-reports/<ID>
# editor limits command time? call it once per scheme: … --scheme VLPlayerLib, then --scheme VLPlayerLib_tvOS, …
```
**Other stacks:** run the profile's `build` commands one after another, in the foreground.

Then:
1. Read `build-summary.md`. Every scheme must be `SUCCEEDED`.
   - `CODE_FAIL` → fix the code (see 3).
   - `ENV_FAIL` → the script already retried once with a clean build. If you can see the cause (e.g. a stale or locked DerivedData, a package not resolved), fix it and build again. Otherwise stop and show it. Never count it as a success or as a code error.
2. **Packages:** if resolving changed `Package.resolved`, or the merge touched package references, check that the protected pins are still target's. Then build **all** schemes again; a build from before a package change doesn't count.
3. Fix compile errors one at a time; use the editor's compile-fix skill if it has one.
   - Keep business logic.
   - Respect platform conditionals (`#if os(iOS)` / `#if os(tvOS)`, flavours, build configs).
   - No stubbing, no deleting calls, no force-unwrap or `try!` shortcuts.
   - Any fix that changes behaviour → ask first.
   - After every fix, rebuild the affected schemes, and at the end rebuild **all** schemes once more.
4. **Duplicate build files:** if the summary lists "Skipping duplicate build file", run `pbx_targets.py <pbxproj> --duplicates` on the merged project and with `--ref <target.ref> --repo <target>` on the target branch. Duplicates that appear only after the merge came from the merge: remove the extra entry. If they were already on target, just mention them.
5. Re-run `verify_coverage.py`; build fixes must not remove merged code.
6. **Hand-over gate:** don't say the merge "compiles" or "is done" until the **last** sequential run shows every scheme `SUCCEEDED`. Put the per-scheme table in your reply. If something still fails or couldn't be built here, say so plainly, with the scheme and first error.
7. If the toolchain isn't available here, give the exact commands, ask the developer to run them, and fix from the errors they paste.

### 2.7 Hand over — the developer commits
Only after the hand-over gate in 2.6 has passed (or the developer has accepted the listed failures):
```bash
python3 "$SKILL_DIR/scripts/commit_message.py" ~/Downloads/merge-reports/<ID>/analysis.json --tree <target_folder> \
  --build "<scheme ✔/✘ list from build-summary.md>" --post-merge "<post-merge commands ✔>"
```
This writes `COMMIT_MSG.txt`:
- subject line;
- merge summary: report ID, editor and session, who decided, coverage and build results;
- **`developer -- file -- merged line numbers -- item/decision -- developer notes`**, grouped by developer;
- changes intentionally not merged, with who decided and why.

**Final summary to the developer** (one message):
- build table: every scheme `SUCCEEDED`;
- coverage result;
- counts: decided by AI / by developer / auto-merged;
- the AI decisions that dropped or rewrote source code, one line each with the evidence, so they can spot-check;
- files changed by post-merge steps;
- the report path.

Then show the full commit message and the command they can run **themselves**: `git commit -F <report>/COMMIT_MSG.txt`. Edit the message if they ask. **Do not commit, continue the merge, or push — not even if asked to "finish it"; explain that this skill leaves commits and pushes to them.**

Then:
- Write `merge-result.md` in the report folder: verification summary, build summary, items handled differently from the report and why.
- Set `status` to `MERGED_UNCOMMITTED` in analysis.json.
- Tell them how to undo before committing: `git merge --abort`, or `git reset --hard merge-guard/backup/<ID>` (their call; you don't run either).
