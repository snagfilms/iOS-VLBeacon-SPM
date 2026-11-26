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
5b. Correctness depends on an **external contract** the repo can't prove: a backend REST/GraphQL schema (e.g. "does the server input type accept this field?"), server behaviour, or another repo's API or package version. Ask the exact question the developer can forward to that team.
6. `verify_coverage.py` reports `MISSING` code you can't restore with confidence, or an `ENV_FAIL` / missing toolchain blocks the build.
7. Anything destructive that no decision covers (deleting files/folders, discarding local work).

Everything else: decide, record the evidence, continue, and list it in the final summary and the report. The developer can override any AI decision before they commit; nothing is ever committed or pushed by you.

**Review mode** (the old flow: write the report and wait for the developer to decide every item) is used only when the developer asks for it ("report first", "review mode", "don't merge yet") or `.merge-guard.json` has `"mode": "review"`.

Follow the rule [safe-branch-merge.mdc](safe-branch-merge.mdc) at all times. Categories, edge cases, config and schema: [reference.md](reference.md).
`SKILL_DIR` = the folder containing this file (wherever it was installed: `.claude/skills/…`, `.ai-skills/…`, or anywhere else).
Scripts need only `git`, `bash` and `python3` (3.8+) and run on macOS, Linux and WSL.

**Generic by design.** Nothing in the scripts is tied to one project: they detect the stack (Xcode app, Swift package, framework with a podspec, Gradle, Node …) and read everything project-specific from `<repo>/.merge-guard.json` (protected files, post-merge and generator commands, generated-code globs, parallel modules, required build targets, lint and test commands). When a project needs something new, add it there, not in the scripts.

**Shell safety (zsh):** write git object paths as `"${REF}:path/to/file"` — in zsh `$REF:A…`, `:h`, `:t`, `:r`, `:e` are path modifiers and silently turn the argument into a different path.

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

Put the `WARN` lines into your notes for the report. Act on these preflight lines:
- **`RULES …`** — the repository's own rules for agents and contributors (CLAUDE.md, AGENTS.md, `.cursor/rules`, another merge skill …). **Read them before reviewing anything** and follow them in every decision and port (e.g. "no Apollo types inside the new module", "legacy code stays minimal"). If the repo has its own merge skill, do both: where they differ, the stricter rule wins; tell the developer.
- **Installed skill copy differs** — agents in that repo run older rules. Tell the developer to re-run `install.sh` (and commit it if the team shares it).
- **Other worktrees / stashes** — work there is not part of the merge; list it. The target branch checked out in another worktree is a `BLOCK`.
- **Commit hooks** — tell the developer they will run on their commit; `verify_commit.py` checks afterwards that they didn't change the merged content.
- **Case-only paths** — a case-insensitive disk keeps one of them; never "fix" by deleting one without asking.

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

