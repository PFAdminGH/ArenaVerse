"""playfantasia.core.combat.effects
==================================
**StatusEffect** objects are the long‑lived buffs, debuffs and damage‑over‑
time instances that stick to a Combatant between turns.

Design goals
------------
1.  *Deterministic*: no random rolls inside hooks – the encounter supplies
    the RNG, so replays are reproducible.
2.  *Tiny Surface*: only three lifecycle hooks (`on_apply`, `on_tick`,
    `on_remove`) so designers / code reviewers have a fixed mental model.
3.  *Stacking Rules*: a single `StackRule` enum covers 95 % of RPG needs.
4.  *No Dependencies Upwards*: this file never imports `encounter` or
    `skills` – keeping our layered architecture clean.
"""

from __future__ import annotations

# --------------------------------------------------------------------- #
# Std‑lib imports
# --------------------------------------------------------------------- #
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, TYPE_CHECKING, Any

if TYPE_CHECKING:
    from playfantasia.core.combat.combatant import Combatant

# --------------------------------------------------------------------- #
# StackRule – how re‑application behaves
# --------------------------------------------------------------------- #
class StackRule(Enum):
    """What happens if the same effect tag is applied again."""
    REFRESH = auto()     # Keep one instance → reset duration
    STACK_ADD = auto()   # Add independent copy (common for DoTs)
    STACK_MERGE = auto() # Merge into one; increment .stacks
    REJECT = auto()      # Ignore new application entirely

# --------------------------------------------------------------------- #
# Base class
# --------------------------------------------------------------------- #
@dataclass(slots=True)
class StatusEffect:
    """
    The superclass every concrete effect inherits from.  Most fields are
    **data only**; the three hook methods contain the behaviour.
    """

    # Core identity
    tag: str                           # dot.poison, buff.rage …
    duration: int                      # turns remaining
    source: 'Combatant'                # who cast / applied it

    # Stacking behaviour
    stack_rule: StackRule = StackRule.REFRESH
    stacks: int = 1
    max_stacks: int = 1

    # Power knobs – subclasses populate these
    magnitude: int = 0                 # generic "strength" number
    flat_mods: Dict[str, int] = field(default_factory=dict)
    mult_mods: Dict[str, float] = field(default_factory=dict)

    # ---------------------------------------------------------------- #
    # Lifecycle hooks – default to no‑op so subclasses implement only
    # what they need.
    # ---------------------------------------------------------------- #
    def on_apply(self, target: 'Combatant') -> None:
        """Called **once** when the effect is first attached."""
        pass

    def on_tick(self, target: 'Combatant') -> None:
        """
        Called at the *start* of the affected combatant's turn.
        The encounter decrements `duration` afterwards.
        """
        pass

    def on_remove(self, target: 'Combatant') -> None:
        """Called when duration hits zero or effect is forcibly dispelled."""
        pass


# --------------------------------------------------------------------- #
# Concrete example effects
# --------------------------------------------------------------------- #
class PoisonDOT(StatusEffect):
    """
    Classic damage‑over‑time that scales with the caster's INT and refreshes
    on re‑application.
    """
    BASE_PCT = 0.15  # 15 % of caster INT per tick

    def __init__(self, source: 'Combatant', duration: int = 2):
        super().__init__(
            tag="dot.poison",
            duration=duration,
            source=source,
            stack_rule=StackRule.REFRESH,
        )

    def on_apply(self, target: 'Combatant'):
        caster_int = self.source.total_stats().get("INT", 0)
        self.magnitude = max(1, int(caster_int * self.BASE_PCT))

    def on_tick(self, target: 'Combatant'):
        # True damage – ignores armour
        target.take_damage(self.magnitude, dmg_type="true")

# --------------------------------------------------------------------- #
class Shield(StatusEffect):
    """
    Flat armour boost that *merges* on re‑apply (higher duration wins).
    """
    def __init__(self, source: 'Combatant', duration: int = 2):
        super().__init__(
            tag="buff.shield",
            duration=duration,
            source=source,
            stack_rule=StackRule.STACK_MERGE,
            max_stacks=1,
        )

    def on_apply(self, target: 'Combatant'):
        bonus = int(self.source.total_stats().get("INT", 0) * 0.4)
        # Store so we can undo exactly the same amount on_remove
        self.flat_mods = {"ARM": bonus}

    def on_remove(self, target: 'Combatant'):
        # Nothing special: flat_mods automatically vanish when Combatant
        # removes the effect from its list.
        pass

# --------------------------------------------------------------------- #
class Rage(StatusEffect):
    """
    +50 % STR, −10 % ACC for 1 turn.  Refreshes rather than stacks.
    """
    def __init__(self, source: 'Combatant', duration: int = 1):
        super().__init__(
            tag="buff.rage",
            duration=duration,
            source=source,
            stack_rule=StackRule.REFRESH,
        )

    def on_apply(self, target: 'Combatant'):
        # multiplicative buffs are percentage (0.5 = +50 %)
        self.mult_mods = {
            "STR": 0.5,     # +50 % strength
            "ACC": -0.1,    # −10 % accuracy
        }

# --------------------------------------------------------------------- #
# Public factory mapping for quick look‑ups (useful for templates later)
# --------------------------------------------------------------------- #
EFFECT_REGISTRY: Dict[str, type[StatusEffect]] = {
    "dot.poison": PoisonDOT,
    "buff.shield": Shield,
    "buff.rage": Rage,
}