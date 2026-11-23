#!/usr/bin/env bash
# Privacy check: nothing private may reach a tracked file here or any text sent upstream.
#
#   scripts/leakcheck.sh               every file git would track in this folder
#   scripts/leakcheck.sh --staged      files staged for commit (the pre-commit hook runs this)
#   scripts/leakcheck.sh --outgoing    outbox/, inbox/ and the uncommitted diff of the upstream worktree
#   scripts/leakcheck.sh FILE ...      the named files
#   add --generic-only to run without the private list (for people who do not have one)
#
# Two lists are applied. The generic one is below. The private one never lives in this folder:
# it is `denylist.txt` in the directory named by $RV_PRIVATE_DIR, or by the one-line, untracked
# file `.private-path`. On the operator's machine a missing private list is an error, so that a
# broken setup cannot pass silently.
set -uo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
cd "$root"
mode=all; generic_only=0; files=()
for arg in "$@"; do
  case $arg in
    --staged|--outgoing) mode=${arg#--} ;;
    --generic-only) generic_only=1 ;;
    *) mode=files; files+=("$arg") ;;
  esac
done

pat=$(mktemp); list=$(mktemp); trap 'rm -f "$pat" "$list"' EXIT
cat >"$pat" <<'PAT'
/(Users|home)/[A-Za-z0-9._-]+/
gh[opsur]_[A-Za-z0-9]{20,}
github_pat_[A-Za-z0-9_]{20,}
(^|[^A-Za-z0-9])sk-[A-Za-z0-9_-]{20,}
BEGIN [A-Z ]*PRIVATE KEY
[A-Za-z0-9._%+-]+@(gmail|icloud|outlook|yahoo|proton)\.[a-z]+
PAT

priv=${RV_PRIVATE_DIR:-}
[ -z "$priv" ] && [ -f .private-path ] && priv=$(head -n 1 .private-path)
if [ -n "$priv" ] && [ -f "$priv/denylist.txt" ]; then
  grep -vE '^[[:space:]]*(#|$)' "$priv/denylist.txt" >>"$pat"
elif [ $generic_only = 0 ]; then
  echo "leakcheck: no private list found (\$RV_PRIVATE_DIR or .private-path -> <dir>/denylist.txt)." >&2
  echo "           Refusing to pass. Use --generic-only only if you have no private material." >&2
  exit 2
fi

case $mode in
  all)
    if git rev-parse --git-dir >/dev/null 2>&1; then git ls-files -co --exclude-standard >"$list"
    else find . -type f -not -path './work/*' -not -path './runs/*' -not -path './.turn/*' \
           -not -path './inbox/*' -not -path './outbox/*' -not -name .private-path -not -name LOCAL.md \
           -not -path '*/__pycache__/*' | sed 's#^\./##' >"$list"; fi ;;
  staged) git diff --cached --name-only --diff-filter=ACM >"$list" ;;
  outgoing)
    find outbox inbox -type f 2>/dev/null >"$list"
    wt=${RV_WORKTREE:-$root/$(python3 -c "import json;print(json.load(open('config/project.json'))['worktree'])")}
    if [ -d "$wt/.git" ]; then
      git -C "$wt" diff >"$root/.turn-outgoing.diff" 2>/dev/null && echo ".turn-outgoing.diff" >>"$list"
      [ -f "$wt/.agent/PR.md" ] && echo "$wt/.agent/PR.md" >>"$list"
    fi ;;
  files) printf '%s\n' "${files[@]}" >"$list" ;;
esac

status=0; n=0
while IFS= read -r f; do
  [ -f "$f" ] || continue
  n=$((n + 1))
  if grep -nIEi -f "$pat" -- "$f" /dev/null | cut -c1-220; then :; fi
  grep -qIEi -f "$pat" -- "$f" && status=1
done <"$list"
rm -f "$root/.turn-outgoing.diff"
if [ $status = 1 ]; then
  echo "leakcheck: FAILED. The lines above match a private or secret pattern. Remove them; do not rephrase around the check." >&2
  exit 1
fi
echo "leakcheck: ok ($n files, mode $mode$([ $generic_only = 1 ] && echo ', generic list only'))"
