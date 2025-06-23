\"\"\"playfantasia.core.combat.combatant
=====================================

The **Combatant** class is the heart of a single entity inside the battle
simulation (player, monster, summoned minion …).  It owns its stats, gear,
active status‐effects and current HP  – *but it knows nothing about* turn
order or how an encounter progresses.  That orchestration lives in
`core.combat.encounter`.

Why separate things this way?
    •  Keeping Combatant self‑contained means we can unit‑test damage maths
       without spinning up a whole battle.
    •  Encounter can iterate a list[Combatant] generically; it doesn’t care
       whether a unit is a goblin or the player’s wizard.

---------------------------------------------------------------------------
TL;DR of public interface
---------------------------------------------------------------------------
•  `.total_stats()` – aggregated view (base + gear + effects).
•  `.take_damage(raw, *, dtype='phys')` – apply mitigation, subtract HP,
   return *post‑mitigation* damage actually done (for the log).
•  `.heal(amount)` – bounded by max HP.
•  `.apply_effect(StatusEffect)` – resolves stacking rules and stores it.
•  `.tick_effects()` – call once per turn; triggers DOT, decrements timers.
•  Properties: `.hp`, `.is_alive`, `.max_hp`, `.name`.
\"\"\"

from __future__ import annotations

# ----------------------------------------------------------------------- #
# Std‑lib & typing
# ----------------------------------------------------------------------- #
from dataclasses import dataclass, field
from typing import Dict, List, TYPE_CHECKING, Any, Optional

# ----------------------------------------------------------------------- #
# Internal imports – note: only things **below** Combatant in dependency
# tree get imported here (formulas, util.random).  We do NOT import
# 'skills' or 'encounter' to avoid circular deps.
# ----------------------------------------------------------------------- #
from playfantasia.core.combat import formulas
from playfantasia.core.util.random import rng_bool  # used for flee rolls etc.

# Forward‑refs to avoid circular import at type‑check time.
if TYPE_CHECKING:
    from playfantasia.core.combat.effects import StatusEffect
    from playfantasia.core.items.item import Item


# ----------------------------------------------------------------------- #
# Designer‑facing list of canonical stat keys.
# Every system that needs a stat should pull from this set so we never end
# up with “STR” vs “Strength” bugs.
# ----------------------------------------------------------------------- #
STAT_KEYS: tuple[str, ...] = (
    "STR",   #  Strength          – adds to crit multiplier / melee dmg
    "DEX",   #  Dexterity         – might feed dodge later
    "INT",   #  Intelligence      – spell scaling
    "ACC",   #  Accuracy          – hit chance
    "EVA",   #  Evasion           – dodge chance
    "CRT",   #  Critical Rate     – crit chance
    "ARM",   #  Armor             – flat damage mitigation
    "HP",    #  Maximum hit‑points
)


# ----------------------------------------------------------------------- #
# Helper: tiny additive container for gear stats so we don’t write the
# same comprehension three times.
# ----------------------------------------------------------------------- #
def _sum_item_stats(items: List["Item"]) -> Dict[str, int]:
    total: Dict[str, int] = {}
    for itm in items:
        for k, v in getattr(itm, "stat_bonus", {}).items():
            total[k] = total.get(k, 0) + v
    return total


