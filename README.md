# riemann-verified

Lean 4 proofs contributed to [`mccorvie/riemann-masullo`](https://github.com/mccorvie/riemann-masullo),
a public formalization of A. M. Masullo's manuscript *The Music of the Primes*, with a record of
how each one was checked.

**Current numbers: [`REPORT.md`](REPORT.md)**, generated from the ledgers in [`ledger/`](ledger/).

## What a result here means

- Every proof counted was accepted by Lean in a build of the real upstream module, after which
  `#print axioms` was read and recorded. Nothing is counted because a model said it was right.
- A proof may depend on other declarations upstream that are still unproved. Lean reports that
  as `sorryAx`, and it is listed next to the result.
- Statements are never changed. Upstream's check compares statement hashes before and after.
- Targets that were tried and not proved stay in the totals.
- A proved declaration is a statement Lean accepted. The manuscript is an unrefereed draft, and
  nothing here is a claim about whether its main results hold.

## How the work is done

Most of it is scripts with no model call: a pass of standard tactics over scratch copies of a
file, a gate that applies one proof, builds the module and keeps the edit only if the build
passes, and ledgers that record every attempt. A model is used once per batch, on the
statements the scripts could not close.

Each result carries the route by which it was found: Lean-only search, after a model pass, by
hand, or an undisclosed method. Proofs from an undisclosed method are checked by exactly the
same gate as the others; the method itself is not part of this repository.

## Layout

| Path | Contents |
|---|---|
| [`AGENTS.md`](AGENTS.md) | how an agent or a person takes a turn here |
| [`docs/PILOT.md`](docs/PILOT.md) | the first batch, step by step |
| [`docs/LESSONS.md`](docs/LESSONS.md) | why it is organized this way |
| `scripts/firstpass.py` | the Lean-only pass |
| `scripts/gate.py` | apply, build, axioms, hand-in checks |
| `scripts/rv` | state, turns, upstream preflight, drafts, report |
| `ledger/` | current state and append-only history |

## Running it yourself

You need `elan`, `git`, `gh`, `python3` and about 20 GB of disk. `scripts/setup.sh` clones
upstream into `work/` and fetches the built Mathlib; `scripts/selftest.sh` checks the scripts
against a small Lean project without it. `scripts/leakcheck.sh --generic-only` is the privacy
check without a private pattern list.

This repository is licensed under Apache-2.0 ([`LICENSE`](LICENSE)), the same licence as the
upstream project. Proofs contributed there are under its terms.
