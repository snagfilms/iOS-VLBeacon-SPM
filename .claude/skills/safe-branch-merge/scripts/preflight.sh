#!/usr/bin/env bash
# preflight.sh — read-only safety checks before analysing or merging.
#
# Usage:
#   preflight.sh <source_folder> <source_branch> <target_folder> <target_branch> [--no-fetch]
#
# Prints one line per check:  OK | WARN | BLOCK  <message>
# Ends with:  VERDICT: READY   or   VERDICT: NEEDS_ACTION (n blocking)
# Never changes the working tree. Without --no-fetch it runs `git fetch origin <branch>`,
# which only updates remote-tracking refs.

set -u
SRC_DIR="${1:?source folder}"; SRC_BR="${2:?source branch}"
TGT_DIR="${3:?target folder}"; TGT_BR="${4:?target branch}"
NO_FETCH=0; [ "${5:-}" = "--no-fetch" ] && NO_FETCH=1

BLOCKS=0
ok()    { echo "OK    $*"; }
warn()  { echo "WARN  $*"; }
block() { echo "BLOCK $*"; BLOCKS=$((BLOCKS+1)); }

check_folder() {
  local label="$1" dir="$2" br="$3" role="$4"
  echo "== $label: $dir  (expected branch: $br)"
  if [ ! -d "$dir" ]; then block "$label folder does not exist"; return; fi
  if ! git -C "$dir" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    block "$label folder is not a git work tree"; return
  fi
  local top; top=$(git -C "$dir" rev-parse --show-toplevel)
  ok "$label repo root: $top"

  local cur; cur=$(git -C "$dir" symbolic-ref --quiet --short HEAD 2>/dev/null || echo "DETACHED@$(git -C "$dir" rev-parse --short HEAD)")
  if git -C "$dir" show-ref --verify --quiet "refs/heads/$br"; then
    ok "$label branch '$br' exists locally ($(git -C "$dir" rev-parse --short "refs/heads/$br"))"
  else
    block "$label branch '$br' does not exist locally in $dir (checkout or fetch it first)"
  fi
  if [ "$cur" = "$br" ]; then
    ok "$label folder is on '$br'"
  else
    if [ "$role" = "target" ]; then
      block "$label folder is on '$cur', not '$br' — the merge happens here, ask the developer before switching"
    else
      warn "$label folder is on '$cur', not '$br' — analysis reads the '$br' ref, the working tree is not used"
    fi
  fi

  local gd; gd=$(git -C "$dir" rev-parse --git-dir)
  case "$gd" in /*) ;; *) gd="$dir/$gd";; esac
  for f in MERGE_HEAD CHERRY_PICK_HEAD REVERT_HEAD BISECT_LOG; do
    [ -e "$gd/$f" ] && block "$label has an operation in progress ($f) — finish or abort it first"
  done
  { [ -d "$gd/rebase-merge" ] || [ -d "$gd/rebase-apply" ]; } && block "$label has a rebase in progress"

  local all dirty own
  all=$(git -C "$dir" status --porcelain=v1 --untracked-files=all 2>/dev/null)
  # files the safe-branch-merge installer created are not "local work": never block on them,
  # never ask to stash or commit them (the developer commits them whenever they like)
  local OWN_RE='^\?\? (\.claude/skills/safe-branch-merge/|\.ai-skills/safe-branch-merge/|\.cursor/rules/safe-branch-merge\.mdc|\.windsurf/rules/safe-branch-merge\.md|\.github/instructions/safe-branch-merge\.instructions\.md|\.merge-guard\.json|\.merge-guard-build/|AGENTS\.md$|CLAUDE\.md$)'
  own=$(printf '%s\n' "$all" | grep -E "$OWN_RE" || true)
  dirty=$(printf '%s\n' "$all" | grep -vE "$OWN_RE" | sed '/^$/d' || true)
  if [ -n "$own" ]; then
    echo "INFO  $label has $(printf '%s\n' "$own" | wc -l | tr -d ' ') untracked file(s) installed by safe-branch-merge — ignored (not stashed, not committed; git merge leaves untracked files alone)"
  fi
  local inst; inst=$(printf '%s\n' "$all" | grep -E '^ M (AGENTS\.md|CLAUDE\.md)$' || true)
  if [ -n "$inst" ] && [ "$(printf '%s\n' "$all" | sed '/^$/d' | grep -vE "$OWN_RE" | grep -vE '^ M (AGENTS\.md|CLAUDE\.md)$' | wc -l | tr -d ' ')" = "0" ]; then
    warn "$label: only AGENTS.md/CLAUDE.md were changed (installer pointer block). They block the merge only if the source branch also changes them — if git refuses, ask the developer to commit or stash just those files themselves."
    dirty=""
  fi
  if [ -n "$dirty" ]; then
    local n; n=$(printf '%s\n' "$dirty" | wc -l | tr -d ' ')
    if [ "$role" = "target" ]; then
      block "$label has $n local change(s). Ask the developer to commit or stash them THEMSELVES (never offer to commit). Stash command if they want it: git -C \"$dir\" stash push -u -m \"pre-merge $(date +%Y%m%d-%H%M)\""
    else
      warn "$label has $n local change(s) — they are NOT part of the analysis (only committed '$br' is read). Ask whether they should be committed first."
    fi
    printf '%s\n' "$dirty" | head -15 | sed 's/^/        /'
    [ "$n" -gt 15 ] && echo "        ... ($n total)"
  else
    ok "$label working tree is clean"
  fi
  local stashes; stashes=$(git -C "$dir" stash list 2>/dev/null | wc -l | tr -d ' ')
  [ "$stashes" -gt 0 ] && warn "$label has $stashes existing stash entr(y/ies) — mention them, never drop them"

  if git -C "$dir" remote get-url origin >/dev/null 2>&1; then
    if [ $NO_FETCH -eq 0 ]; then
      if git -C "$dir" fetch --quiet origin "$br" 2>/dev/null; then ok "$label fetched origin/$br"
      else warn "$label could not fetch origin/$br (offline or branch not on origin)"; fi
    fi
    if git -C "$dir" show-ref --verify --quiet "refs/remotes/origin/$br" && git -C "$dir" show-ref --verify --quiet "refs/heads/$br"; then
      local ab; ab=$(git -C "$dir" rev-list --left-right --count "refs/heads/$br...refs/remotes/origin/$br")
      local ahead=${ab%%[[:space:]]*} behind=${ab##*[[:space:]]}
      if [ "$behind" -gt 0 ]; then
        block "$label local '$br' is $behind commit(s) behind origin — ask the developer to pull before analysing"
      else ok "$label '$br' is up to date with origin"; fi
      [ "$ahead" -gt 0 ] && warn "$label local '$br' has $ahead unpushed commit(s) — they will be included"
    fi
  else
    warn "$label has no 'origin' remote"
  fi

  [ -f "$top/.gitmodules" ] && warn "$label uses submodules — submodule pointer changes must be reviewed by hand"
  grep -qs "filter=lfs" "$top/.gitattributes" && warn "$label uses Git LFS — make sure 'git lfs pull' was run"
  if [ -f "$top/setup_environment.sh" ] || ls "$top"/*/AppCMS.xcodeproj >/dev/null 2>&1 || [ -d "$top/AppCMS.xcodeproj" ]; then
    echo "INFO  $label looks like an AppCMS project (setup_environment.sh / AppCMS.xcodeproj found)"
  fi
}

