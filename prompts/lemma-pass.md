# The lemma pass: a strong model on one named lemma

This is the expensive step. It is allowed only when `outbox/lemma-<name>.md` exists and names an
intermediate lemma that two or more targets need. Record it first:
`scripts/rv model-pass --model <name> --tier strong --lemma <name> --targets A,B --purpose "…"`.

The task is that one lemma, stated exactly as written in the note, as a `private theorem` placed
directly above the first target that uses it. Nothing else.

1. Read the note, the lemma's statement, and what it cites. Not the whole file.
2. Prove the lemma. Write it, with the proofs of the targets that now follow from it, as
   candidates in `inbox/` in the usual format (`prompts/model-pass.md`, step 3).
3. Check and keep: `scripts/firstpass.py … --candidates inbox --route model:<name>`, then
   `scripts/gate.py apply …` for each target.
4. If the lemma is false or cannot be proved in this pass, say exactly where it fails in the
   note and stop. Do not weaken it into something the targets no longer follow from.
