#!/usr/bin/env python3
"""
Load a ManaBox CSV -> pool.json for the builder.

Expected CSV headers include (case-insensitive):
  Name, Scryfall ID, Quantity, Set code, ...

We strongly recommend using Scryfall's bulk "default_cards.json" locally:
  1) curl -L https://api.scryfall.com/bulk-data/default_cards -o default_cards_meta.json
  2) python - <<'PY'
import json, requests
meta=json.load(open("default_cards_meta.json"))
import requests, sys
r=requests.get(meta["download_uri"], timeout=120); open("default_cards.json","wb").write(r.content)
print("Wrote default_cards.json")
PY

Usage:
  python tools/load_bulk_csv.py --csv data/my_bulk.csv --scry data/default_cards.json --out data/pool.json
"""
import argparse, csv, json, pathlib, sys

def norm(s): return (s or "").strip()

def load_scryfall_bulk(path):
    cards = json.load(open(path, "r", encoding="utf-8"))
    by_id = {c.get("id"): c for c in cards if c.get("id")}
    by_name = {}
    for c in cards:
        name = c.get("name")
        if not name: continue
        # prefer latest printing for a name if duplicates
        if name not in by_name:
            by_name[name] = c
    return by_id, by_name

def row_get(row, *candidates):
    # case-insensitive lookup across several possible column names
    for key in row.keys():
        lk = key.strip().lower()
        for cand in candidates:
            if lk == cand.lower():
                return row[key]
    return None

def load_bulk_csv(csv_path, scry_by_id, scry_by_name, limit=None):
    pool = []
    seen_names = set()

    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        r = csv.DictReader(f)
        if not r.fieldnames:
            print("[error] CSV appears to have no header row.")
            sys.exit(2)

        for i, row in enumerate(r, 1):
            if limit and len(pool) >= limit:
                break

            name = norm(row_get(row, "Name", "Card Name", "Card"))
            scry_id = norm(row_get(row, "Scryfall ID", "ScryfallID", "scryfall_id"))
            if not name and not scry_id:
                continue

            sc = None
            if scry_id and scry_id in scry_by_id:
                sc = scry_by_id[scry_id]
            else:
                # fallback by name if no ID
                sc = scry_by_name.get(name)

            if not sc:
                # couldn’t resolve; skip quietly (or print a warning)
                # print(f"[warn] could not resolve: {name or scry_id}")
                continue

            card_name = sc.get("name") or name
            if card_name in seen_names:
                continue
            seen_names.add(card_name)

            pool.append({
                "name": card_name,
                "type_line": sc.get("type_line", ""),
                "cmc": sc.get("cmc", 0),
                "oracle_text": sc.get("oracle_text", "") or "",
                "color_identity": sc.get("color_identity", []),
                "tags": [],  # optional; you can fill later from your ingest/tags
            })

    return pool

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True, help="Path to your ManaBox-exported CSV")
    ap.add_argument("--scry", required=True, help="Path to Scryfall default_cards.json")
    ap.add_argument("--out", default="data/pool.json", help="Where to write the pool JSON")
    ap.add_argument("--limit", type=int, default=None, help="Limit for quick testing")
    args = ap.parse_args()

    out_path = pathlib.Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    scry_by_id, scry_by_name = load_scryfall_bulk(args.scry)
    pool = load_bulk_csv(args.csv, scry_by_id, scry_by_name, limit=args.limit)

    print(f"[ok] resolved {len(pool)} unique cards from {args.csv}")
    # Show a couple examples so you see it's working
    for c in pool[:5]:
        print("  -", c["name"], "|", c["type_line"], "| cmc:", c["cmc"])

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(pool, f, ensure_ascii=False)
    print(f"[ok] wrote pool -> {out_path}")

if __name__ == "__main__":
    main()
