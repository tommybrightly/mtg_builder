# tools/load_bulk_csv.py
import csv, requests

def load_bulk_csv(path):
    pool = []
    with open(path, newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            name = row["Name"].strip()
            scry_id = row.get("Scryfall ID")
            if not name:
                continue
            # fetch details from Scryfall
            if scry_id:
                url = f"https://api.scryfall.com/cards/{scry_id}"
                resp = requests.get(url)
                if resp.status_code == 200:
                    card = resp.json()
                    pool.append({
                        "name": card["name"],
                        "type_line": card.get("type_line",""),
                        "cmc": card.get("cmc", 0),
                        "oracle_text": card.get("oracle_text",""),
                        "color_identity": card.get("color_identity",[]),
                        "tags": [],
                    })
    return pool
