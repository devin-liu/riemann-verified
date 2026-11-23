# Running one cycle

Paste this into a fresh desktop agent whose working folder is this one. Replace the name. A
cycle is one file taken from scout to pull request; it may span several turns.

> You are running one cycle in this folder as `claude-desktop`. Read `AGENTS.md`, then run
> `scripts/rv status` and `scripts/rv turn start --agent claude-desktop`. If the turn is held by
> someone else, or `pgrep -fl 'lake|setup.sh|firstpass|gate.py'` shows a run, say so and stop.
> Sort out any worktree edits the ledger does not explain first.
>
> Then work the cycle, cheapest step first, using only the scripts:
>
> 0. **Sync.** With a clean worktree, run `scripts/setup.sh --update`: it returns the checkout
>    to `main` and fast-forwards it to upstream. The fork's own `main` does not need syncing;
>    only the branch you push matters, and it is cut from the updated `main`.
>
> 1. **Inbox.** For each file in `inbox/` with no result in the ledger yet, check it with
>    `scripts/firstpass.py <file> --decl … --candidates inbox --route private` and apply each win
>    with `scripts/gate.py apply`. Candidates already checked are skipped.
>
>    **Every accepted win is claimed at once**, under the standing go-ahead in `AGENTS.md`
>    ("Outward actions", step 1). If someone else holds it or it is closed, set `taken`.
>    This applies to wins in step 3 as well.
> 2. **Open pull requests.** For each target in `pr-open`, read `gh pr view <n>`; set `merged`
>    only if it merged, and fix and push if the check says fail.
> 3. **New file.** If nothing is waiting, follow "Next action" in `NEXT.md`, or
>    `scripts/rv scout --min-free 1` and `scripts/rv preflight <file> --add`. Scout picks from
>    upstream's own unclaimed query (open `proof` issues without `claimed`, `stuck` or `gap`;
>    `refutation` issues count), minus fresh `Claiming` comments the label has not caught up
>    with and issues an open PR already closes. Run `firstpass.py` over its free
>    targets and apply the wins. Make one mid-tier model pass over the misses, as `AGENTS.md`
>    says; mark what is still unproved `stuck` with a note.
> 4. **Hand-in and pull request, in the same turn.** If anything is `proved-local`, run
>    `scripts/gate.py handin` in the background with its log under `runs/`, then
>    `scripts/rv draft pr`, and read the diff and the draft. Then open the pull request without
>    asking, as in `AGENTS.md` ("Outward actions", step 2): fresh preflight, one new branch from
>    `main` with only these targets' files, noreply author, push to `fork`, `outbox/pr.sh` plus
>    `--head <your-login>:<branch>`. Set `pr-open` after `gh pr view` shows it. Do not wait for
>    me unless one of the stop conditions listed there holds; then ask in one question.
>
> Ask me before anything that leaves this machine, except what the standing go-ahead in
> `AGENTS.md` covers: claim, hand-in branch and pull request for targets the gate accepted
> this turn, and fixes pushed to our own open PR. When you stop, for any reason, run
> `scripts/rv turn end --did "…" --next "…" --needs "…"`. List the stuck targets in `--needs`
> so I can decide whether they go to a private attempt. Then tell me in three lines what changed,
> what is next, and what you need from me.

Stuck targets that the operator sends for a private attempt are claimed first, under the second
standing go-ahead in `AGENTS.md` ("claim before a private attempt"): at most four, each with a
fresh preflight, and only those whose claim is visible upstream are handed over. They come back
as `inbox/` files, and step 1 of the next cycle picks them up. How that attempt is started is in the untracked
`LOCAL.md`, not here.
