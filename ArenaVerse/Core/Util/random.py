\"\"\"playfantasia.core.util.random
================================
Single choke‑point wrapper around Python’s `random.Random`.

Why bother?

*  **Deterministic replays** – Gameplay passes in a seeded Random so we can
   reproduce battles bit‑for‑bit.
*  **Easy future swap** – If we need a faster RNG or PCG32, we update one file.

Only two helpers are exposed for now: `rng_bool` and `rng_float`.
\"\"\"

from __future__ import annotations
import random
from typing import Any

# ---------------------------------------------------------------------------#
# Public helpers
# ---------------------------------------------------------------------------#
def rng_bool(rnd: \"random.Random\", p: float) -> bool:
    \"\"\"Return *True* with probability **p** (0 ≤ p ≤ 1).\"\"\"
    if p <= 0.0:
        return False
    if p >= 1.0:
        return True
    return rnd.random() < p


def rng_float(rnd: \"random.Random\", a: float, b: float) -> float:
    \"\"\"Uniform float in the closed range [a, b].\"\"\"
    return rnd.uniform(a, b)


# ---------------------------------------------------------------------------#
# Emergency global RNG (non‑deterministic).  Gameplay logic should **not**
# rely on this; it's only for dev tools or colourful debug prints.
# ---------------------------------------------------------------------------#
DEFAULT_RNG = random.Random()