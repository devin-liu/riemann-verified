# The model pass: one look at a batch of misses

You get one pass. Its input is `runs/<run>/FAILURES.md`: the statements Lean could not close
with cheap tactics, each with its goal and the first error of every tactic tried, and a list of
the declarations above them in the file. Record the pass before you start:
`scripts/rv model-pass --model <name> --tier mid --targets A,B --purpose "…"`.

1. Read the bundle once. Before proving anything, ask whether the misses share a cause: the
   same missing fact, the same definition that needs unfolding, the same helper. If two or more
   targets would follow from one intermediate lemma, write that lemma's statement down first.
2. Read only what the targets cite: the definitions and lemmas named in the statements, by line
   range, and the paper passage in the docstring (`scripts/paper.sh <first> <last>` in the
   upstream checkout). Search Mathlib with `grep -rn` under `.lake/packages/mathlib/Mathlib`
   for the specific fact you need.
3. Write at most three candidates per target as `inbox/<decl>.<label>.lean`, labels `c01`,
   `c02`, `c03`. A file holds the text that goes after `:=`, normally `by` and a tactic block.
   Helpers come first as `private theorem <decl>_aux …` with every argument written out,
   followed by a line containing only `-- rv:proof`.
4. Check them all in one Lean run, then keep what passes:
   `scripts/firstpass.py <file> --decl <decl> --candidates inbox --route model:<name>`
   `scripts/gate.py apply <file> <decl> --from-run <run>`
5. One repair round is allowed for a candidate whose only failure is a small, specific Lean
   error. After that, stop.

Never change a statement. No `sorry`, no raised `maxHeartbeats`, no new definitions, instances,
attributes, `variable` or `open` lines. If Lean hangs on a step that is trivial on paper, give
`exact` and `refine` explicit arguments and types, or state the step as a private lemma about
abstract spaces and apply it; do not retry the same search.

Outcomes, all acceptable:

- **Proved**: the gate accepted it.
- **A shared lemma is the blocker**: write its exact Lean statement, why two or more targets
  need it, and what you tried, to `outbox/lemma-<name>.md`. That is the input for a lemma pass.
- **A problem with the statement**: evidence to `outbox/finding-<issue>.md`, state `finding`.
- **Stuck**: `scripts/rv set <decl> --state stuck --note "what was tried, how far it got, where it stopped"`.
