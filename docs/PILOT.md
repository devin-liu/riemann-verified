# The first batch: four statements in one file

The pilot answers three questions with numbers: how many statements Lean closes with no model
call, how many more one mid-tier model pass closes, and what that pass costs. It also proves
out the whole path once, hand-in included, before anything larger is tried.

File: `RiemannMasullo/Ch07_SchauderBasesZeta/Sec3b.lean` (called `$F` below).

| Group | Issue | Declaration | Paper |
|---|---|---|---|
| translate | #4743 | `sLocalAbsolutePW_translate` | Prop. 7.3.2.2(4), p. 352 |
| translate | #4749 | `sLocalInvariantPW_translate` | Prop. 7.3.2.4(3), p. 356 |
| support | #4741 | `sLocalAbsolutePW_globalSupport` | Prop. 7.3.2.2(2), p. 352 |
| support | #4748 | `sLocalInvariantPW_globalSupport` | Prop. 7.3.2.4(2), p. 356 |

Start with the translate pair. The two statements differ only in which level they name, so one
proof, or one private helper, may serve both.

**Check the file before anything else.** On 2026-11-22 the four issues were free, but the same
file had ten claims held by four other contributors and one open pull request. Upstream's advice
is to leave a file that two or three others are working in. Whether the pilot stays here or
moves is the operator's decision; `scripts/rv preflight $F` shows the picture as it is now, and
`scripts/rv scout` ranks the other files by free statements and by how many people are in them.

## Steps

Each step ends with a line in the ledger. Do them in order, one turn or several.

1. **Warm worktree** (operator's go-ahead: several GB of downloads).
   `scripts/setup.sh --warm $F`
   It clones upstream, fetches the built Mathlib, builds the one module and records its time.
   If it reports that Lake compiled Mathlib itself, stop and fix the cache.
   Then, once, on the clean tree: `scripts/gate.py baseline` (a full build; it records the
   statement hashes that the hand-in is compared against).
2. **Upstream check.** `scripts/rv preflight $F`
   Stop if a pilot issue is now claimed, or if the file changed upstream in a way that touches
   the targets.
3. **Lean-only pass, translate pair.**
   `scripts/firstpass.py $F --decl sLocalAbsolutePW_translate --decl sLocalInvariantPW_translate`
4. **Keep wins.** For each: `scripts/gate.py apply $F <decl> --from-run <run>`
5. **Claim** what is being worked on (operator's go-ahead): `scripts/rv draft claim`
   Upstream asks for a claim before work starts. The Lean-only pass is a few minutes of local
   checking, so the claim follows it directly; run `scripts/rv preflight $F` again first.
6. **One model pass on the misses.** Record it (`scripts/rv model-pass …`), then follow
   `prompts/model-pass.md` on `runs/<run>/FAILURES.md`. Check the candidates:
   `scripts/firstpass.py $F --decl <decl> --candidates inbox --route model:<name>`, then
   `gate.py apply`. If the operator reads the usage meter before and after, record it:
   `scripts/rv usage "…"`.
7. **Support pair.** Steps 3 to 6 again for the other two, unless the first pair showed the
   file is out of reach.
8. **Hand-in.** `scripts/gate.py handin`, `scripts/rv draft pr`, read the diff, and the
   operator opens one pull request.
9. **Release the rest** with a note each: `scripts/rv set <decl> --state stuck --note "…"`,
   `scripts/rv draft release`.
10. **Report.** `scripts/rv report`.

## What the pilot decides

- Lean-only wins out of four, wins after the pass out of four, and the usage change.
- Whether the next batch is a whole-file sweep, and of which file: prefer one that is low in
  the import order, nearly finished, uncrowded, and where several statements wait on the same
  missing lemma.
