from src.learned_scorer import score as learned_score

# ---- rules / helpers ----

DEFAULT_BUCKET_TARGETS = {
    "lands": 37,
    "ramp": 10,
    "draw": 10,
    "removal": 9,
    "interaction": 5,
    "finishers": 2,
    "creatures": 28,  # aim ~26–32 creatures depending on archetype
}

def desired_land_count(avg_cmc: float, ramp_count: int) -> int:
    """Heuristic for land count based on curve + ramp."""
    base = 36
    if avg_cmc >= 3.4: base += 2
    if avg_cmc <= 2.6: base -= 2
    # Adjust by ramp
    if ramp_count >= 10: base -= 2
    elif ramp_count <= 6: base += 2
    return max(32, min(39, base))

def bucket_of(card):
    """
    Very simple bucket classifier from tags/type_line.
    You can expand this later for better accuracy.
    """
    tl = (card.get("type_line") or "")
    tags = set(card.get("tags") or [])

    if "Land" in tl:
        return "lands"
    if "Artifact" in tl and "Mana" in (card.get("oracle_text") or ""):
        return "ramp"
    if "ramp" in tags:
        return "ramp"
    if "draw" in tags or "draw a card" in (card.get("oracle_text") or "").lower():
        return "draw"
    if "removal" in tags or "destroy target" in (card.get("oracle_text") or "").lower():
        return "removal"
    if "counter target" in (card.get("oracle_text") or "").lower():
        return "interaction"
    if "Creature" in tl:
        return "creatures"
    return None


def pick_for_bucket_ranked(cmdr, pool, bucket, need, used):
    # gather candidates for this bucket
    cands = []
    for c in pool:
        if c["name"] in used:
            continue
        # bucket filter
        if bucket == "creatures":
            if "Creature" not in (c.get("type_line") or ""):
                continue
        else:
            b = bucket_of(c)
            if b != bucket and not (bucket == "finishers" and b is None):
                continue
        cands.append(c)

    # rank by learned score (commander-aware). fallback tie-breaker: lower cmc first
    scored = []
    cname = cmdr["name"]
    for c in cands:
        s = learned_score(cname, c["name"])
        cmc = c.get("cmc") or 10.0
        scored.append((s, -float(cmc), c))
    scored.sort(reverse=True, key=lambda t: (t[0], t[1]))

    picks = []
    for s, _negcmc, c in scored:
        picks.append(c)
        used.add(c["name"])
        if len(picks) >= need:
            break
    return picks
