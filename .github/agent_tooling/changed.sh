#!/bin/sh
# changed — git changed files. Scopes an audit to the diff.
# Usage:
#   changed              working-tree + staged vs HEAD (default)
#   changed <ref>        diff vs <ref> (e.g. main, HEAD~3)
#   changed --names      bare names only (no status)
set -eu

names_only=0
ref=""
for a in "$@"; do
  case "$a" in
    --names) names_only=1 ;;
    *) ref="$a" ;;
  esac
done

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "error: not a git repo" >&2
  exit 2
fi

if [ -n "$ref" ]; then
  if [ "$names_only" -eq 1 ]; then
    git --no-pager diff --name-only "$ref"
  else
    git --no-pager diff --name-status "$ref"
  fi
else
  if [ "$names_only" -eq 1 ]; then
    { git --no-pager diff --name-only; git --no-pager diff --cached --name-only; } | sort -u
  else
    git --no-pager status --short
  fi
fi
