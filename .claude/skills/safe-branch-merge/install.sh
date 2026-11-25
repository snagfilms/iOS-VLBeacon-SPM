#!/usr/bin/env bash
# install.sh — install the safe-branch-merge skill + rule for any project and any AI code editor.
#
#   bash install.sh /path/to/repo            # simplest: type "bash install.sh " and drag the project folder in
#   bash install.sh                          # from inside a project (or with install.sh copied into it): uses that
#                                            # project after a Y/n check; otherwise asks you to drag the folder in
#   bash install.sh /path/to/repo --tools claude,cursor     # only some editors
#   bash install.sh /path/to/repo --no-config              # don't create .merge-guard.json
#   bash install.sh --global                 # all projects (Claude Code; other editors get instructions)
#
# The path may be any folder or file inside the project (e.g. a dragged .xcodeproj); the git repo root is used.
# What it writes (only for the tools you pick; default = all):
#   claude   <repo>/.claude/skills/safe-branch-merge/   (full skill; Claude Code discovers it)
#            + a short pointer block in <repo>/CLAUDE.md
#   cursor   <repo>/.cursor/rules/safe-branch-merge.mdc  (rule, points at the skill folder)
#   windsurf <repo>/.windsurf/rules/safe-branch-merge.md
#   copilot  <repo>/.github/instructions/safe-branch-merge.instructions.md
#   agents   a block in <repo>/AGENTS.md (read by Codex, Cursor, Jules, Aider, Zed and other agents)
#   config   <repo>/.merge-guard.json from the detected project profile — only if it doesn't exist yet
#
# The full skill is copied once; every other tool gets a rule file pointing at it. Re-running updates in place.
# Nothing is committed — commit the files yourself if the team should share them.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NAME="safe-branch-merge"
MODE=""; DEST=""; TOOLS="all"; INIT_CFG=1; RAW_PATH=""
usage() { sed -n '2,23p' "$0"; }

repo_root() {  # print the project root containing $1 (git first, then walk up for .git); fail if none
  local d="$1" r
  if r="$(git -C "$d" rev-parse --show-toplevel 2>/dev/null)" && [ -n "$r" ]; then printf '%s' "$r"; return 0; fi
  d="$(cd "$d" 2>/dev/null && pwd -P)" || return 1
  while [ -n "$d" ] && [ "$d" != "/" ]; do
    if [ -e "$d/.git" ]; then printf '%s' "$d"; return 0; fi
    d="$(dirname "$d")"
  done
  return 1
}

clean_path() {  # undo what drag-and-drop / copy-paste adds: quotes, backslash escapes, file://, spaces, ~
  local p="$1"
  p="${p#"${p%%[![:space:]]*}"}"; p="${p%"${p##*[![:space:]]}"}"
  p="${p#file://}"
  if [[ "$p" == \'*\' || "$p" == \"*\" ]]; then p="${p:1:${#p}-2}"; fi
  p="$(printf '%s' "$p" | sed 's/\\\(.\)/\1/g')"
  p="${p//%20/ }"
  [[ "$p" == "~"* ]] && p="$HOME${p:1}"
  printf '%s' "$p"
}

while [ $# -gt 0 ]; do
  case "$1" in
    --project) MODE=project; RAW_PATH="${2:-}"; shift 2;;
    --global)  MODE=global; DEST="$HOME"; shift;;
    --tools)   TOOLS="$2"; shift 2;;
    --init-config) INIT_CFG=1; shift;;          # kept for old instructions; now the default
    --no-config) INIT_CFG=0; shift;;
    -h|--help) usage; exit 0;;
    -*) echo "unknown option: $1"; usage; exit 1;;
    *) MODE=project; RAW_PATH="${RAW_PATH:+$RAW_PATH }$1"; shift;;   # tolerate an unquoted path with spaces
  esac
done

