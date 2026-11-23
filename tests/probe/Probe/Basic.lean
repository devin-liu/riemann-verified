/-! A small file shaped like an upstream section file. Used only by scripts/selftest.sh. -/

namespace Probe

set_option maxHeartbeats 400000

variable {n m : Nat}

local notation "big(" k ")" => (1 ≤ k)

/-- Paper: Definition 1, p. 1. -/
def level (k : Nat) : Prop := big(k)

section Levels

/-- Paper: Lemma 1, p. 1.
Closed by a hypothesis. -/
theorem keep_hyp (h : n ≤ m) (_hpos : 0 < m) : n ≤ m := by sorry

/-- Paper: Lemma 2, p. 1.
Needs a library lemma. -/
theorem step_up (h : n ≤ m) :
    n ≤ m + 1 := by
  sorry

@[simp]
theorem already_done : level 1 := by
  unfold level; exact Nat.le_refl 1

/-- Paper: Lemma 3, p. 2. Not reachable by cheap tactics. -/
theorem hard_one (f : Nat → Nat) (hf : ∀ k, f (k + 1) = f k + 2) (h0 : f 0 = 0) :
    ∀ k, f k = 2 * k := sorry

end Levels

/-- Paper: Lemma 4, p. 2. Can be proved from the earlier unproved lemma. -/
theorem uses_earlier (h : n ≤ m) : n ≤ m + 1 + 1 := by sorry

/-- After the last target. False, so nothing may close it. -/
theorem later_broken : (1 : Nat) = 2 := by sorry

end Probe