check_folder "SOURCE" "$SRC_DIR" "$SRC_BR" source
check_folder "TARGET" "$TGT_DIR" "$TGT_BR" target

echo "== Relationship"
if git -C "$SRC_DIR" rev-parse >/dev/null 2>&1 && git -C "$TGT_DIR" rev-parse >/dev/null 2>&1; then
  S_TOP=$(cd "$(git -C "$SRC_DIR" rev-parse --show-toplevel)" && pwd -P)
  T_TOP=$(cd "$(git -C "$TGT_DIR" rev-parse --show-toplevel)" && pwd -P)
  if [ "$S_TOP" = "$T_TOP" ]; then
    ok "Both folders are the same checkout — source is read from the '$SRC_BR' ref, no checkout needed"
  else
    S_ROOTS=$(git -C "$SRC_DIR" rev-list --max-parents=0 "refs/heads/$SRC_BR" 2>/dev/null | sort)
    T_ROOTS=$(git -C "$TGT_DIR" rev-list --max-parents=0 "refs/heads/$TGT_BR" 2>/dev/null | sort)
    if [ -n "$S_ROOTS" ] && [ -n "$(comm -12 <(echo "$S_ROOTS") <(echo "$T_ROOTS"))" ]; then
      ok "Different checkouts of the same repository history (shared root commit)"
    else
      warn "Folders have UNRELATED history — git merge cannot be used. Analysis needs --since <commit|date> on the source branch."
    fi
    S_URL=$(git -C "$SRC_DIR" remote get-url origin 2>/dev/null || echo "-")
    T_URL=$(git -C "$TGT_DIR" remote get-url origin 2>/dev/null || echo "-")
    [ "$S_URL" != "$T_URL" ] && warn "origin URLs differ: source=$S_URL target=$T_URL"
  fi
fi

if [ $BLOCKS -eq 0 ]; then echo "VERDICT: READY"; else echo "VERDICT: NEEDS_ACTION ($BLOCKS blocking)"; fi
exit 0
