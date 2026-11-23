# Starting a turn

Paste this into a desktop agent whose working folder is this one. Replace the name.

> You are taking a turn in this folder as `codex-desktop`. Read `AGENTS.md`, then run
> `scripts/rv status` and `scripts/rv turn start --agent codex-desktop`. If the turn is held by
> someone else, say so and stop. If the worktree has edits the ledger does not explain, sort
> that out first ("Every session" in `AGENTS.md`). Otherwise do the "Next action" shown, using the scripts and
> the spending rules in `AGENTS.md`; do not read ledgers or whole Lean files directly. Ask me
> before anything that leaves this machine, except what the standing go-ahead in `AGENTS.md`
> ("Outward actions") covers. When you stop, for any reason, run
> `scripts/rv turn end --did "…" --next "…"` and tell me in three lines what changed, what is
> next, and what you need from me.
