"""arenaverse.core.combat.encounter
====================================
A **CombatEncounter** owns the battle loop.  It is intentionally dumb:
•  It knows *who* is fighting and in what order they act (initiative).
•  It calls each combatant's chosen SkillHandle.
•  It advances cooldowns and status‑effects.
•  It records ActionResult objects so the UI / test harness can replay.

Everything else – formulas, skill details, status effect behaviour – lives
in their dedicated modules.  That keeps this file small and easy to audit.
"""

from __future__ import annotations

# -------------------------------------------------------------------- #
# Std‑lib
# -------------------------------------------------------------------- #
import random
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

# -------------------------------------------------------------------- #
# Internal imports
# -------------------------------------------------------------------- #
from ..combat.combatant import Combatant
from ..combat.skills import select_first_ready, SkillHandle, ActionResult
# Encounter deliberately does NOT import effects or formulas directly.


# -------------------------------------------------------------------- #
# Helper: simple initiative roll
# In future we'll move to a full speed queue, but for now we roll once at
# battle start and keep that fixed order.
# -------------------------------------------------------------------- #
def _roll_initiative(combatants: List[Combatant], rnd) -> List[Combatant]:
    """Return a new list sorted descending by DEX, tie‑broken randomly."""
    # snapshot so we don't mutate caller order
    order = list(combatants)
    # Sort by (DEX, random float) descending
    order.sort(key=lambda c: (c.total_stats().get("DEX", 0), rnd.random()), reverse=True)
    return order


# -------------------------------------------------------------------- #
# Battle log – small wrapper around list[ActionResult]
# -------------------------------------------------------------------- #
@dataclass(slots=True)
class BattleLog:
    rounds: List[List[ActionResult]] = field(default_factory=list)

    def add_round(self, actions: List[ActionResult]):
        self.rounds.append(actions)

    def as_dict(self) -> Dict[str, Any]:
        return {"rounds": [[a.as_dict() for a in r] for r in self.rounds]}

    def __str__(self):
        out = []
        for i, rnd in enumerate(self.rounds, 1):
            out.append(f"===== Round {i} =====")
            for action in rnd:
                if not action.hit:
                    out.append(f"{action.actor}'s {action.skill_used} MISSED {action.target}")
                else:
                    crit = " CRIT!" if action.crit else ""
                    out.append(f"{action.actor} used {action.skill_used} on {action.target} "
                               f"for {action.damage} dmg{crit}")
        return "\n".join(out)


# -------------------------------------------------------------------- #
# CombatEncounter
# -------------------------------------------------------------------- #
@dataclass(slots=True)
class CombatEncounter:
    """Container that drives the fight until one side is wiped out."""

    combatants: List[Combatant]
    rng_seed: int = 42  # deterministic by default

    # these fields are initialised in __post_init__
    rng: random.Random = field(init=False, repr=False)
    initiative: List[Combatant] = field(init=False, repr=False)

    def __post_init__(self):
        self.rng = random.Random(self.rng_seed)
        # Give each combatant the same RNG (substream) for consistency
        for c in self.combatants:
            c.rng = self.rng
        self.initiative = _roll_initiative(self.combatants, self.rng)

    # ---------------------------------------------------------------- #
    def run_battle(self) -> BattleLog:
        """Loop rounds until only one faction (for now: last man standing)."""
        log = BattleLog()

        round_idx = 0
        while self._count_alive() > 1 and round_idx < 99:  # hard cap to avoid inf loops
            round_idx += 1
            actions_this_round: List[ActionResult] = []

            for actor in self.initiative:
                if not actor.is_alive:
                    continue  # dead before their turn
                # 1. Start‑of‑turn effects tick
                actor.tick_effects()
                if not actor.is_alive:
                    continue  # DOT might have killed them

                # 2. Pick a target – simplest: first alive enemy
                target = self._pick_target(actor)
                if target is None:
                    continue  # no enemies left

                # 3. Choose a skill (AI placeholder)
                skill = select_first_ready(self._get_hotbar(actor))

                # 4. Execute
                result = skill.execute(actor, target, self, self.rng)
                actions_this_round.append(result)

                # 5. Tick cooldowns for ALL skills in actor's bar
                for s in self._get_hotbar(actor):
                    s.tick_cd()

                # Early exit if battle ended mid‑round
                if self._count_alive() <= 1:
                    break

            log.add_round(actions_this_round)

        return log

    # ---------------------------------------------------------------- #
    # Helper – naive: everyone fights everyone (no team logic yet)
    # ---------------------------------------------------------------- #
    def _pick_target(self, actor: Combatant) -> Optional[Combatant]:
        for c in self.combatants:
            if c is not actor and c.is_alive:
                return c
        return None

    # ---------------------------------------------------------------- #
    def _get_hotbar(self, actor: Combatant) -> List[SkillHandle]:
        """Placeholder: attach skills list if not already set."""
        hb = getattr(actor, "hotbar", None)
        if hb is None:
            # Lazy create: BasicAttack only
            from ..combat.skills import BasicAttack, PowerStrike
            actor.hotbar = [PowerStrike(), BasicAttack()]
        return actor.hotbar

    # ---------------------------------------------------------------- #
    def _count_alive(self) -> int:
        return sum(1 for c in self.combatants if c.is_alive)