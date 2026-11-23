module

import all Probe.Base
public import Probe.Base

@[expose] public noncomputable section

namespace Probe

variable {n m : Nat}

/-- Paper: Lemma 5, p. 3. A module-system file whose dependency has unproved lemmas. -/
theorem carry_over (h : n ≤ m) : n ≤ m := by sorry

/-- Paper: Lemma 6, p. 3. Needs a private fact of the imported module. -/
theorem needs_hidden : (1 : Nat) ≤ 1 ∧ (0 : Nat) ≤ 3 := by sorry

end Probe