Then, and after **every** re-run of `collect_changes.py`:
```bash
python3 "$SKILL_DIR/scripts/classify_items.py" ~/Downloads/merge-reports/<REPORT_ID>/analysis.json
```
- **IB_METADATA:** XIB/storyboard hunks whose only change is the client module name (with `customModuleProvider="target"`) or the Interface Builder tool version are decided "keep target" by rule, so sibling hunks are handled the same way.
- **Look-alikes (parallel implementations):** the structure can be "same" while target rebuilt a screen or service in a new module (ViewliftOne: `AppCMS/ViewliftOne/…/VLOneMonetizationBadgeView.swift` next to legacy `VLMonetizationBadgeView.swift`). Items whose file has a same-named counterpart there get `counterparts` (with the identifiers the counterpart does / doesn't use). Set the modules in `.merge-guard.json` → `"parallel_modules": ["AppCMS/ViewliftOne/"]`; otherwise they are detected.

Then the repository-wide scan (after every re-run too):
```bash
python3 "$SKILL_DIR/scripts/risk_scan.py" ~/Downloads/merge-reports/<REPORT_ID>/analysis.json
```
It writes `repo_risks` (top of report.html) and flags items. Handle each code (details: reference.md → "Repository risks"):
- `REVERT_REINTRODUCED` — target reverted a change on purpose and source still carries it: the item escalates; show the revert commit.
- `SECRET` — source adds something that looks like a credential: escalates; never merge it without the owner's OK.
- `GENERATED` — generated code is kept as target; run the generator after the merge (`regenerate` in `.merge-guard.json`).
- `APP_SCHEMES` — app/extension targets without a shared scheme: build them explicitly (`--require-target`), and tell the developer.
- `BUILD_SETTINGS`, `DEPENDENCIES`, `CORE_DATA`, `UTF16_STRINGS`, `CASE`, `MERGE_BASES`, `DUPLICATE_SUBJECTS`, `TOOLING` — review and mention in the summary; ask only where a decision is needed.
"Needs action" risks go into the one question message with the escalations.

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

**Many items?** If your editor can run sub-agents (Cursor Task, Claude Code agents …), split the review into batches by module/file and give each reviewer this checklist, the item ids and `analysis.json`.

**Results enter analysis.json only through `apply_review.py`** (never by editing the AI fields by hand):
```bash
python3 "$SKILL_DIR/scripts/apply_review.py" <report>/analysis.json <report>/review-queue/batch_*.results.json --by <reviewer>
```
It keeps every version in `ai_history`. **Never raise a confidence, drop `escalate`, or change CUSTOM to an option to get past the threshold.** If new evidence really settles an earlier doubt, give `change_reason` (what you found that the first review didn't have) and a real independent check by a separate reviewer; otherwise `auto_decide.py` escalates the item. Direct edits are detected and recorded as "edited directly".

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
   - `external_dependency`: the exact question, whenever the proposal relies on something outside the repo (new or changed field in a backend request, a server schema, another package's API). Code that only *compiles* doesn't prove the server accepts it.
7. For `NEW_FILE` and `NEW_SYMBOL`: confirm the folder/file, the build targets (Xcode `pbx_targets.py`, SPM target, Gradle module …), imports and access levels.
8. When you name developers, use only `source_authors` / `target_authors`. They're line-exact; if a list is empty, say the exact author wasn't found.
9. Check `CLEAN` items for dependencies on something target removed or renamed, and upgrade those to decision items.
10. **Dependencies between items:** when a decision relies on another item ("pairs with M-0333", "the helper arrives with CLEAN M-0345", "follows M-0132"), list them in `depends_on`. Verify that the other item really supplies what you rely on (the function / property exists in its source lines and that item is not decided TARGET). An item that depends on an escalated item is escalated with it.
11. **Look-alikes (`counterparts`):** open each counterpart and decide whether the source change (business rule, CMS key, API argument) must also be ported there. Set `counterpart_verdict`: `port` (and say where in `counterpart_note`) or `not-needed` (why, e.g. "ViewliftOne screen reads the same key via MonetizationBadgeParser"). Do this for CLEAN items too.
12. **Review items (NEAR_CHANGE, PROJECT_FILE, NEW_FILE …) are decisions too.** If your recommendation is not "take source", `auto_decide.py` records it as the item's decision and the merge must follow it. "Accept the git auto-merge" is `SOURCE`, not `BOTH`.

### 1.35 Independent check (fresh eyes)
Every `high`-severity item, and every item whose choice drops source code or behaviour, gets a second review.
- **With sub-agents:** run a **separate** checker. Give it the item, the code access and the checklist, but not your conclusion. Then compare its answer with yours.
- **Without sub-agents:** do a deliberate second pass yourself: re-read the three versions and the callers from scratch, and try to prove the opposite decision.

Record `check_verdict` (`agree` / `disagree`), `check_by` (who checked: the sub-agent's name, or `second pass`) and `check_note` — **what the checker verified and how it tried to prove the opposite**, in a real sentence. "Agrees.", "Adopted agent recommendation", "Second pass settled X" are rejected as boilerplate. A disagreement is escalated, never averaged.

### 1.4 Decide, render, continue
```bash
python3 "$SKILL_DIR/scripts/auto_decide.py" ~/Downloads/merge-reports/<REPORT_ID>/analysis.json   # --threshold from .merge-guard.json (default 0.8)
python3 "$SKILL_DIR/scripts/render_report.py" ~/Downloads/merge-reports/<REPORT_ID>/analysis.json
```
- `auto_decide.py` sets `decision` + `decided_by: "ai"` on everything you proved — needs-decision **and** reviewed Review items — and lists:
  - **RECHECK (exit 3) — your work, not the developer's:** a missing or boilerplate independent check on a high-severity / code-dropping / rewriting choice, or a look-alike without `counterpart_verdict`. Fix them (apply_review.py) and re-run. If a separate check is truly impossible, escalate the item instead.
  - **Escalations (exit 2):** the hard rules, plus "an earlier doubt was cleared without change_reason" and "depends on an escalated item".
- **Escalations:** ask the developer **once**, in one compact table: `ID | file → function | what source does | what target does | your lean + why | the question`. Mention that the full cards are in `report.html` → "Needs you". Record each answer as that item's `decision` with `decided_by: "developer"` and quote their words in `decision_notes`. A name, "ok" or "proceed" is not an answer to a specific question; ask again. Re-run `auto_decide.py` and continue.
- **No escalations:** tell the developer in 2–3 lines where the report is, how many items the AI decided and how many were auto-merged, and that you're **continuing with the merge now**. Don't wait.
- **Review mode** only: stop here and wait for `Resume merge report <REPORT_ID>`. Tell the developers how to use the page: share the **Who needs to talk to whom** table in Slack (Copy as text / Copy as image) so each developer pair meets on its blocking cards first, filter by their name, pick / comment / tick **Mark reviewed** on their cards, keep progress with **Auto-save to file…** (Chrome/Edge) or **Export decisions**, and that the merge owner can **Import** everyone's files and watch the **Ready to merge** chip. Details: reference.md → "Developer review page".
- Only `render_report.py` writes `report.html`. Never hand-edit or regenerate the page in another way; improvements go into the script so every report gets them. Re-rendering a report keeps developers' browser progress (it is keyed by the Report ID), but new cards start as pending.

## Phase 2 — Merge (never commit)
Runs straight after Phase 1 in autonomous mode, or on "Resume merge report <ID>" in review mode / a new chat.

### 2.1 Reload and re-check
1. Load `~/Downloads/merge-reports/<ID>/analysis.json`. Ask for the path if it isn't there.
2. If the developer exported decisions or edited `report.md` (overrides, or review mode), run `python3 "$SKILL_DIR/scripts/parse_decisions.py" <analysis.json>`. It reads every `decisions-*.json` in the report folder (one per developer, the merge owner's combined export, or the auto-save file). Exit code 2 lists items still open (`MISSING` / `AMBIGUOUS` / `CUSTOM-WITHOUT-NOTES` / `CONFLICT`). Ask about only those, in one message; for a `CONFLICT` name each reviewer and their option and ask which one is final.
   - If the file's `readiness` says `BLOCKED`, say so and list the blockers before merging.
   - A pre-selected AI option the developer never touched is **not** a developer decision; `reviewed_by` shows who actually reviewed each card.
   - A developer decision must be explicit for that item: a name, "ok" or "proceed" doesn't answer a specific question.
   - AI decisions (`decided_by: "ai"`) stand unless the developer overrides them.
   - **Overrides that would break things:** a developer may pick "Replace with source code as-is" (`SOURCE`) on code target refactored or optimised, or a choice that breaks another decided item (a changed signature, a removed type). Before applying it, show in one table what the literal choice removes or breaks. Offer the **behaviour-preserving reading** (source's business rule kept inside target's code), and ask once: behaviour-preserving (recommended) or literal. Don't apply either reading silently.
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
| `NEAR_CHANGE` / auto-merged | Follow the item's decision when it has one: `TARGET` → keep target's lines for this hunk, `AI`/`BOTH` → apply `proposed_code`. Without a decision, re-read the whole function; a textual merge can still be wrong logic. |
| `IB_METADATA` | Keep target's metadata lines (module name / tool version) for this hunk; take every other change in the file. |
| Item with `counterpart_verdict: port` | Apply the item as decided **and** port the same business rule into the counterpart file named in `counterpart_note`. Record it in `final_path` notes. |
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
Run the `post_merge` commands (from `project_profile.py` / `.merge-guard.json`) **through the runner**, which records exactly which files each command changed:
```bash
python3 "$SKILL_DIR/scripts/run_post_merge.py" ~/Downloads/merge-reports/<ID>/analysis.json --tree <target_folder>
# or explicitly: --cmd "cd AppCMS && bash setup_environment.sh motv stage"
```
- Environment scripts often rewrite tracked files (project file, Pods, plists, generated code) and may live in a sub-folder; ask for their arguments (client, environment) if the profile says so.
- Exit 1 = a command failed: fix the cause from its output if you can; otherwise show it and ask.
- Exit 2 = a command changed **merged files**: re-run `verify_coverage.py`, and ask whether those edits belong in the merge commit.
- If the profile notes that `.merge-guard.json` empties a detected step (`"post_merge": []`), confirm with the developer that skipping it is intended.
- Then run the generators for `GENERATED` items (`regenerate`), and lockfile regeneration.

### 2.6 Resolve packages, build every target, fix compilation
**Never run builds in parallel or in the background.** Parallel `xcodebuild` runs into one DerivedData fail with `database is locked` / `has been modified since the module file was built`. Those are false failures that hide the real result.

**Xcode projects:** use the build script. It resolves Swift packages once, builds every scheme one at a time in its own DerivedData, retries an environment failure once (clean build), and separates real code errors from environment errors:
```bash
python3 "$SKILL_DIR/scripts/build_xcode.py" --repo <target_folder> --out ~/Downloads/merge-reports/<ID>
# editor limits command time? call it once per scheme: … --scheme VLPlayerLib, then --scheme VLPlayerLib_tvOS, …
```
- Every **application / app-extension target must be built** — the script finds them in the project and fails with `MISSING_SCHEME` when no listed scheme builds one (schemes that exist only in a user's `xcuserdata` don't exist on CI). Pass `--require-target` / `--scheme` or set `required_targets` in `.merge-guard.json`.
- Packages are built **only at the revisions in `Package.resolved`** (branch-pinned packages would otherwise pull new remote commits mid-merge). Use `--allow-package-updates` only when the developer wants packages updated.

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
6. **Lint and tests:** run the profile's `lint` on the merged files (CI and commit hooks reject violations) and its `test` commands for the modules the merge touched. Report failures with the first error; fix only what the merge caused.
6. **Hand-over gate:** don't say the merge "compiles" or "is done" until the **last** sequential run shows every scheme `SUCCEEDED`. Put the per-scheme table in your reply. If something still fails or couldn't be built here, say so plainly, with the scheme and first error.
7. If the toolchain isn't available here, give the exact commands, ask the developer to run them, and fix from the errors they paste.

### 2.7 Hand over — the developer commits
Only after the hand-over gate in 2.6 has passed (or the developer has accepted the listed failures):
```bash
python3 "$SKILL_DIR/scripts/commit_message.py" ~/Downloads/merge-reports/<ID>/analysis.json --tree <target_folder> \
  --build "<scheme ✔/✘ list from build-summary.md>" --post-merge "<post-merge commands ✔>"
```
This writes `COMMIT_MSG.txt`. **Exit 4 = no merge in progress** (`MERGE_HEAD` missing, e.g. after `git merge --quit`, a stash or a reset): a commit now would be a plain commit and git would forget the source branch was merged, so the next merge shows the same changes again. Don't hand over until it's fixed: restart the merge record (`git merge --no-commit -s ours <source.ref>` needs a clean index, so explain the options to the developer), or tell them to record it right after their commit with `git merge -s ours <source>`.
After the developer commits, check `git merge-base --is-ancestor <source.head> HEAD`; if it fails, tell them the merge wasn't recorded.

The file contains:
- subject line;
- merge summary: report ID, editor and session, who decided, coverage and build results;
- **`developer -- file -- merged line numbers -- item/decision -- developer notes`**, grouped by developer;
- changes intentionally not merged, with who decided and why.

**Final summary to the developer** (one message):
- build table: every scheme `SUCCEEDED`;
- coverage result;
- counts: decided by AI / by developer / auto-merged;
- the AI decisions that dropped or rewrote source code, one line each with the evidence, so they can spot-check;
- look-alike verdicts (`port` / `not-needed`) and any earlier doubts that were cleared, with the reason;
- when items still need people: the top developer pairs from report.html's "Who needs to talk to whom" table (pair → blocking card IDs);
- files changed by post-merge steps;
- the report path.

Then show the full commit message and the command they can run **themselves**: `git commit -F <report>/COMMIT_MSG.txt`. Edit the message if they ask. **Do not commit, continue the merge, or push — not even if asked to "finish it"; explain that this skill leaves commits and pushes to them.**

After the developer commits, run:
```bash
python3 "$SKILL_DIR/scripts/verify_commit.py" ~/Downloads/merge-reports/<ID>/analysis.json --tree <target_folder>
```
It checks the source is now an ancestor (merge recorded), that a merge commit brought it in, and that the committed tree equals the hand-over (commit hooks or formatters didn't change merged files). After the PR lands, run it again with `--ref origin/<target_branch>`: it lists merged files that changed afterwards.

Then:
- Write `merge-result.md` in the report folder: verification summary, build summary, items handled differently from the report and why.
- Set `status` to `MERGED_UNCOMMITTED` in analysis.json.
- Tell them how to undo before committing: `git merge --abort`, or `git reset --hard merge-guard/backup/<ID>` (their call; you don't run either).
