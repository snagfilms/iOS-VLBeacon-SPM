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
    render_report.py       analysis.json → report.html + report.md
    auto_decide.py         applies AI decisions (confidence + evidence + independent check), lists escalations
    parse_decisions.py     loads developer decisions/overrides (exported JSON or ticked report.md)
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
