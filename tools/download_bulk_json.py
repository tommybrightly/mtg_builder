import json, urllib.request

# read the meta file
with open(r".\data\default_cards_meta.json", encoding="utf-8") as f:
    meta = json.load(f)

url = meta["download_uri"]
print("Downloading from:", url)

# fetch the full default_cards.json (~70 MB)
outfile = r".\data\default_cards.json"
urllib.request.urlretrieve(url, outfile)

print("Wrote", outfile)