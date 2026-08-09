#!/usr/bin/env bash
# Mirror the built site into a gh-pages worktree.
#
# `--delete` is kept on purpose so that removed build artefacts do not accumulate on the
# published branch. The danger is that the gh-pages branch carries files the site build never
# produces (.nojekyll, 404.html, licence documents); a plain mirroring delete removes them, and
# losing .nojekyll silently changes how GitHub Pages serves the site.
#
# So the protected list is version-controlled, excluded from the delete, and checked three times:
# before the sync via a dry run, after the sync on disk, and again in the staged git diff. Any
# protected path that would disappear stops the deploy before anything is committed or pushed.
#
#   scripts/sync_gh_pages.sh <site-dir> <worktree-dir>
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROTECTED_LIST="${GH_PAGES_PROTECTED_LIST:-$ROOT/config/gh_pages_protected.txt}"

SITE="${1:?usage: sync_gh_pages.sh <site-dir> <worktree-dir>}"
WORKTREE="${2:?usage: sync_gh_pages.sh <site-dir> <worktree-dir>}"

[ -d "$SITE" ]     || { echo "site directory not found: $SITE" >&2; exit 2; }
[ -d "$WORKTREE" ] || { echo "worktree not found: $WORKTREE" >&2; exit 2; }
[ -f "$PROTECTED_LIST" ] || { echo "protected list not found: $PROTECTED_LIST" >&2; exit 2; }

mapfile -t PROTECTED < <(grep -v '^[[:space:]]*#' "$PROTECTED_LIST" | grep -v '^[[:space:]]*$')
[ "${#PROTECTED[@]}" -gt 0 ] || { echo "protected list is empty: $PROTECTED_LIST" >&2; exit 2; }

RSYNC_ARGS=(-a --delete --exclude=.git --exclude="*.orig-*" --exclude="*.orig2-*" --exclude="*.orig3-*")
for path in "${PROTECTED[@]}"; do RSYNC_ARGS+=(--exclude="/$path"); done

# ---- preflight: would the mirror delete anything protected? --------------------------------
echo "preflight: dry run"
DRY="$(rsync "${RSYNC_ARGS[@]}" --dry-run --itemize-changes "$SITE/" "$WORKTREE/")"
FAILED=0
while IFS= read -r line; do
  # rsync reports removals as "*deleting   <path>"
  case "$line" in
    *deleting*)
      victim="${line#*deleting}"; victim="${victim#"${victim%%[![:space:]]*}"}"
      for path in "${PROTECTED[@]}"; do
        if [ "$victim" = "$path" ] || [ "$victim" = "$path/" ]; then
          echo "REFUSING TO DEPLOY: protected path would be deleted: $victim" >&2
          FAILED=1
        fi
      done
      ;;
  esac
done <<< "$DRY"
[ "$FAILED" -eq 0 ] || exit 3

# ---- sync ------------------------------------------------------------------------------------
rsync "${RSYNC_ARGS[@]}" "$SITE/" "$WORKTREE/"

# ---- postflight: are they still on disk? ------------------------------------------------------
for path in "${PROTECTED[@]}"; do
  if [ ! -e "$WORKTREE/$path" ]; then
    echo "REFUSING TO DEPLOY: protected path missing after sync: $path" >&2
    FAILED=1
  fi
done
[ "$FAILED" -eq 0 ] || exit 4

# ---- postflight: does git think they were deleted? --------------------------------------------
if git -C "$WORKTREE" rev-parse --git-dir >/dev/null 2>&1; then
  git -C "$WORKTREE" add -A -- .
  while IFS=$'\t' read -r status path _; do
    [ "$status" = "D" ] || continue
    for protected in "${PROTECTED[@]}"; do
      if [ "$path" = "$protected" ]; then
        echo "REFUSING TO DEPLOY: git records a deletion of protected path: $path" >&2
        FAILED=1
      fi
    done
  done < <(git -C "$WORKTREE" diff --cached --name-status)
  [ "$FAILED" -eq 0 ] || exit 5
fi

echo "sync complete; ${#PROTECTED[@]} protected paths verified"
