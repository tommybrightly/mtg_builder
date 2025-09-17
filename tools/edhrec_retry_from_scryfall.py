#!/usr/bin/env python3
"""
Retry fetching EDHREC JSON only for commanders that are missing,
resolving the exact EDHREC slug via Scryfall to avoid slug mismatches.

Usage:
  python tools/edhrec_retry_from_scryfall.py --from data/datasets/edhrec_missing.txt --sleep 1.5
  # or:
  python tools/edhrec_retry_from_scryfall.py --from commanders.txt --only-missing --sleep 1.5
"""

import argparse, json, pathlib, re, time, random, urllib.parse
import requests

ROOT = pathlib.Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw_edhrec"
RAW.mkdir(parents=True, exist_ok=True)

UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
                  " AppleWebKit/537.36 (KHTML, like Gecko)"
                  " Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

SCRY_NAMED = "https://api.scryfall.com/cards/named"

def read_names(path: pathlib.Path):
    return [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]

def already_cached(name: str) -> bool:
    slug = _slugify(name)
    return (RAW / f"{slug}.json").exists()

def _slugify(name: str) -> str:
    s = name.lower()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"\s+", "-", s.strip())
    return s

def scryfall_edhrec_slug(commander_name: str) -> str:
    """Ask Scryfall for the commander and extract the EDHREC page path/slug."""
    # Try exact first, then fuzzy
    for mode in ("exact", "fuzzy"):
        r = requests.get(SCRY_NAMED, params={mode: commander_name}, headers=UA, timeout=30)
        if r.status_code == 200:
            data = r.json()
            # EDHREC page is under related_uris.edhrec, e.g. https://edhrec.com/commanders/kaalia-of-the-vast
            rel = (data.get("related_uris") or {}).get("edhrec")
            if not rel:
                # Some double-faced or special cards place EDHREC link in URIs too
                rel = data.get("edhrec_uri") or data.get("edhrec")
            if not rel:
                # Fallback: build from slugify; not perfect but better than nothing
                return _slugify(commander_name)
            # Parse the path segment after /commanders/
            try:
                path = urllib.parse.urlparse(rel).path  # /commanders/kaalia-of-the-vast
                parts = [p for p in path.split("/") if p]
                # Handle pages like /commanders/kaalia-of-the-vast or /themes/...; we only want commanders
                if "commanders" in parts:
                    idx = parts.index("commanders")
                    slug = parts[idx+1] if idx+1 < len(parts) else _slugify(commander_name)
                    return slug.lower()
            except Exception:
                return _slugify(commander_name)
    # If Scryfall couldn’t find it at all:
    return _slugify(commander_name)

def fetch_edhrec_json_by_slug(slug: str, referer_ok=True, max_retries=7, base_sleep=1.5):
    url = f"https://json.edhrec.com/pages/commanders/{slug}.json"
    cache_path = RAW / f"{slug}.json"
    if cache_path.exists():
        try:
            return json.loads(cache_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    headers = dict(UA)
    if referer_ok:
        headers["Referer"] = f"https://edhrec.com/commanders/{slug}"

    last_err = None
    for i in range(max_retries):
        try:
            r = requests.get(url, headers=headers, timeout=30)
            if r.status_code == 200:
                data = r.json()
                cache_path.write_text(json.dumps(data), encoding="utf-8")
                return data
            if r.status_code == 404:
                raise RuntimeError(f"HTTP 404 for {url}")
            if r.status_code in (403, 429, 500, 502, 503, 504):
                last_err = RuntimeError(f"HTTP {r.status_code} for {url}")
            else:
                r.raise_for_status()
        except requests.RequestException as e:
            last_err = e
        # backoff + jitter
        sleep = base_sleep * (2 ** i) + random.uniform(0.0, 0.6)
        time.sleep(min(sleep, 10.0))
    raise last_err or RuntimeError(f"Failed {url}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="src", required=True, help="Text file with commander names (one per line)")
    ap.add_argument("--only-missing", dest="only_missing", action="store_true", help="Skip names whose JSON is already cached")
    ap.add_argument("--sleep", type=float, default=1.5, help="Base sleep for backoff")
    args = ap.parse_args()

    src = pathlib.Path(args.src)
    names = read_names(src)
    ok = 0; fail = 0
    for name in names:
        if args.only_missing and already_cached(name):   # ✅ fixed attribute
            continue
        slug = scryfall_edhrec_slug(name)
        try:
            fetch_edhrec_json_by_slug(slug, base_sleep=args.sleep)
            print(f"[ok] {name}  ->  {slug}")
            ok += 1
        except Exception as e:
            print(f"[fail] {name}  ->  {slug}  : {e}")
            fail += 1
    print(f"[done] fetched: {ok}, failed: {fail}")


if __name__ == "__main__":
    main()
