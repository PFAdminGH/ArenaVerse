# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║                    PlayFantasia • Battle Runner (v0.002)                  ║
# ╠═══════════════════════════════════════════════════════════════════════════╣
# ║  PURPOSE                                                                 ║
# ║    • Display each combatant’s full stats & gear before fighting.         ║
# ║    • Run EITHER a single verbose duel OR many duels for win-rate stats.  ║
# ║    • Aggregation logic lives here; combat math stays in the engine.      ║
# ║                                                                           ║
# ║  QUICK HOW-TO                                                             ║
# ║    1) Make sure you have already executed:                                ║
# ║         • Combat Engine cell (defines Item, Combatant, CombatEncounter)   ║
# ║         • Sample Data cell (creates COMBATANT_A and COMBATANT_B)          ║
# ║    2) Adjust the PARAMETERS section below and run this cell.              ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

from copy import deepcopy
from statistics import mean
import random

from playfantasia.combat_engine import Combatant, CombatEncounter
from playfantasia.sample_data import COMBATANT_A, COMBATANT_B


# ─────────────────────────────────────────────────────────────────────────────
# PARAMETERS – tweak these and re-run
# ─────────────────────────────────────────────────────────────────────────────
SINGLE_BATTLE = True   # ► True  = one detailed fight
                        # ► False = many fights for stats (set NUM_TRIALS)

NUM_TRIALS    = 100      # Used only if SINGLE_BATTLE is False

USE_SEED    = False    # Set False for “truly” random sessions
SEED_BASE   = 42      # Moved down one line; value unchanged

# Choose which combatants to pit against each other.
# By default we use the aliases from your Sample Data cell.
COMBATANT_ONE = COMBATANT_A   # e.g. warrior
COMBATANT_TWO = COMBATANT_B   # e.g. wizard
# Feel free to import / create others and plug them in here.

# ─────────────────────────────────────────────────────────────────────────────
# HELPER FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────
def snapshot(combatant):
    """
    Return a formatted multiline string with:
      • core + extra stats
      • equipment list
      • NEW: up to three equipped skills (shows cooldown for quick reference)
    """
    stats = combatant.total_stats

    # 1) Pretty-print stats --------------------------------------------------
    core_stats = ", ".join(f"{k}:{stats[k]}"
                           for k in ("STR", "CON", "DEX", "INT", "WIS", "AGI"))
    extras = {k: v for k, v in stats.items()
              if k not in {"STR","CON","DEX","INT","WIS","AGI",
                           "weapon_damage","armor","resist"}}
    extras_str = ", ".join(f"{k}:{v}" for k, v in extras.items()) or "None"

    # 2) Gear read-out -------------------------------------------------------
    gear = ", ".join(sorted({itm.name for itm in combatant._equipment.values()})) \
           or "None"

    # 3) **NEW** — list equipped skills -------------------------------------
    # If the fighter has no skills, show “None” so the column never vanishes.
    skills = ", ".join(f"{sk.name}(CD:{sk.cooldown_max})"
                       for sk in combatant._skills) or "None"

    # 4) Assemble the block --------------------------------------------------
    return (
        f"{combatant.name}\n"
        f"  Core Stats - {core_stats}\n"
        f"  Weapon DMG:{stats['weapon_damage']}  "
        f"Armor:{stats['armor']}  Resist:{stats['resist']}\n"
        f"  Extras     - {extras_str}\n"
        f"  Gear       - {gear}\n"
        f"  Skills     - {skills}\n"      # ← NEW line
    )


def fresh_copies():
    """Deep-copy the combatants so each trial starts with full HP and no RNG bias."""
    return deepcopy(COMBATANT_ONE), deepcopy(COMBATANT_TWO)

# ─────────────────────────────────────────────────────────────────────────────
# SINGLE DETAILED BATTLE
# ─────────────────────────────────────────────────────────────────────────────
if SINGLE_BATTLE:
    # Show combatant sheets first
    print("=== Combatant Load-out ===")
    print(snapshot(COMBATANT_ONE))
    print(snapshot(COMBATANT_TWO))

    # Decide the seed: deterministic if USE_SEED, otherwise fresh entropy
    seed = SEED_BASE if USE_SEED else random.SystemRandom().randrange(2**32)
    print(f"\n[INFO] Seed for this encounter: {seed}")

    # Run the duel
    p1, p2 = fresh_copies()
    encounter = CombatEncounter(p1, p2, seed=seed)
    winner = encounter.run_full_battle()

    # Show full turn-by-turn log + winner
    print("\n" + encounter.summary())

# ─────────────────────────────────────────────────────────────────────────────
# AGGREGATED MONTE-CARLO BATTLES
# ─────────────────────────────────────────────────────────────────────────────
else:
    wins_one, wins_two, draws = 0, 0, 0
    rounds: list[int] = []

    for n in range(NUM_TRIALS):
        # One distinct seed per encounter → repeatable yet independent streams.
        seed = (SEED_BASE + n) if USE_SEED else None

        p1, p2 = fresh_copies()
        encounter = CombatEncounter(p1, p2, seed=seed)
        victor    = encounter.run_full_battle()

        rounds.append(encounter.round)
        if victor is p1:
            wins_one += 1
        elif victor is p2:
            wins_two += 1
        else:
            draws += 1

    # ── Aggregate report ──────────────────────────────────────────────────
    print("=== Aggregated Results ===")
    print(snapshot(COMBATANT_ONE))
    print(snapshot(COMBATANT_TWO))

    print(
        f"""Trials run            : {NUM_TRIALS}
{COMBATANT_ONE.name} wins   : {wins_one}  ({wins_one/NUM_TRIALS*100:.1f}%)
{COMBATANT_TWO.name} wins   : {wins_two}  ({wins_two/NUM_TRIALS*100:.1f}%)
Draws                 : {draws}
Average rounds/fight  : {mean(rounds):.2f}
Shortest / Longest    : {min(rounds)} / {max(rounds)} rounds"""
    )