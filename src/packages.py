# src/packages.py
from __future__ import annotations
from typing import List, Dict, Set

# Each package is a small set of cards that form a coherent win line.
# If your pool has a subset, the builder will try to include what's present.
WINCON_PACKAGES: List[Dict] = [
    {
        "name": "Unblockable Counters Alpha",
        "cards_any": ["Herald of Secret Streams"],   # any of these helps
        "cards_all": [],                              # require all? (leave empty if not)
        "tags_hint": ["counters"],                    # boosts synergy & retrieval prompts
        "notes": "Go-wide +1/+1 counters; swing unblockable for lethal."
    },
    {
        "name": "Overrun Alpha Strike",
        "cards_any": ["Craterhoof Behemoth", "Overwhelming Stampede", "Triumph of the Hordes"],
        "cards_all": [],
        "tags_hint": ["tokens","counters"],
        "notes": "Pump the team then alpha strike."
    },
    {
        "name": "Tokens Go-Wide",
        "cards_any": ["Parallel Lives", "Doubling Season", "Anointed Procession"],
        "cards_all": [],
        "tags_hint": ["tokens"],
        "notes": "Double token production; overwhelm via numbers."
    },
    {
        "name": "Aetherflux Storm",
        "cards_any": ["Aetherflux Reservoir"],
        "cards_all": [],
        "tags_hint": ["draw","interaction"],
        "notes": "Spell chains gain life into Reservoir blast."
    },
    # Add your own packages here as you expand your pool
]

def available_packages(pool_names: Set[str]) -> List[Dict]:
    """Return packages for which at least one 'cards_any' is present AND all of 'cards_all' are present (if specified)."""
    out = []
    for p in WINCON_PACKAGES:
        any_ok = any(c in pool_names for c in p.get("cards_any", [])) if p.get("cards_any") else True
        all_ok = all(c in pool_names for c in p.get("cards_all", [])) if p.get("cards_all") else True
        if any_ok and all_ok:
            out.append(p)
    return out
