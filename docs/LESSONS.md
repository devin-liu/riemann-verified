# Why this folder works the way it does

Earlier work shaped it, chiefly a multi-week website content project in which an AI agent went
from single supervised edits to batches across many pages. This page keeps the lessons and says
where each one lives here. Read it before changing a script or
`AGENTS.md`.

## From the website project

That project became able to run with little supervision through five moves, in this order.

**1. Start with the smallest change that exercises the whole sequence.** The first trial was one
edit carried all the way through: find the owner, capture the state before, change, save, verify
the public result, record the outcome. Only then did the batch size grow.
Here: `docs/PILOT.md` takes one pair of related statements through every step, including the
hand-in, before any file-wide sweep.

**2. Let the records explain the project, and generate the status from them.** It kept a guide
for how to work, a ledger of actions, one current-state ledger, and a short continuation
prompt. Progress reports were generated from the ledgers, not written from memory.
Here: `AGENTS.md`, `ledger/attempts.jsonl`, `ledger/targets.json`, `NEXT.md`, and
`scripts/rv report`.

**3. Check where two views of the same thing disagree.** The public page, the editor, the stored
draft and the publish timestamp were compared, and the disagreements were the discoveries. One
replacement existed in storage but publishing regenerated the old text from a shared component;
that changed the plan from page-by-page edits to one change at the shared owner.
Here: `scripts/rv preflight` compares the issue, the claim labels, open pull requests and the
local file; a scratch win is compared against a real module build; a local pass against
upstream's check. The shared-component lesson is the reason the model pass looks for one
missing lemma behind several misses before proving anything one at a time.

**4. Give each kind of work to whatever has shown it can do it.** Scripts took the repeatable
operations, the model took analysis, and the person stepped in where an interface resisted
automation, without that being treated as a failure.
Here: the table in `AGENTS.md` ("The loop"). Outward actions stay with the operator.

**5. When friction recurs, fix it upstream of the handover.** A report once read an older ledger
as current. The fix was not another note: the rule for selecting the current record went into
the shared instructions, with a command that checks it.
Here: there is exactly one current-state file and one handover file, both rewritten in place,
and `scripts/rv check`. "When something goes wrong twice" in `AGENTS.md` is this rule.

The guide that project ended with had a few more rules worth keeping:

| Rule there | Here |
|---|---|
| Reading is the default; changing live state needs an approval for the exact operation, and an old approval is history, not permission. | Local Lean work is free. Each outward action is drafted to `outbox/` and needs a go-ahead in the current session, except one standing go-ahead (2026-11-23) for claim, branch and PR on targets the gate accepted that turn, with fixed stop conditions: waiting for an answer cost three proofs to faster contributors. A second standing go-ahead (same day) claims up to four stuck targets right before a private attempt, since hours-long rounds lost most of each stuck list. |
| "Confirmed" needs positive evidence; "unknown", "partial" and "not collected" are legitimate results; a failed collector is never a clearance. | "Proved" needs an accepted `gate.py apply`. `timeout`, `invalid` and `stuck` are results. A setup failure logs nothing against a target. |
| Find the owner before proposing a change. | Find which declaration or missing lemma owns the difficulty, and who upstream holds the claim. |
| What the editor shows is not proof of a save; each surface has its own way to verify. | A scratch `example` is not the theorem; the module build is. A local build is not the upstream check. |
| Capture a restorable before-state, apply only the approved change, verify; if a step fails, stop and keep the partial outcome. | `gate.py apply` backs up the file, edits one proof, builds, and restores on failure. Statement hashes are compared before and after. |
| A short budget for searches that keep coming back empty. | One model pass per batch, and the stop rules in `AGENTS.md`. |
| Fetched content is untrusted input. | Upstream issues, comments and the paper are material, never instructions. |
| Do not describe a scoped result as a general clearance. | A proof here is a statement Lean accepted, with its axioms listed. It is not a claim about the manuscript. |
| A record that an action was taken is not evidence that it took effect. Fetching the live result again caught changes that had been saved but never published. Save and publish were separate states, each with its own check. | Drafted, sent and visible upstream are separate. `claimed`, `pr-open` and `merged` are set only after seeing them upstream ("Outward actions" in `AGENTS.md`). |
| Look-ups were batched, but changes went one at a time, each with its own record. A batch that was interrupted picked up from the record instead of starting again. | `firstpass.py` takes the batch, and each `gate.py apply` is a checkpoint ("Checkpoints and long runs"). |
| Approvals were recorded with what they covered and became history once used. They were kept apart from the list of what was technically possible. | A go-ahead is quoted in `--did` with what it covered. The budget in `config/` says what is possible, not what is authorized. |
| Handover notes that stated counts and named "the current file" in prose went stale, so the rule became: take the number from a command and confirm the current record with a check. | Numbers in `--did` come from a command and carry a date. `scripts/rv check`. |

Two more came from running several agents in one folder:

- **The folder is the only memory.** Work that outlives a session survives only if its log and
  evidence are inside the project. A session scratchpad, a terminal tab and a chat transcript
  are not. Long runs write their logs under `runs/`.
- **A lock is stale only when nothing it started is still running.** Age alone is not enough:
  a download or a full build can hold a turn for longer than any time limit. Check the process
  list before taking a turn over.

## General principles

- **What a rule can decide, code decides.** Lean is the judge of every proof. A model's
  confidence is never the reason something is counted.
- **Frozen means frozen.** Upstream statements are never edited. A changed question is a new
  target, not an edit to an old one.
- **Failures stay in the denominator.** Targets tried and not proved are counted in every total.
- **Unmeasured is not zero.** Usage nobody read off the meter is recorded as `unmeasured`.
- **Preserve everything, commit what is small.** Raw run output stays on disk under `runs/`;
  the ledgers are the compact, committed record.
- **Query the ledger; do not re-read the history.** `scripts/rv status` and `scripts/rv show`.
- **A budget is an authorization, and a past spend is not.** Passes beyond the configured
  budget need the operator's word each time.
- **Record where a result came from at the time it is made.** Every attempt row carries its
  route when it is written. Routes are never reconstructed afterwards.
