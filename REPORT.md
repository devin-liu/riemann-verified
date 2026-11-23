# Progress report

Generated 2026-11-23T07:52:40-05:00 by `scripts/rv report` from `ledger/`. Do not edit by hand.

Upstream: [mccorvie/riemann-masullo](https://github.com/mccorvie/riemann-masullo). Every proof counted here was accepted by Lean in a build of the real module; none is counted on a model's say-so.

## Where the targets stand

| State | Count |
|---|---|
| open | 3 |
| merged | 2 |
| stuck | 14 |
| taken | 4 |
| **all targets taken on** | **23** |

Targets that were tried and not proved stay in the total.

## How the proved ones were found

| Route | Proved | Merged upstream |
|---|---|---|
| undisclosed method | 2 | 2 |

## Cost

- Lean runs with no model call: 11, 14 minutes, 119 proof attempts.
- Model passes: 4 (mid claude-opus-5-5: usage before unmeasured; mid claude-opus-5-5: usage before unmeasured; mid claude-opus-5-5: usage before unmeasured; mid claude-opus-5-5: usage before unmeasured).
- A usage figure of `unmeasured` means nobody read the meter; it is not zero.

## Targets

| Issue | Declaration | State | Route | PR | Axioms |
|---|---|---|---|---|---|
| #4289 | `existsUnique_sLocalNormOneQuotientTransition` | stuck |  |  |  |
| #4297 | `sLocalThetaIsotypeSum_complete` | taken | after a model pass |  | propext, sorryAx, Classical.choice, Quot.sound |
| #4299 | `sLocalThetaIsotypeSum_inherited_properties` | stuck |  |  |  |
| #4300 | `globalThetaIsotypeSum_inherited_properties` | stuck |  |  |  |
| #4301 | `globalThetaToHomogeneousProduct_not_isClosed_range` | stuck |  |  |  |
| #4305 | `sLocalStandardThetaTensor_toGlobal_openQuotient` | stuck |  |  |  |
| #4306 | `infiniteStandardThetaAverage_integrable` | stuck |  |  |  |
| #4308 | `exists_infiniteStandardThetaAverage` | stuck |  |  |  |
| #4317 | `sLocalStandardThetaTensor_quotient_equiv` | stuck |  |  |  |
| #4318 | `infiniteStandardThetaAverage_forwardDecay` | stuck |  |  |  |
| #4319 | `infiniteStandardThetaAverage_logBound` | stuck |  |  |  |
| #4457 | `globalPrincipalValueConverse_nontrivial` | open |  |  |  |
| #4458 | `globalPrincipalValueConverse_normTwist` | open |  |  |  |
| #4462 | `globalPrincipalValueConverse_normTwist_divided_exact` | open |  |  |  |
| #4554 | `sLocalPrincipalValue_tfae` | stuck |  |  |  |
| #4558 | `sLocalPolarPrincipalValue_tfae` | stuck |  |  |  |
| #4741 | `sLocalAbsolutePW_globalSupport` | taken | undisclosed method |  | propext, sorryAx, Classical.choice, Quot.sound |
| #4743 | `sLocalAbsolutePW_translate` | merged | undisclosed method | #6098 | propext, sorryAx, Classical.choice, Quot.sound |
| #4748 | `sLocalInvariantPW_globalSupport` | taken | undisclosed method |  | propext, sorryAx, Classical.choice, Quot.sound |
| #4749 | `sLocalInvariantPW_translate` | merged | undisclosed method | #6098 | propext, sorryAx, Classical.choice, Quot.sound |
| #5186 | `sLocalUncutCarving_lt` | stuck |  |  |  |
| #5193 | `memLp_sLocalCarvingGenerator` | taken |  |  |  |
| #5194 | `sLocalCarvingLimit_eq_closedSpan` | stuck |  |  |  |
