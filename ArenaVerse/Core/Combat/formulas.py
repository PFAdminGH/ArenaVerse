    """
PlayFantasia • formulas.py
Pure maths – no game objects.
"""

from __future__ import annotations
import math
import random

__all__ = [
    # secondary
    "sec_hp", "sec_weapon_damage",
    # opposed helpers
    "sigmoid_opposed", "chance_to_hit", "chance_to_crit",
    # damage
    "raw_damage", "mitigation", "final_damage",
]

# ──────────────────────────────────────────────────────────────
# 1.  Secondary attributes
# ──────────────────────────────────────────────────────────────
def sec_hp(CON: int) -> int:
    return CON * 10

def sec_weapon_damage(wpn_dmg: int, STR: int = 0, INT: int = 0,
                      dmg_type: str = "physical") -> float:
    stat = STR if dmg_type == "physical" else INT
    return wpn_dmg + 0.5 * stat


# ──────────────────────────────────────────────────────────────
# 2.  Generic opposed-stat logistic curve
# ──────────────────────────────────────────────────────────────
def sigmoid_opposed(att: float, deff: float,
                    *, base=5.0, ceiling=95.0, k=0.15) -> float:
    """Bounded logistic curve used for all opposed rolls."""
    return base + (ceiling - base) / (1 + math.exp(-k * (att - deff)))


# Convenience RNG so tests can seed deterministically
_rng: random.Random = random.Random()
def set_seed(seed: int | None) -> None: _rng.seed(seed)


# ──────────────────────────────────────────────────────────────
# 3.  Chances
# ──────────────────────────────────────────────────────────────
def chance_to_hit(att_stats: dict, def_stats: dict) -> float:
    return sigmoid_opposed(
        att_stats.get("DEX", 0) + att_stats.get("AGI", 0),
        def_stats.get("AGI", 0),
    )

def chance_to_crit(att_stats: dict, def_stats: dict) -> float:
    return sigmoid_opposed(
        att_stats.get("DEX", 0),
        def_stats.get("AGI", 0),
    )


# ──────────────────────────────────────────────────────────────
# 4.  Damage pipeline
# ──────────────────────────────────────────────────────────────
def raw_damage(att_stats: dict, dmg_type: str = "physical") -> float:
    base = att_stats.get("weapon_damage", 0)
    STR, INT = att_stats.get("STR", 0), att_stats.get("INT", 0)
    return base + 0.5 * (STR if dmg_type == "physical" else INT)

def mitigation(def_stats: dict, dmg_type: str = "physical") -> float:
    if dmg_type == "physical":
        return def_stats.get("armor", 0) * 0.25
    if dmg_type == "magical":
        return def_stats.get("resist", 0) * 0.30
    return 0  # true dmg

def final_damage(att_stats: dict, def_stats: dict, dmg_type="physical") -> int:
    dmg = raw_damage(att_stats, dmg_type) - mitigation(def_stats, dmg_type)
    return max(1, int(dmg))