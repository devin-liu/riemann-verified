# Progress report

Generated 2026-11-23T00:29:46-05:00 by `scripts/rv report` from `ledger/`. Do not edit by hand.

Upstream: [mccorvie/riemann-masullo](https://github.com/mccorvie/riemann-masullo). Every proof counted here was accepted by Lean in a build of the real module; none is counted on a model's say-so.

## Where the targets stand

| State | Count |
|---|---|
| pr-open | 2 |
| stuck | 2 |
| **all targets taken on** | **4** |

Targets that were tried and not proved stay in the total.

## How the proved ones were found

| Route | Proved | Merged upstream |
|---|---|---|
| undisclosed method | 2 | 0 |

## Cost

- Lean runs with no model call: 3, 1 minutes, 26 proof attempts.
- Model passes: 1 (mid claude-opus-5-5: usage before unmeasured).
- A usage figure of `unmeasured` means nobody read the meter; it is not zero.

## Targets

| Issue | Declaration | State | Route | PR | Axioms |
|---|---|---|---|---|---|
| #4741 | `sLocalAbsolutePW_globalSupport` | stuck |  |  |  |
| #4743 | `sLocalAbsolutePW_translate` | pr-open | undisclosed method | #6098 | propext, sorryAx, Classical.choice, Quot.sound |
| #4748 | `sLocalInvariantPW_globalSupport` | stuck |  |  |  |
| #4749 | `sLocalInvariantPW_translate` | pr-open | undisclosed method | #6098 | propext, sorryAx, Classical.choice, Quot.sound |
