import csv
import pathlib
import re
import sys
import time
from typing import Any, Dict, List

import orjson
import requests
from rich import print
from tqdm import tqdm

# Paths
DATA = pathlib.Path("data")
CACHE = DATA / "scryfall_cache"
CACHE.mkdir(parents=True, exist_ok=True)
OUT = DATA / "cards.jsonl"

SCRY_NAMED = "https://api.scryfall.com/cards/named"

# --- simple tagging rules ---
TAG_RULES = [
    (re.compile(r"draw (a|\d+)? card", re.I), "draw"),
    (re.compile(r"investigate", re.I), "draw"),
    (re.compile(r"search your library.*(land|basic)", re.I), "ramp"),
    (re.compile(r"add [WUBRG]", re.I), "ramp"),
    (re.compile(r"treasure token", re.I), "ramp"),
    (re.compile(r"destroy target (artifact|enchantment|creature|planeswalker|permanent)", re.I), "removal"),
    (re.compile(r"exile target", re.I), "removal"),
    (re.compile(r"counter target spell", re.I), "interaction"),
    (re.compile(r"\+1/\+1 counter", re.I), "counters"),
    (re.compile(r"token", re.I), "tokens"),
]

# Load banlist if present
BANLIST = set()
if (DATA / "banlist.txt").exists():
    BANLIST = {
        line.strip()
        for line in (DATA / "banlist.txt").read_text().splitlines()
        if line.strip()
    }


def slugify(name: str) -> str:
    """Turn card name into a safe filename."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def scryfall_lookup(name: str) -> Dict[str, Any]:
    """Fetch card details from Scryfall, cached locally."""
    cache_path = CACHE / f"{slugify(name)}.json"
    if cache_path.exists():
        return orjson.loads(cache_path.read_bytes())

    # Try exact name first, then fuzzy
    for mode in ("exact", "fuzzy"):
        resp = requests.get(SCRY_NAMED, params={mode: name}, timeout=20)
        if resp.status_code == 200:
            data = resp.json()
            cache_path.write_bytes(orjson.dumps(data))
            time.sleep(0.05)  # polite delay
            return data
    raise RuntimeError(f"Scryfall lookup failed for {name}")


def tag_oracle(oracle_text: str) -> List[str]:
    """Apply regex rules to tag card roles."""
    tags = set()
    for pat, tag in TAG_RULES:
        if pat.search(oracle_text or ""):
            tags.add(tag)
    return sorted(tags)


def main():
    bulk = DATA / "bulk.csv"
    if not bulk.exists():
        print("[red]data/bulk.csv not found[/red]")
        sys.exit(1)

    with open(bulk, newline="") as f, open(OUT, "wb") as out:
        reader = csv.DictReader(f)
        for row in tqdm(list(reader), desc="Enriching via Scryfall"):
            name = row["name"].strip()
            qty = int(row.get("quantity") or 1)

            try:
                s = scryfall_lookup(name)
            except Exception as e:
                print(f"[yellow]Warn:[/yellow] {name} lookup failed: {e}")
                continue

            rec = {
                "name": s.get("name", name),
                "quantity": qty,
                "type_line": s.get("type_line"),
                "oracle_text": s.get("oracle_text") or "",
                "cmc": s.get("cmc"),
                "color_identity": s.get("color_identity") or [],
                "legalities": s.get("legalities") or {},
                "set": s.get("set"),
                "collector_number": s.get("collector_number"),
                "is_commander_legal": s.get("legalities", {}).get("commander") == "legal",
                "tags": tag_oracle(s.get("oracle_text") or ""),
                "is_banned": (s.get("name", name) in BANLIST),  # add this line
            }


            out.write(orjson.dumps(rec))
            out.write(b"\n")

    print(f"[green]Wrote[/green] {OUT}")


if __name__ == "__main__":
    main()
