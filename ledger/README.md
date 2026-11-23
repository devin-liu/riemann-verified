# Ledgers

Read them through `scripts/rv status`, `scripts/rv show <decl>` and `scripts/rv report`. Write
them only through the scripts. `scripts/rv check` verifies them.

- `targets.json`: one row per upstream declaration taken on, keyed by name. This is the only
  source for the current state. Fields: `issue`, `file`, `group`, `state`, `route`, `model`,
  `pr`, `axioms`, `inherited_sorry`, `build_secs`, `claimed_at`, `note`, `updated`.
- `attempts.jsonl`: append-only, one JSON object per line. `type` is one of
  `compile` (a Lean run: tier, seconds, attempts, `model_calls: 0`),
  `try` (one tactic or candidate on one declaration: `route`, `label`, `result`, `detail`),
  `apply` (the gate: `result`, `axioms`, `build_secs`),
  `time` (a file's elaboration time), `state` (a transition), `preflight`, `scout`, `model-pass`,
  `usage`, `handin-check`.
- `sessions.jsonl`: append-only, one row per turn: who, when, what was done, what is next.

States: `open`, `claimed`, `proved-local`, `pr-open`, `merged`, `stuck`, `finding`, `released`,
`taken`. Routes: `lean-only`, `model`, `private`, `human`.

`result` values for a `try`: `win` (no error, no `sorry`, Lean finished), `miss`, `timeout`
(Lean did not finish; says nothing about the proof), `invalid` (the file itself failed before
the target; nothing was tested).
