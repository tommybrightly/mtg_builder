# src/llm_builder.py
import json, sys, math
from typing import List
from .io_utils import load_pool, write_decklist, write_explanations
from .rules import BUCKETS, TARGETS, desired_land_count, is_land, is_creature, within_ci
from .shortlist import shortlist

### 0) LLM call (fill this for your provider/library)
def call_llm(system_msg: str, user_msg: str) -> str:
    """
    Return the LLM string response. Keep it provider-agnostic here.
    For OpenAI-like SDKs, you'd do: client.chat.completions.create(...).
    """
    raise NotImplementedError("Wire this to your LLM provider")

JSON_INSTRUCTIONS = """
Return JSON with this schema:
{
  "picks": ["Card Name 1", "Card Name 2", ...],    // EXACTLY N names from the shortlist
  "explanation": "1 paragraph explaining your picks for this bucket and how it supports the commander.",
  "win_conditions": ["short phrase 1", "short phrase 2"] // add only if this is the 'finishers' or 'creatures' bucket, else [].
}
Only return JSON, no prose.
"""

def llm_pick(commander: dict, bucket: str, shortlist_cards: List[dict], need: int) -> dict:
    names = [c["name"] for c in shortlist_cards]
    user = f"""
Commander: {commander['name']}  (CI: {''.join(commander.get('color_identity') or [])})
Bucket: {bucket}
You must pick EXACTLY {need} cards FROM THIS SHORTLIST ONLY (do not invent names):

Shortlist:
{json.dumps(names, ensure_ascii=False, indent=2)}

{JSON_INSTRUCTIONS}
"""
    sysmsg = "You are a helpful MTG Commander deck assistant. Respect color identity and only choose from the provided shortlist."
    out = call_llm(sysmsg, user).strip()
    # robust parse
    try:
        data = json.loads(out)
        assert isinstance(data.get("picks"), list)
    except Exception:
        # fallback: pick top-N from shortlist
        data = {"picks": names[:need], "explanation": "Fallback to shortlist tops.", "win_conditions": []}
    # hard trim to shortlist & need
    allow = set(names)
    picks = [n for n in data["picks"] if n in allow][:need]
    data["picks"] = picks
    return data

def build_deck(commander_name: str, pool_path="data/pool.json"):
    pool = load_pool(pool_path)
    # try to find commander in pool; stub CI from known colors if needed
    cmdr = next((c for c in pool if c["name"] == commander_name), {"name": commander_name, "color_identity": [], "type_line": "Legendary Creature"})
    if not cmdr.get("color_identity"):
        # simple local patch: infer from known legends you run; or hardcode for tests
        KNOWN = {"Kaalia of the Vast":["W","B","R"]}
        cmdr["color_identity"] = KNOWN.get(cmdr["name"], cmdr.get("color_identity", []))

    used = set([cmdr["name"]])
    buckets = {b:[] for b in BUCKETS}
    explanations = []

    # non-lands first
    for b in ["creatures","ramp","draw","removal","interaction","finishers"]:
        need = TARGETS[b]
        sl = shortlist(cmdr, [c for c in pool if c["name"] not in used], b, k=max(need*4, 30))
        if not sl:
            continue
        data = llm_pick(cmdr, b, sl, need)
        picks = [c for c in sl if c["name"] in set(data["picks"])]
        for p in picks: used.add(p["name"])
        buckets[b] = picks
        if data.get("explanation"):
            explanations.append(f"### {b.capitalize()}\n{data['explanation']}")
        if data.get("win_conditions") and b in ("creatures","finishers"):
            explanations.append(f"- Win cons: " + "; ".join(data["win_conditions"]))

    # lands heuristic from curve + ramp
    nonlands = [c for b in BUCKETS if b!="lands" for c in buckets[b]]
    avg_cmc = (sum(float(c.get("cmc") or 0) for c in nonlands)/len(nonlands)) if nonlands else 2.8
    ramp_ct = len(buckets.get("ramp",[]))
    target_lands = desired_land_count(avg_cmc, ramp_ct)

    lands = [c for c in pool if is_land(c) and c["name"] not in used and within_ci(c, cmdr.get("color_identity"))]
    lands = lands[:target_lands]
    for p in lands: used.add(p["name"])
    buckets["lands"] = lands

    # flatten and top-up with best creatures/draw if under 100
    deck = [cmdr] + [c for b in BUCKETS for c in buckets.get(b,[])]
    if len(deck) < 100:
        need = 100 - len(deck)
        fillers = [c for c in pool if c["name"] not in used and not is_land(c) and within_ci(c, cmdr.get("color_identity"))]
        fillers.sort(key=lambda c: (0 if is_creature(c) else 1, float(c.get("cmc") or 10.0)))
        fillers = fillers[:need]
        deck += fillers

    # write files
    deck_path = write_decklist(cmdr["name"], deck, out_dir="data")
    exp_path  = write_explanations(cmdr["name"], "\n\n".join(explanations) or "Builder v1 explanations.", out_dir="data")
    return deck_path, exp_path

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print('Usage: python -m src.llm_builder "Commander Name" [pool.json]')
        sys.exit(1)
    name = sys.argv[1]
    poolp = sys.argv[2] if len(sys.argv) >= 3 else "data/pool.json"
    dp, ep = build_deck(name, poolp)
    print(f"[ok] wrote {dp}")
    print(f"[ok] wrote {ep}")
