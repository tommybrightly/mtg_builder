from src.learned_scorer import score as learned_score
from tools.load_bulk_csv import load_bulk_csv

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

# ---------- more helpers ----------

def average_cmc(cards):
    vals = [c.get("cmc") for c in cards if isinstance(c.get("cmc"), (int, float))]
    return (sum(vals) / len(vals)) if vals else 0.0

def pick_lands(cmdr, pool, n, used):
    """Very simple land picker: take on-color lands from pool (nonbasics first), cap at n."""
    ci = set(cmdr.get("color_identity") or [])
    def on_color(c):
        return set(c.get("color_identity") or []).issubset(ci)
    lands = [c for c in pool if "Land" in (c.get("type_line") or "") and c["name"] not in used and on_color(c)]
    # prefer nonbasics first, then basics; within each, stable order by name
    nonbasics = [c for c in lands if "Basic" not in (c.get("type_line") or "")]
    basics = [c for c in lands if "Basic" in (c.get("type_line") or "")]
    picks = nonbasics + basics
    out = []
    for c in picks:
        if len(out) >= n: break
        used.add(c["name"])
        out.append(c)
    return out

def pick_best_fillers(cmdr, pool, used, need):
    """
    Fill remaining slots with best nonland cards.
    Preference: creatures > draw > removal > interaction > finishers > misc.
    """
    prefer = ["creatures", "draw", "removal", "interaction", "finishers", None]
    buckets = {k: [] for k in prefer}
    for c in pool:
        if c["name"] in used: continue
        if "Land" in (c.get("type_line") or ""): continue
        b = bucket_of(c)
        if "Creature" in (c.get("type_line") or ""): b = "creatures"
        if b not in buckets: b = None
        buckets[b].append(c)

    # light sorting: cheaper first inside each bucket
    for k in buckets:
        buckets[k].sort(key=lambda c: (float(c.get("cmc") or 10.0), c.get("name","")))

    out = []
    for k in prefer:
        for c in buckets.get(k, []):
            if len(out) >= need: break
            used.add(c["name"]); out.append(c)
        if len(out) >= need: break
    return out

# ---------- main builder ----------

def build_deck(cmdr, pool):
    """
    cmdr: dict for the commander (must include name, color_identity, type_line,...)
    pool: list[dict] of candidate cards (your bulk) with fields used above
    returns: list[dict]  ->  [commander] + 99 cards
    """
    used = set([cmdr["name"]])
    buckets = {}
    targets = DEFAULT_BUCKET_TARGETS.copy()

    # 1) non-land buckets, creatures first
    for b in ["creatures", "ramp", "draw", "removal", "interaction", "finishers"]:
        need = max(0, targets.get(b, 0) - len(buckets.get(b, [])))
        if need <= 0: 
            buckets[b] = buckets.get(b, [])
            continue

        picks = pick_for_bucket_ranked(cmdr, pool, b, need, used)
        buckets[b] = buckets.get(b, []) + picks

    # 2) lands target from curve + ramp count
    nonlands = [c for k, v in buckets.items() if k != "lands" for c in v]
    avg = average_cmc([c for c in nonlands if "Land" not in (c.get("type_line") or "")])
    ramp_ct = len(buckets.get("ramp", []))
    lands_target = desired_land_count(avg, ramp_ct)
    buckets["lands"] = pick_lands(cmdr, pool, lands_target, used)[:lands_target]

    # 3) flatten and adjust to 100 (do NOT add more lands)
    deck = [cmdr] + [c for k, v in buckets.items() for c in v]
    if len(deck) < 100:
        need = 100 - len(deck)
        fillers = pick_best_fillers(cmdr, pool, used, need)
        deck += fillers[:need]
    elif len(deck) > 100:
        deck = deck[:100]

    return deck

# ---------- optional CLI (requires your own loader) ----------

if __name__ == "__main__":
    import sys, json, os
    if len(sys.argv) < 2:
        print("Usage: python -m src.builder \"Commander Name\" [path\\to\\pool.json]")
        sys.exit(1)

    commander_name = sys.argv[1]
    pool_path = sys.argv[2] if len(sys.argv) >= 3 else os.path.join("data", "pool.json")

    try:
        pool = json.load(open(pool_path, "r", encoding="utf-8"))
    except FileNotFoundError:
        print(f"[error] Pool not found: {pool_path}. Generate it with tools\\load_bulk_csv.py.")
        sys.exit(2)

    # Try to find the commander in your bulk; if not present, use a minimal stub.
    cmdr = next((c for c in pool if c.get("name") == commander_name), None)
    if not cmdr:
        print(f"[warn] '{commander_name}' not found in pool; using minimal stub (color identity empty).")
        cmdr = {"name": commander_name, "color_identity": [], "type_line": "Legendary Creature", "cmc": 0}

    deck = build_deck(cmdr, pool)

    # Write a simple .txt decklist (1 copy of each)
    safe = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in commander_name)
    outpath = os.path.join("data", f"deck_{safe}.txt")
    with open(outpath, "w", encoding="utf-8") as f:
        for c in deck:
            f.write(f"1 {c['name']}\n")

    print(f"[ok] Built deck for {commander_name}: {len(deck)} cards")
    print(f"[ok] Wrote decklist -> {outpath}")



