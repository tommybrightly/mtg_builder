# src/builder.py
from __future__ import annotations
import pathlib, orjson
from collections import Counter
from src.rules import (
    DEFAULT_BUCKET_TARGETS, within_color_identity, legal_in_commander,
    bucket_of, average_cmc,
)
from src.retrieve import search as retrieve
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn
from src.scoring import score_deck
from src.explain import explain_card, detect_wincons
console = Console()

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

def filter_pool_for_commander(cmdr, enforce_legality=True, enforce_color_id=True):
    ci = cmdr.get("color_identity") or []
    out = []
    for c in _cards:
        if c["name"] == cmdr["name"]:
            continue
        if enforce_legality:
            # skip banned or illegal-in-commander
            if c.get("is_banned"):
                continue
            if not legal_in_commander(c):
                continue
        if enforce_color_id:
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


def build(commander_name, enforce_legality=True, enforce_color_id=True, explain=False):
    cmdr = resolve_commander(commander_name)

    if enforce_legality:
        if cmdr.get("is_banned"):
            raise SystemExit("Commander '{}' is banned (banlist). Use --no-legality to ignore.".format(cmdr["name"]))
        if not legal_in_commander(cmdr):
            raise SystemExit("Commander '{}' is not Commander-legal. Use --no-legality to ignore.".format(cmdr["name"]))

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TimeElapsedColumn(),
        console=console,
        transient=True,
    ) as progress:

        t_filter = progress.add_task("Filtering pool…", total=None)
        pool = filter_pool_for_commander(
            cmdr,
            enforce_legality=enforce_legality,
            enforce_color_id=enforce_color_id
        )
        progress.update(t_filter, completed=1)

        targets = DEFAULT_BUCKET_TARGETS.copy()
        used = set([cmdr["name"]])
        buckets = dict((k, []) for k in targets.keys())

        # non-land buckets
        for b in ["ramp", "draw", "removal", "interaction", "finishers"]:
            need = targets.get(b, 0)
            if need <= 0:
                continue
            t_bucket = progress.add_task(f"Selecting {b} ({need})…", total=need)
            picks = []
            # pick_for_bucket will grab up to 'need' cards; we’ll advance as we go
            # simple loop to track progress by length change
            prev_len = 0
            while len(picks) < need:
                new_picks = pick_for_bucket(cmdr, pool, b, need - len(picks), used)
                if not new_picks:
                    break
                picks.extend(new_picks)
                progress.advance(t_bucket, len(picks) - prev_len)
                prev_len = len(picks)
            buckets[b] = picks
            progress.update(t_bucket, completed=need)

        # lands depend on current nonlands
        total_nonlands = sum(len(v) for k, v in buckets.items() if k != "lands") + 1  # + commander
        desired_lands = max(35, 100 - total_nonlands)
        t_lands = progress.add_task(f"Picking lands ({desired_lands})…", total=desired_lands)
        lands = pick_lands(cmdr, pool, desired_lands, used)
        buckets["lands"] = lands[:desired_lands]
        progress.update(t_lands, completed=len(buckets["lands"]))

    # flatten and adjust to 100
    deck = [cmdr] + [c for k, v in buckets.items() for c in v]
    if len(deck) > 100:
        deck = deck[:100]
    elif len(deck) < 100:
        need = 100 - len(deck)
        extra_basics = pick_lands(cmdr, [], need, used=set())
        deck += extra_basics[:need]

        # compute bucket counts for scoring
    bucket_counts = {k: len(v) for k, v in buckets.items()}
    # pick up commander tags from its text (crude)
    cmdr_tags = []
    txt = (cmdr.get("oracle_text") or "").lower()
    if "counter" in txt: cmdr_tags.append("counters")
    if "token" in txt: cmdr_tags.append("tokens")

    total_score, breakdown = score_deck(deck, bucket_counts, targets, cmdr_tags)

    # explanations + wincons
    explanations = {}
    if explain:
        for b, cards in buckets.items():
            explanations[b] = [explain_card(c, cmdr, b, use_llm=True) for c in cards[:10]]  # limit output length
    wincons = detect_wincons(deck)

    return {"commander":[cmdr], "buckets":buckets, "deck":deck, "score":total_score, "score_breakdown":breakdown, "wincons":wincons, "explanations":explanations}


def summarize(deck):
    tags = Counter()
    for c in deck:
        for t in (c.get("tags") or []):
            tags[t] += 1
    return "Avg CMC: {:.2f} | Size: {} | Top tags: {}".format(
        average_cmc(deck), len(deck), dict(tags.most_common(5))
    )

if __name__ == "__main__":
    import sys, argparse, pathlib
    p = argparse.ArgumentParser()
    p.add_argument("commander")
    p.add_argument("--no-legality", action="store_true")
    p.add_argument("--no-color-id", action="store_true")
    p.add_argument("--explain", action="store_true", help="Generate explanations and win-cons (uses Ollama if running).")
    args = p.parse_args()

    res = build(
        args.commander,
        enforce_legality=not args.no_legality,
        enforce_color_id=not args.no_color_id,
        explain=args.explain,
    )
    deck = res["deck"]
    console.print("Score: {:.2f}  ".format(res["score"]), res["score_breakdown"])
    console.print("Win-Cons:")
    for w in res["wincons"]:
        console.print(" •", w)

    # write files
    DATA = pathlib.Path("data")
    with open(DATA / "decklist.txt", "w") as f:
        for c in deck:
            f.write("1 {}\n".format(c["name"]))
    if args.explain:
        with open(DATA / "explanations.md", "w", encoding="utf-8") as f:
            f.write("# Deck Explanations\n\n")
            for b, exps in (res["explanations"] or {}).items():
                if not exps: 
                    continue
                f.write(f"## {b.title()}\n")
                for e in exps:
                    f.write(f"- {e}\n")
                f.write("\n")
        with open(DATA / "wincons.md", "w", encoding="utf-8") as f:
            f.write("# Win Conditions\n\n")
            for w in res["wincons"]:
                f.write(f"- {w}\n")
    console.rule("[bold green]Deck build complete")
    console.print("Wrote data/decklist.txt", style="green")
    if args.explain:
        console.print("Wrote data/explanations.md and data/wincons.md", style="green")

