"""playfantasia.core.combat.skills
=================================
*SkillHandle* objects are how the encounter tells a combatant to perform a
single action.  Each instance owns its **cooldown counter**, is able to say
"I am ready" or "Still recharging", and — when executed — returns an
*ActionResult* that the logger can serialise or print.

In the long term every concrete skill will migrate into data templates, but
we keep two hard‑coded examples here so the battle loop has something to
call while the template compiler is not yet written.
"""

from __future__ import annotations

# ──────────────────────────────────────────────────────────────────────
# Standard library
# ──────────────────────────────────────────────────────────────────────
from dataclasses import dataclass, field
from typing import Any, Dict, TYPE_CHECKING, List

# ──────────────────────────────────────────────────────────────────────
# Internal imports (only low‑level helpers; avoid circular deps)
# ──────────────────────────────────────────────────────────────────────
from playfantasia.core.combat import formulas
from playfantasia.core.util.random import rng_bool
from playfantasia.core.combat.combatant import Combatant

if TYPE_CHECKING:
    from playfantasia.core.combat.encounter import CombatEncounter
    from playfantasia.core.combat.effects import StatusEffect

# -------------------------------------------------------------------- #
# ActionResult – tiny DTO returned by every skill execution
# -------------------------------------------------------------------- #
@dataclass(slots=True)
class ActionResult:
    """
    A record of one action execution – whether it hit, crit, damage done,
    etc.  The battle logger or UI layer can turn this straight into text or
    animations.
    """
    actor: str
    target: str
    skill_used: str
    hit: bool = False
    crit: bool = False
    damage: int = 0   # post‑mitigation
    # placeholder for future: applied_effects: list[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        """Return a plain dict for easy JSON dumps."""
        return self.__dict__

# -------------------------------------------------------------------- #
# Base class – every concrete skill inherits from this
# -------------------------------------------------------------------- #
@dataclass(slots=True)
class SkillHandle:
    """
    An object that lives in a combatant's hotbar.  It holds its own cooldown
    timer so the CombatEncounter can simply call `tick_cd()` on everyone at
    the end of a round.
    """
    name: str
    cooldown_max: int = 0
    current_cd: int = 0

    # ───────── Ready / cooldown helpers ───────── #
    def is_ready(self) -> bool:
        return self.current_cd == 0

    def tick_cd(self):
        if self.current_cd > 0:
            self.current_cd -= 1

    def reset_cd(self):
        """Set the timer back to full (called after a successful execute)."""
        self.current_cd = self.cooldown_max

    # ───────── Main API ───────── #
    def execute(
        self,
        actor: Combatant,
        target: Combatant,
        encounter: "CombatEncounter",
        rnd,
    ) -> ActionResult:
        """
        Sub‑classes override this.  They MUST call `self.reset_cd()` at the
        end so that future turns see the correct cooldown.
        """
        raise NotImplementedError

# -------------------------------------------------------------------- #
# Concrete sample 1: BasicAttack
# -------------------------------------------------------------------- #
class BasicAttack(SkillHandle):
    """
    Fallback physical hit that every unit can perform.  No cooldown.
    Damage = STR.  Uses hit and crit rolls from formulas.py.
    """
    def __init__(self):
        super().__init__(name="Basic Attack", cooldown_max=0)

    def execute(
        self,
        actor: Combatant,
        target: Combatant,
        encounter: "CombatEncounter",
        rnd,
    ) -> ActionResult:
        res = ActionResult(actor=actor.name, target=target.name, skill_used=self.name)

        # 1. Did we hit?
        if not formulas.hit_roll(
            actor.total_stats().get("ACC", 0),
            target.total_stats().get("EVA", 0),
            rnd,
        ):
            res.hit = False
            self.reset_cd()  # basic attack still "spends" the action
            return res

        res.hit = True

        # 2. Base damage starts at STR
        dmg = actor.total_stats().get("STR", 1)

        # 3. Crit check
        if formulas.crit_roll(actor.total_stats().get("CRT", 0), rnd):
            res.crit = True
            dmg = int(dmg * formulas.crit_multiplier(actor.total_stats().get("STR", 0)))

        # 4. Target mitigates & loses HP
        res.damage = target.take_damage(dmg, "phys")

        self.reset_cd()
        return res

# -------------------------------------------------------------------- #
# Concrete sample 2: PowerStrike – shows a cooldown and self‑buff
# -------------------------------------------------------------------- #
class PowerStrike(SkillHandle):
    """200 % STR damage and applies a one‑turn Rage effect to self."""
    def __init__(self):
        super().__init__(name="Power Strike", cooldown_max=2)

    def execute(
        self,
        actor: Combatant,
        target: Combatant,
        encounter: "CombatEncounter",
        rnd,
    ) -> ActionResult:
        res = ActionResult(actor=actor.name, target=target.name, skill_used=self.name)
        res.hit = True  # guaranteed hit for demo purposes

        dmg = actor.total_stats().get("STR", 1) * 2
        if formulas.crit_roll(actor.total_stats().get("CRT", 0), rnd):
            res.crit = True
            dmg = int(dmg * formulas.crit_multiplier(actor.total_stats().get("STR", 0)))

        res.damage = target.take_damage(dmg, "phys")

        # Attempt to apply Rage if the effect class exists
        try:
            from playfantasia.core.combat.effects import Rage
            actor.apply_effect(Rage(source=actor))
        except (ImportError, AttributeError):
            pass  # Rage not implemented yet – safe in early scaffolding

        self.reset_cd()
        return res

# -------------------------------------------------------------------- #
# Helper – pick the first ready skill from a hotbar
# -------------------------------------------------------------------- #
def select_first_ready(hotbar: List[SkillHandle]) -> SkillHandle:
    """
    Utility for simple AI: iterate the list in order, return the first skill
    whose cooldown is 0.  If none are ready, return a new BasicAttack().
    """
    for s in hotbar:
        if s.is_ready():
            return s
    return BasicAttack()