# src/builder.py
from __future__ import annotations
import pathlib, orjson
from collections import Counter

from src.rules import (
    DEFAULT_BUCKET_TARGETS, within_color_identity, legal_in_commander,
    bucket_of, average_cmc,
)
from src.retrieve import search as retrieve

BASICS = {"Forest", "Island", "Swamp", "Mountain", "Plains", "Wastes"}

def is_basic(card):
    return card.get("name") in BASICS

def basics_for_ci(ci):
    # choose basics based on color identity
    ci = set(ci or [])
    order = []
    if "G" in ci: order.append("Forest")
    if "U" in ci: order.append("Island")
    if "W" in ci: order.append("Plains")
    if "B" in ci: order.append("Swamp")
    if "R" in ci: order.append("Mountain")
    if not order: order = ["Wastes"]
    return order


DATA = pathlib.Path("data")
CARDS = DATA / "cards.jsonl"

# --- Load all cards once ---
_cards = [orjson.loads(line) for line in CARDS.read_bytes().splitlines()]
_name_to_card = {c["name"]: c for c in _cards}

def resolve_commander(name):
    c = _name_to_card.get(name)
    if not c:
        raise SystemExit("Commander '{}' not found in your pool (data/bulk.csv).".format(name))
    return c

def filter_pool_for_commander(cmdr):
    ci = cmdr.get("color_identity") or []
    out = []
    for c in _cards:
        if c["name"] == cmdr["name"]:
            continue
        if not legal_in_commander(c):
            continue
        if not within_color_identity(c, ci):
            continue
        if int(c.get("quantity") or 1) < 1:
            continue
        out.append(c)
    return out

def pick_for_bucket(cmdr, pool, bucket, need, used):
    """Retrieve semantically, but only accept cards that our simple bucket rules agree with."""
    picks = []
    hints = []
    txt = (cmdr.get("oracle_text") or "").lower()
    if "counter" in txt:
        hints.append("counters")
    if "token" in txt:
        hints.append("tokens")

    tries = 0
    while len(picks) < need and tries < 5:
        q = "{} for {} commander; low cmc; synergy: {}".format(
            bucket, "".join(cmdr.get("color_identity") or []), ",".join(hints)
        )
        for cand, score in retrieve(q, k=40):
            if cand["name"] in used:
                continue
            if cand not in pool:
                continue
            b = bucket_of(cand)
            if b == bucket or (bucket == "finishers" and b is None):
                picks.append(cand)
                used.add(cand["name"])
                if len(picks) >= need:
                    break
        tries += 1
        if len(picks) < need and tries >= 5:
            break
    return picks

def pick_lands(cmdr, pool, desired, used):
    # 1) grab all nonbasic lands in-color
    nonbasics = [c for c in pool if "Land" in (c.get("type_line") or "") and not is_basic(c)]
    picks = []

    for c in nonbasics:
        if c["name"] in used:
            continue
        picks.append(c)
        used.add(c["name"])
        if len(picks) >= desired:
            return picks

    # 2) fill with basics, allowing multiples
    basic_names = basics_for_ci(cmdr.get("color_identity") or [])
    # fetch a template card obj for each basic we have in the pool (or all cards list)
    basic_objs = []
    for bn in basic_names:
        c = _name_to_card.get(bn)
        if c:
            basic_objs.append(c)

    if not basic_objs:
        # nothing to add (unlikely if you listed at least one basic)
        return picks

    i = 0
    while len(picks) < desired:
        picks.append(basic_objs[i % len(basic_objs)])
        # NOTE: do NOT add basics to "used" so they can repeat
        i += 1

    return picks


def build(commander_name):
    cmdr = resolve_commander(commander_name)
    pool = filter_pool_for_commander(cmdr)
    targets = DEFAULT_BUCKET_TARGETS.copy()

    used = set([cmdr["name"]])
    buckets = dict((k, []) for k in targets.keys())

    # non-land buckets first
    for b in ["ramp", "draw", "removal", "interaction", "finishers"]:
        need = targets.get(b, 0)
        if need <= 0:
            continue
        picks = pick_for_bucket(cmdr, pool, b, need, used)
        buckets[b] = picks

    # lands depend on how many we already have
    nonland_count = sum(len(v) for k, v in buckets.items() if k != "lands") + 1  # + commander
    desired_lands = max(35, 100 - nonland_count)
    buckets["lands"] = pick_lands(cmdr, pool, desired_lands, used)

    # flatten
    deck = [cmdr] + [c for k, v in buckets.items() for c in v]

    # Adjust to exactly 100 by trimming extra non-critical picks or adding basics if short
    if len(deck) > 100:
        deck = deck[:100]
    elif len(deck) < 100:
        extra = 100 - len(deck)
        buckets["lands"] += pick_lands(cmdr, pool, extra, used)
        deck = [cmdr] + [c for k, v in buckets.items() for c in v]
        deck = deck[:100]
        # top up with more basics
        need = 100 - len(deck)
        extra_basics = pick_lands(cmdr, [], need, used=set())  # only basics
        deck += extra_basics[:need]


    return {"commander": [cmdr], "buckets": buckets, "deck": deck}

def summarize(deck):
    tags = Counter()
    for c in deck:
        for t in (c.get("tags") or []):
            tags[t] += 1
    return "Avg CMC: {:.2f} | Size: {} | Top tags: {}".format(
        average_cmc(deck), len(deck), dict(tags.most_common(5))
    )

if __name__ == "__main__":
    import sys
    commander = sys.argv[1] if len(sys.argv) > 1 else "Ezuri, Claw of Progress"
    res = build(commander)
    deck = res["deck"]
    print(summarize(deck))
    out_txt = DATA / "decklist.txt"
    with open(out_txt, "w") as f:
        for c in deck:
            f.write("1 {}\n".format(c["name"]))
    print("Wrote {}".format(out_txt))
