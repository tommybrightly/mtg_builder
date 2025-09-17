import json
import requests
meta = json.load(open(r".\data\default_cards_meta.json", encoding="utf-8"))
url = meta["download_uri"]
r = requests.get(url, timeout=180)
open(r".\data\default_cards.json","wb").write(r.content)
print("Wrote .\\data\\default_cards.json")