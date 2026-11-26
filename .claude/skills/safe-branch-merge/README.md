# safe-branch-merge

A skill and a rule for merging one branch into another, in **any project** (iOS/tvOS, Android, web, backend) and **any AI code editor** (Claude Code, Claude desktop, Cursor, Windsurf, Copilot, Codex …), without losing code.

How it works (autonomous by default):
1. The AI analyses both branches, builds a file/function map, and reviews every change from the code logic, with an independent second check.
2. It decides what it can prove and asks the developer once, only about what it can't (business choices, unproven removals, low confidence).
3. It merges or ports without committing, checks that no code was lost, and builds every target sequentially.
4. It hands over a commit message plus a full report. **It never commits or pushes.** Say "review mode" to get the report first and decide everything yourself.

```
safe-branch-merge/
  SKILL.md                 workflow: phase 1 report → phase 2 resume, merge, verify, build, commit message
  safe-branch-merge.mdc    guardrail rule (Cursor format; plain Markdown below the front matter for any tool)
  reference.md             categories, decisions, edge cases, project profiles, .merge-guard.json, editors
  install.sh               installs skill + rule into a project (or globally) for every editor
  scripts/
    preflight.sh           branches, local changes, behind origin, in-progress operations (read-only)
    project_profile.py     detects the stack → protected files, post-merge steps, build commands
    collect_changes.py     compares branches, maps moved files, compares by function when restructured, developer/date per change
    propose_file_map.py    drafts the file map (moved / split / new files, per-function homes, folder + Xcode/SPM targets) for the AI to decide
    symbols.py             function/type index for Swift, Obj-C, Kotlin, Java, JS/TS, C#, Go (used by the two above)
    classify_items.py      rule-based pass: IB metadata-only XIB hunks; look-alikes in parallel modules (e.g. ViewliftOne)
    risk_scan.py           repository-wide risks: reverts re-introduced, secrets, generated code, case collisions,
                           build-setting drift, branch-pinned packages, app targets without shared schemes, Core Data, UTF-16 strings
    run_post_merge.py      runs post-merge/setup commands and records which (merged) files each one changed
    verify_commit.py       after the developer's commit / after the PR lands: merge recorded, content = hand-over
    apply_review.py        merges AI review results into analysis.json and keeps every version (ai_history)
    quality_scan.py        quality.json: file risk scores, platform (#if os) context, test hints, new SwiftLint warnings
                           on merged lines, dependency pin diff (read-only; --periphery for unused code)
    report_server.py       opens a report with ✦ Ask AI: the local Cursor agent (read-only) answers questions per card
    render_index.py        ~/Downloads/merge-reports/index.html: every report with status, verification, build, hotspots
    render_report.py       analysis.json → report.html (review tracker, ready-to-merge gate, developer filter,
                           who-talks-to-whom pairs with Slack copy as text / image, multi-file import, auto-save,
                           4-way diff with result preview, "why the AI chose this" + evidence links, feature areas,
                           keyboard review, quality & risk, deep links, minimap, dark mode, print layout, history/hotspots,
                           changed-since tags, callers, behaviour checklists, QA plan, commit preview, search,
                           inline diff, assign) + report.md
    auto_decide.py         applies AI decisions (confidence + evidence + real independent check + history), lists RECHECK and escalations
    parse_decisions.py     loads developer decisions/overrides (one or many exported JSON files, or ticked report.md); flags reviewer disagreements
    verify_coverage.py     proves every source line is merged, moved, or explicitly dropped
    build_xcode.py         resolves Swift packages, builds every scheme sequentially, honest per-scheme summary
    commit_message.py      COMMIT_MSG.txt: developer -- file -- line numbers -- decision -- notes
    pbx_targets.py         which Xcode targets contain a file; --duplicates finds double build-file entries
    add_to_targets.rb      add a file to Xcode groups/targets (macOS, `gem install xcodeproj`)
```

## Install
In Terminal, type `bash ` and drag `install.sh` in, then type a space, drag your project folder in, and press Enter:
```bash
bash ~/Documents/Viewlift/Skills/safe-branch-merge/install.sh ~/path/to/repo
```
- **From inside the project:** `cd` into the project (any subfolder) and run `bash <path>/install.sh`, or copy the `safe-branch-merge` folder into the project and run `bash safe-branch-merge/install.sh`. It detects the project and asks `Install into <repo>? [Y/n]`.
- Run it with no path from anywhere else and it asks you to drag the folder in.
- Any folder or file inside the project works (for example a dragged `.xcodeproj`); it finds the git repo root itself.
- It installs for all editors and creates `.merge-guard.json` from the detected stack if the project doesn't have one yet.

Options: `--tools claude,cursor` (only those editors), `--no-config` (skip `.merge-guard.json`), `--global` (all projects, Claude Code).
The installer writes files but commits nothing. Commit them yourself if the team should share them.

