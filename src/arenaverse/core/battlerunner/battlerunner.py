#!/usr/bin/env python3
'''
ArenaVerse • Battle Runner (v0.3, post-formula-refactor)
=======================================================

Purpose
-------
* Run **one** fully-detailed duel (turn-by-turn log) *or*
  **many** head-less duels to measure win-rates / fight length.
* Keep every bit of maths inside the engine – this script is orchestration +
  pretty-printing only.
* **Items are deliberately absent** for now; they’ll be wired back in later.

Quick examples
--------------
  # One verbose fight, random seed
  $ python battle_runner.py

  # 1 000 Monte-Carlo duels with a fixed seed
  $ python battle_runner.py --mode monte -n 1000 --seed 123
'''
from __future__ import annotations

# ── std-lib ────────────────────────────────────────────────────────────
import argparse
import random
from copy import deepcopy
from statistics import mean
from typing import List, Tuple

# ── engine imports ─────────────────────────────────────────────────────
from ..combat.combatant import Combatant
from ..combat.encounter import CombatEncounter, BattleLog
# (formulas isn’t used directly here but is handy for future tweaks)
from ..combat import formulas   # noqa: F401

# ───────────────────────────────────────────────────────────────────────
# Temporary roster helper – no YAML/DB loader yet
# ───────────────────────────────────────────────────────────────────────
def make_default_fighters() -> Tuple[Combatant, Combatant]:
    """Return two fresh Combatants for test battles."""
    hero = Combatant(
        name="Knight",
        base_stats={
            "STR": 12, "CON": 14, "ACC": 8, "EVA": 6, "CRT": 4,
            "weapon_damage": 4, "armor": 3,
        },
    )
    orc = Combatant(
        name="Orc Berserker",
        base_stats={
            "STR": 14, "CON": 12, "ACC": 7, "EVA": 5, "CRT": 3,
            "weapon_damage": 5, "armor": 1,
        },
    )
    return hero, orc

# ───────────────────────────────────────────────────────────────────────
# Pretty-printing helpers
# ───────────────────────────────────────────────────────────────────────
CORE_KEYS = (
    "STR", "CON", "ACC", "EVA", "CRT",
    "HP", "weapon_damage", "armor",
)

def snapshot(unit: Combatant) -> str:
    """Neat multi-line dump of a combatant’s build (no gear yet)."""
    stats = unit.total_stats()
    stats.setdefault("HP", unit.max_hp)          # ensure HP is shown
    core  = ", ".join(f"{k}:{stats.get(k, 0)}" for k in CORE_KEYS if k in stats)
    skills = ", ".join(s.name for s in getattr(unit, "hotbar", [])[:3]) or "BasicAttack"
    return f"{unit.name}\n  Stats : {core}\n  Skills: {skills}\n"

# ───────────────────────────────────────────────────────────────────────
# Single detailed encounter
# ───────────────────────────────────────────────────────────────────────
def run_single(seed: int | None = None, quiet: bool = False) -> None:
    a0, b0 = make_default_fighters()
    seed = seed if seed is not None else random.SystemRandom().randrange(2**32)
    print(f"[INFO] Seed for this encounter: {seed}\n")

    p1, p2 = deepcopy(a0), deepcopy(b0)
    battle  = CombatEncounter([p1, p2], rng_seed=seed)
    log: BattleLog = battle.run_battle()

    # ── report ─────────────────────────────────────────────────────────
    print("=== Combatant Load-out ===")
    print(snapshot(p1))
    print(snapshot(p2))

    if not quiet:
        print("=== Battle Log ===")
        print(str(log))

    winner = next((c for c in battle.combatants if c.is_alive), None)
    print("\n=== Result ===")
    if winner:
        print(f"Winner: {winner.name} in {len(log.rounds)} rounds")
    else:
        print(f"Draw after {len(log.rounds)} rounds")

# ───────────────────────────────────────────────────────────────────────
# Monte-Carlo aggregate
# ───────────────────────────────────────────────────────────────────────
def run_monte(num_trials: int, seed: int | None = None) -> None:
    a0, b0 = make_default_fighters()
    wins_a = wins_b = draws = 0
    rounds: List[int] = []

    base_seed = seed if seed is not None else random.SystemRandom().randrange(2**32)
    for n in range(num_trials):
        trial_seed = base_seed + n
        p1, p2 = deepcopy(a0), deepcopy(b0)
        battle   = CombatEncounter([p1, p2], rng_seed=trial_seed)
        log      = battle.run_battle()
        rounds.append(len(log.rounds))

        winner = next((c for c in battle.combatants if c.is_alive), None)
        if   winner is p1: wins_a += 1
        elif winner is p2: wins_b += 1
        else:              draws  += 1

    # ── summary ────────────────────────────────────────────────────────
    print("=== Monte-Carlo Summary ===")
    print(snapshot(a0))
    print(snapshot(b0))
    print(f"Trials run          : {num_trials}")
    print(f"{a0.name} wins       : {wins_a}  ({wins_a/num_trials*100:.1f}%)")
    print(f"{b0.name} wins   : {wins_b}  ({wins_b/num_trials*100:.1f}%)")
    print(f"Draws               : {draws}")
    print(f"Avg. rounds/fight   : {mean(rounds):.2f}")
    print(f"Shortest fight      : {min(rounds)} rounds")
    print(f"Longest fight       : {max(rounds)} rounds")

# ───────────────────────────────────────────────────────────────────────
# CLI glue
# ───────────────────────────────────────────────────────────────────────
def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        prog="battle_runner",
        description="Run ArenaVerse combat in detailed or aggregate mode."
    )
    ap.add_argument(
        "--mode", choices=("single", "monte"), default="single",
        help="'single' = one verbose fight; 'monte' = many fights for stats."
    )
    ap.add_argument(
        "-n", "--num", type=int, default=100,
        help="Number of Monte-Carlo trials (mode 'monte' only)."
    )
    ap.add_argument("--seed",  type=int,  help="Optional RNG seed for reproducibility.")
    ap.add_argument("--quiet", action="store_true",
                    help="Suppress turn-by-turn log in single mode.")
    return ap.parse_args()

def main() -> None:
    args = parse_args()
    if args.mode == "single":
        run_single(seed=args.seed, quiet=args.quiet)
    else:
        run_monte(num_trials=args.num, seed=args.seed)

if __name__ == "__main__":
    main()