# ----------------------------------------------------------------------- #
# Combatant – **runtime** entity used by the encounter loop.
# ----------------------------------------------------------------------- #
@dataclass(slots=True)
class Combatant:
    \"\"\"A creature or character that can act in combat.\"\"\"

    # ─────────────────────────────────────────────────────────────────── #
    # Basic identity
    # ─────────────────────────────────────────────────────────────────── #
    name: str

    # ─────────────────────────────────────────────────────────────────── #
    # Core stats – base values defined by archetype or level‑up table.
    # Example: {"STR": 10, "DEX": 6, "INT": 2, ...}
    # (We *do not* enforce all keys present – missing keys treated as 0.)
    # ─────────────────────────────────────────────────────────────────── #
    base_stats: Dict[str, int] = field(default_factory=dict)

    # ─────────────────────────────────────────────────────────────────── #
    # Skills the combatant can use
    # ─────────────────────────────────────────────────────────────────── #
    hotbar: List["SkillHandle"] = field(default_factory=list) # Add this line

    # ─────────────────────────────────────────────────────────────────── #
    # Equipped items (weapon, armour …).  Each item is expected to expose
    # a `.stat_bonus` dict and later a `contributing_mods()` for ModBus.
    # ─────────────────────────────────────────────────────────────────── #
    equipment: List["Item"] = field(default_factory=list, repr=False)

    # ─────────────────────────────────────────────────────────────────── #
    # Current HP – starts at max_hp unless a scenario spawns a wounded unit.
    # ─────────────────────────────────────────────────────────────────── #
    hp: int = -1  # Will be initialised in __post_init__

    # ─────────────────────────────────────────────────────────────────── #
    # Active status effects (buffs/debuffs).  Populated at runtime.
    # ─────────────────────────────────────────────────────────────────── #
    active_effects: List["StatusEffect"] = field(default_factory=list, repr=False)

    # A local RNG for things like flee chance; seeded by encounter.
    rng: Any = field(default=None, repr=False)

    # ------------------------------------------------------------------ #
    # Dataclass post‑init hook – sets HP to max if caller left it at -1.
    # ------------------------------------------------------------------ #
    def __post_init__(self):
        if self.hp == -1:
            self.hp = self.max_hp

    # ------------------------------------------------------------------ #
    # Properties
    # ------------------------------------------------------------------ #
    @property
    def max_hp(self) -> int:
        \"\"\"Dynamic because buffs or gear can raise HP mid‑fight.\"\"\"
        return self.total_stats().get("HP", 1)

    @property
    def is_alive(self) -> bool:
        return self.hp > 0

    # ------------------------------------------------------------------ #
    # Core public methods
    # ------------------------------------------------------------------ #
    def total_stats(self) -> Dict[str, int]:
        \"\"\"Return a fresh **dict** combining base + gear + effect mods.

        1. Start with *base_stats*.
        2. Add any `stat_bonus` from equipped items.
        3. Add each effect's **flat_mods**.
        4. Apply each effect's **mult_mods** (multiplicative).
        \"\"\"
        totals: Dict[str, float] = dict(self.base_stats)

        # 1+2: equipment
        gear_bonus = _sum_item_stats(self.equipment)
        for k, v in gear_bonus.items():
            totals[k] = totals.get(k, 0) + v

        # 3: flat additive buffs/debuffs
        for eff in self.active_effects:
            for k, v in getattr(eff, "flat_mods", {}).items():
                totals[k] = totals.get(k, 0) + v

        # 4: multiplicative (order‑independent because we multiply factors)
        for eff in self.active_effects:
            for k, m in getattr(eff, "mult_mods", {}).items():
                totals[k] = totals.get(k, 0) * (1 + m)

        # Cast everything back to int for downstream math
        return {k: int(v) for k, v in totals.items()}

    # ------------------------------------------------------------------ #
    def take_damage(self, raw: int, dmg_type: str = "physical") -> int:
            """Apply armour / resist mitigation, subtract HP and
            return the **actual** damage taken.

            The attacker has already produced a raw‐damage number.
            We now let `formulas.mitigation()` translate our own stats
            into a flat reduction, then make sure at least 1 HP lands.
            """
            # `total_stats()` gives our aggregated dictionary of stats
            reduction = formulas.mitigation(self.total_stats(), dmg_type)
            dealt     = max(1, int(raw - reduction))

            self.hp = max(0, self.hp - dealt)
            return dealt

    # ------------------------------------------------------------------ #
    def heal(self, amount: int) -> int:
        \"\"\"Restore HP, never exceeding max_hp. Returns real amount healed.\"\"\"
        if amount <= 0 or not self.is_alive:
            return 0
        before = self.hp
        self.hp = min(self.max_hp, self.hp + amount)
        return self.hp - before

    # ------------------------------------------------------------------ #
    # Status‑effect plumbing
    # ------------------------------------------------------------------ #
    def apply_effect(self, effect: "StatusEffect"):
        \"\"\"Handle stacking rules then add the *effect* instance.

        For now we simply append; the real stacking/refresh logic will be
        coded in `effects.py`.  This keeps Combatant tiny and dumb.
        \"\"\"
        from playfantasia.core.combat.effects import StackRule  # local import

        # Quick path: no effect with same tag yet → just add
        same = next((e for e in self.active_effects if e.tag == effect.tag), None)
        if same is None:
            self.active_effects.append(effect)
            effect.on_apply(self)
            return

        # Respect chosen stacking policy
        if effect.stack_rule == StackRule.REFRESH:
            same.duration = effect.duration
            same.magnitude = max(same.magnitude, effect.magnitude)
        elif effect.stack_rule == StackRule.STACK_ADD:
            self.active_effects.append(effect)
            effect.on_apply(self)
        elif effect.stack_rule == StackRule.STACK_MERGE:
            same.stacks = min(same.stacks + 1, getattr(same, "max_stacks", 1))
            same.duration = effect.duration
        # STACK_RULE.REJECT does nothing

    # ------------------------------------------------------------------ #
    def tick_effects(self):
        \"\"\"Call at *start of this combatant’s turn*.\"\"\"
        for eff in list(self.active_effects):  # copy → we might remove
            eff.on_tick(self)
            eff.duration -= 1
            if eff.duration <= 0:
                eff.on_remove(self)
                self.active_effects.remove(eff)

    # ------------------------------------------------------------------ #
    # Debug helper – pretty string
    # ------------------------------------------------------------------ #
    def __str__(self):
        return f\"{self.name} (HP {self.hp}/{self.max_hp})\"