if [ "$MODE" != global ]; then
  MODE=project
  if [ -z "$RAW_PATH" ]; then
    # No path given: use the project we are being run from.
    #  1) the current folder, if it is inside a git repo (and not inside this skill folder itself)
    #  2) the repo that contains this install.sh (e.g. <repo>/.claude/skills/safe-branch-merge/install.sh
    #     or a copy dropped into <repo>/safe-branch-merge/)
    HERE_P="$(cd "$HERE" && pwd -P)"; CWD_P="$(pwd -P)"
    GUESS=""
    if [[ "$CWD_P/" != "$HERE_P/"* ]] && CR="$(repo_root "$CWD_P")"; then
      GUESS="$CR"
    elif HR="$(repo_root "$HERE_P")" && [ "$(cd "$HR" && pwd -P)" != "$HERE_P" ]; then
      # but not when this folder sits in a skills library (sibling folders with their own SKILL.md)
      SIBLINGS=$(find "$(dirname "$HERE_P")" -mindepth 2 -maxdepth 2 -name SKILL.md ! -path "$HERE_P/*" 2>/dev/null | wc -l | tr -d ' ')
      case "$HERE_P" in */.claude/skills/*|*/.ai-skills/*) SIBLINGS=0;; esac
      [ "$SIBLINGS" -eq 0 ] && GUESS="$HR"
    fi
    if [ -n "$GUESS" ]; then
      if [ -t 0 ]; then
        printf 'Install into %s ? [Y/n] ' "$GUESS"; IFS= read -r ANS
        case "$ANS" in [nN]*) GUESS="";; esac
      else
        echo "no path given — using $GUESS"
      fi
    fi
    if [ -n "$GUESS" ]; then
      RAW_PATH="$GUESS"
    elif [ -t 0 ]; then
      echo "Current folder $(pwd) is not inside a git project."
      for _ in 1 2 3; do
        printf 'Drag the project folder here (or paste its path) and press Enter: '
        IFS= read -r RAW_PATH || true
        [ -n "$(clean_path "$RAW_PATH")" ] && break
        echo "Nothing entered — drag the folder from Finder into this window, then press Enter (Ctrl+C to cancel)."
      done
      [ -n "$(clean_path "$RAW_PATH")" ] || { echo "No project folder given."; exit 1; }
    else
      usage; exit 1
    fi
  fi
  P="$(clean_path "$RAW_PATH")"
  [ -e "$P" ] || { echo "Path not found: $P"; exit 1; }
  [ -d "$P" ] || P="$(dirname "$P")"                     # a dragged file → its folder
  if ROOT="$(repo_root "$P")"; then
    DEST="$ROOT"
    [ "$(cd "$P" && pwd -P)" != "$(cd "$ROOT" && pwd -P)" ] && echo "using git repo root: $DEST"
  else
    DEST="$(cd "$P" && pwd)"
    echo "note: $DEST is not a git repository — installing there anyway"
  fi
  echo "project: $DEST"
fi
[ "$TOOLS" = "all" ] && TOOLS="claude,cursor,windsurf,copilot,agents"
has() { [[ ",$TOOLS," == *",$1,"* ]]; }

# one canonical copy: reuse an existing install, else .claude/skills when Claude Code is selected, else .ai-skills
if [ -f "$DEST/.claude/skills/$NAME/SKILL.md" ] || has claude; then SKILL_DIR="$DEST/.claude/skills/$NAME"
else SKILL_DIR="$DEST/.ai-skills/$NAME"; fi
mkdir -p "$SKILL_DIR"
if [ "$(cd "$HERE" && pwd -P)" != "$(cd "$SKILL_DIR" && pwd -P)" ]; then
  (cd "$HERE" && tar cf - --exclude='__pycache__' --exclude='.DS_Store' .) | (cd "$SKILL_DIR" && tar xf -)
fi
chmod +x "$SKILL_DIR"/scripts/* "$SKILL_DIR"/install.sh 2>/dev/null || true
echo "skill:   $SKILL_DIR"

if [ "$MODE" = project ]; then REL="${SKILL_DIR#$DEST/}"; else REL="$SKILL_DIR"; fi
RULE_BODY="$(awk 'BEGIN{f=0} /^---$/{f++; next} f>=2' "$HERE/$NAME.mdc")"
DESC="$(awk -F': ' '/^description:/{sub(/^description: /,""); print; exit}' "$HERE/$NAME.mdc")"
POINTER="Skill folder: \`$REL\` — read \`$REL/SKILL.md\` before any branch merge; scripts are in \`$REL/scripts/\`."

write_block() { # file, content — replace/append between markers
  local f="$1" content="$2" tmp
  mkdir -p "$(dirname "$f")"; touch "$f"; tmp="$(mktemp)"
  awk -v s="<!-- $NAME:start -->" -v e="<!-- $NAME:end -->" '$0==s{skip=1} !skip{a[++n]=$0; if(NF)last=n} $0==e{skip=0} END{for(i=1;i<=last;i++)print a[i]}' "$f" > "$tmp"
  { cat "$tmp"; [ -s "$tmp" ] && echo; echo "<!-- $NAME:start -->"; printf '%s\n' "$content"; echo "<!-- $NAME:end -->"; } > "$f"
  rm -f "$tmp"; echo "updated: $f"
}

if has claude; then
  if [ "$MODE" = project ]; then F="$DEST/CLAUDE.md"; else F="$HOME/.claude/CLAUDE.md"; fi
  write_block "$F" "## Branch merges
For any branch merge / port / conflict resolution use the \`$NAME\` skill and follow its rule \`$REL/$NAME.mdc\`.
Never run git commit or git push — leave both to the developer."
fi
if [ "$MODE" = project ]; then
  if has cursor; then
    F="$DEST/.cursor/rules/$NAME.mdc"; mkdir -p "$(dirname "$F")"
    { echo "---"; echo "description: $DESC"; echo "globs:"; echo "alwaysApply: false"; echo "---"; echo; echo "$POINTER"; echo; printf '%s\n' "$RULE_BODY"; } > "$F"
    echo "written: $F"
  fi
  if has windsurf; then
    F="$DEST/.windsurf/rules/$NAME.md"; mkdir -p "$(dirname "$F")"
    { echo "---"; echo "trigger: model_decision"; echo "description: $DESC"; echo "---"; echo; echo "$POINTER"; echo; printf '%s\n' "$RULE_BODY"; } > "$F"
    echo "written: $F"
  fi
  if has copilot; then
    F="$DEST/.github/instructions/$NAME.instructions.md"; mkdir -p "$(dirname "$F")"
    { echo "---"; echo "applyTo: \"**\""; echo "---"; echo; echo "$POINTER"; echo; printf '%s\n' "$RULE_BODY"; } > "$F"
    echo "written: $F"
  fi
  if has agents; then
    write_block "$DEST/AGENTS.md" "## Branch merges (safe-branch-merge)
$POINTER
Key rules: never lose source code silently; report before merging (\`~/Downloads/merge-reports/\`); ask when unsure with developer name, date and snippets; never run git commit or git push."
  fi
  if [ $INIT_CFG -eq 1 ]; then
    if [ -f "$DEST/.merge-guard.json" ]; then echo "kept existing: $DEST/.merge-guard.json"
    else
      CFG_TMP="$(mktemp)"
      python3 - "$SKILL_DIR/scripts/project_profile.py" "$DEST" > "$CFG_TMP" <<'PY'
import json, subprocess, sys
p = json.loads(subprocess.run([sys.executable, sys.argv[1], sys.argv[2]], capture_output=True, text=True, check=True).stdout)
cfg = {"profile": (p["profiles"] or ["custom"])[0], "mode": "auto", "confidence_threshold": 0.8, "merge_branch": "direct",
       "record_as_merge": True, "protect": p["protect"], "post_merge": p["post_merge"],
       "build": p["build"], "discover": p["discover"], "regenerate": p["regenerate"], "notes": []}
print(json.dumps(cfg, indent=2, ensure_ascii=False))
PY
      mv "$CFG_TMP" "$DEST/.merge-guard.json"
      echo "written: $DEST/.merge-guard.json (review the build commands)"
    fi
  fi
else
  has cursor   && echo "Cursor: global rules live in Cursor's settings (User Rules) — paste the contents of $SKILL_DIR/$NAME.mdc there, or install per project."
  has windsurf && echo "Windsurf: add $SKILL_DIR/$NAME.mdc to your global rules, or install per project."
  has copilot  && echo "Copilot: instructions are per repository — install per project."
fi
echo "done. Nothing was committed."