Requirements: `git`, `bash`, `python3` ≥ 3.8. The project's own toolchain is needed for the build step (e.g. Xcode, Gradle, Node).

## Use
1. Say "Merge Develop into Develop_Analytics with safe-branch-merge" and give both branches and folders. That's it.
2. The agent works through everything. It messages you only if something needs a human: one compact list of questions. Answer those.
3. At the end you get the build table, the coverage result, a list of the AI decisions that dropped or rewrote code (with evidence), the report (`~/Downloads/merge-reports/MRG-…/report.html`), and `COMMIT_MSG.txt`.
4. Spot-check, override anything you disagree with (tell the agent, or use the report), then run `git commit -F …/COMMIT_MSG.txt` and `git push` yourself.

### Reviewing with your team (report.html)
- **Who still has to look:** each card shows ⏳ Pending or ✓ Reviewed (selected / commented / confirmed). The **Tracker** panel and the top bar count reviewed vs pending, per section and per developer. A pre-selected AI option alone does not count as reviewed; tick **Mark reviewed** to agree with it.
- **Per developer:** pick a name in **Developer** to see only their cards; **Pending list** gives a ready-to-paste list grouped by developer.
- **Who needs to talk to whom:** a table of developer pairs (incoming-code author ↔ current-code author) with the cards they must resolve together, blocking ones first. **Copy as text** gives a Slack-formatted message; **Copy as image** puts a PNG of the table on the clipboard (or downloads it) to paste into Slack.
- **Ready to merge:** the chip turns green when every "Needs you" card has an option, no Custom choice is missing a note, and no reviewers disagree.
- **Collect everyone's input:** each developer clicks **Export decisions**; the merge owner clicks **Import decisions** and picks all files at once. Disagreements are flagged in red until settled. Export again to get one combined file for the agent.
- **Start at the top:** the **Start here** box says in one line whether the merge is ready (decisions, build, verification, lint) and gives **Your next step** with a *Go →* button.
- **Cards stay short:** each shows what the AI suggests, how sure it is, up to three status chips and your options. **Show details** (`o`) opens the code and evidence. Red = blocks the merge, amber = needs a look, green = done, grey = info.
- **Review fast:** press `?` for keys — `j`/`k` move between cards, `s`/`t`/`b`/`a`/`c` pick an option, `Enter` accepts the ★ recommendation, `r` marks reviewed. The **Result** column shows what the file will contain for your choice; **Why the AI chose this** links to the exact evidence lines.
- **Spot the risky parts:** **Quality & risk** ranks files by risk and lists new SwiftLint warnings on merged lines, tests that cover the change and dependency pin changes. Cards show chips (`File risk 68`, `no tests`, `#if os(tvOS)`). **Feature areas** lets you review one area at a time.
- **Test it:** every card has a **behaviour checklist**; the **QA test plan** collects them by area (Copy / Download .md). **Who calls this** shows how far a change reaches.
- **Come back later:** cards changed since you last opened the report (or since the last render) are tagged; **Show only these** jumps straight to them. **History** shows files that conflicted in earlier merges; **All reports** opens the index of every merge.
- **Split the work:** `/` searches, **Assign me** (`m`) claims a card, **Assigned: me** shows your list. **Diff: inline** (`i`) and **Base: hidden** change the code view. The **Commit message preview** follows your choices live.
- **Ask AI:** log in once with `cursor-agent login`, then open the report with `python3 <skill>/scripts/report_server.py ~/Downloads/merge-reports/<ID> --open`. A **✦ Ask AI** bubble (bottom right) and a button on every card let you ask the Cursor agent about any conflict (read-only; it never edits code). Answers link to the file in Cursor, can go into the card's notes, and continue in the terminal. Without a login the feature is hidden; ⋯ → *Turn on AI help…* shows how.
- **Your name is required:** open the report with `report_server.py` and your reviewer name comes from `git config user.name` (read-only). Opened as a file, the page asks once for your full name and locks it. Nothing can be decided or exported until a reviewer is set.
- **Jump to a commit:** every commit id (author lines, commit list, AI text and answers) opens that commit on GitHub / GitLab / Bitbucket / Azure DevOps in a new tab. Commits that aren't pushed yet are shown without a link.
- **On a phone or tablet:** the same report works on a phone or tablet. The bar is compact, code shows as tabs (Base / Incoming / Current), options are full-width, and ⋯ holds your name and settings.
- **Share a card:** click its ID to copy a link like `report.html#M-0005`. ◐ switches dark mode; **Print / PDF** gives a clean printed report.
- **Nothing gets lost:** progress is saved in the browser automatically. In Chrome/Edge, click **Auto-save to file…** once and save `decisions-<ID>.json` in the report folder. Every change is then also written to that file and restored from it on reopen.
