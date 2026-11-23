#!/usr/bin/env bash
# One warm upstream worktree. Zero model calls. Run by the operator, or with their go-ahead:
# it downloads the Lean toolchain and the built Mathlib (several GB) and needs free disk.
#
#   scripts/setup.sh              clone upstream read-only into work/, fetch the Mathlib cache
#   scripts/setup.sh --fork       same, but fork first (creates a public fork on your GitHub account)
#   scripts/setup.sh --warm FILE  additionally build one module and record its time
#   scripts/setup.sh --update     fast-forward a clean worktree to upstream main
#
# It never runs `lake update` and never changes the toolchain or dependency pins.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
cfg() { python3 -c "import json,sys;print(json.load(open('$root/config/project.json'))[sys.argv[1]])" "$1"; }
upstream=$(cfg upstream); branch=$(cfg upstream_branch)
wt=${RV_WORKTREE:-$root/$(cfg worktree)}
fork=0; warm=""; update=0
while [ $# -gt 0 ]; do
  case $1 in
    --fork) fork=1; shift ;;
    --warm) warm=$2; shift 2 ;;
    --update) update=1; shift ;;
    *) echo "unknown option $1" >&2; exit 2 ;;
  esac
done

free_gb=$(df -g "$root" | awk 'NR==2 {print $4}')
if [ ! -d "$wt/.lake/packages/mathlib" ] && [ "$free_gb" -lt 25 ]; then
  echo "only ${free_gb} GB free; the toolchain, Mathlib cache and project build need about 15-20 GB. Free space first." >&2
  exit 1
fi

if [ ! -d "$wt/.git" ]; then
  mkdir -p "$(dirname "$wt")"
  git clone "https://github.com/$upstream.git" "$wt" </dev/null
fi
cd "$wt"
# `origin` stays upstream (read-only for us); the fork, if any, is the remote named `fork`.
if [ $fork = 1 ] && ! git remote | grep -qx fork; then
  gh repo fork "$upstream" --remote --remote-name fork </dev/null
  # Without a terminal `gh` can create the fork and still skip the remote: add it ourselves.
  if ! git remote | grep -qx fork; then
    git remote add fork "https://github.com/$(gh api user -q .login </dev/null)/${upstream#*/}.git"
  fi
fi

if [ $update = 1 ]; then
  [ -z "$(git status --porcelain --untracked-files=no)" ] || { echo "worktree has edits; not updating" >&2; exit 1; }
  git fetch --quiet origin "$branch" </dev/null
  # After a pull request the checkout sits on its branch; every new cycle starts from main.
  [ "$(git branch --show-current)" = "$branch" ] || git switch --quiet "$branch"
  git merge --ff-only "origin/$branch"
fi

echo "toolchain: $(cat lean-toolchain)"
start=$(date +%s)
lake exe cache get </dev/null
echo "cache: $(( $(date +%s) - start ))s"

if [ -n "$warm" ]; then
  module=$(echo "${warm%.lean}" | tr / .)
  log="$wt/.agent/rv/warm.log"; mkdir -p "$(dirname "$log")"
  start=$(date +%s)
  # If this starts compiling Mathlib's own files, the cache is wrong: stop and fix the setup.
  lake build "$module" </dev/null 2>&1 | tee "$log" | grep -E --line-buffered 'Mathlib\.|error|Built|✖' | tail -n 20 || true
  secs=$(( $(date +%s) - start ))
  if grep -qE '(Building|Compiling|✔ \[[0-9/]+\] Built) Mathlib\.' "$log"; then
    echo "STOP: lake compiled Mathlib itself. The cache did not apply; fix that before any proof work." >&2
    exit 3
  fi
  echo "warm build of $module: ${secs}s"
  (cd "$root" && python3 scripts/gate.py time "$warm")
fi
echo "worktree ready: $wt @ $(git rev-parse --short HEAD)"
