#!/usr/bin/env python3
"""Cache public AEG L5R decklists from L5R DB (l5rdb.vercel.app).

The site is a NetrunnerDB-style Next app over a public Supabase. We discover
the published anon key from their frontend (same one the browser uses) and
page through public decks / cards / deck_cards.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

USER_AGENT = "HundredAcreClub/1.0 (private tabletop collect; +https://hundredacre.club)"
L5RDB_ORIGIN = "https://l5rdb.vercel.app"
PAGE = 1000


def _fetch(url: str, headers: dict[str, str] | None = None) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    with urllib.request.urlopen(req, timeout=45) as resp:
        return resp.read()


def discover_client() -> tuple[str, str]:
    html = _fetch(L5RDB_ORIGIN + "/").decode("utf-8", "replace")
    chunks = re.findall(r'src="(/_next/static/chunks/[^"]+)"', html)
    supabase = ""
    anon = ""
    for path in chunks:
        js = _fetch(L5RDB_ORIGIN + path).decode("utf-8", "replace")
        if "supabase.co" not in js and "eyJ" not in js:
            continue
        urls = re.findall(r"https://[a-z0-9]+\.supabase\.co", js)
        keys = re.findall(r"eyJ[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{10,}", js)
        if urls:
            supabase = urls[0]
        if keys:
            anon = keys[0]
        if supabase and anon:
            return supabase, anon
    raise RuntimeError("Could not discover L5R DB public API credentials from the site JS.")


def rest_pages(supabase: str, anon: str, table: str, query: str = "select=*") -> list[dict]:
    rows: list[dict] = []
    start = 0
    while True:
        url = f"{supabase}/rest/v1/{table}?{query}"
        headers = {
            "apikey": anon,
            "Authorization": f"Bearer {anon}",
            "Accept": "application/json",
            "Prefer": "count=exact",
            "Range": f"{start}-{start + PAGE - 1}",
        }
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **headers})
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                chunk = json.loads(resp.read().decode("utf-8"))
                content_range = resp.getheader("Content-Range") or ""
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"L5R DB {table} failed: {exc.read()[:240]!r}") from exc
        if not isinstance(chunk, list):
            raise RuntimeError(f"L5R DB {table} returned {type(chunk)}")
        rows.extend(chunk)
        total = None
        if "/" in content_range:
            try:
                total = int(content_range.rsplit("/", 1)[1])
            except ValueError:
                total = None
        print(f"  {table}: {len(rows)}" + (f"/{total}" if total is not None else ""), flush=True)
        if not chunk or (total is not None and len(rows) >= total) or len(chunk) < PAGE:
            break
        start += PAGE
    return rows


def load_cache(cache_dir: Path) -> dict | None:
    manifest = cache_dir / "manifest.json"
    if not manifest.exists():
        return None
    try:
        info = json.loads(manifest.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    payload = {}
    for key in ("decks", "deck_cards", "cards", "formats"):
        path = cache_dir / f"{key}.json"
        if not path.exists():
            return None
        payload[key] = json.loads(path.read_text(encoding="utf-8"))
    payload["manifest"] = info
    return payload


def save_cache(cache_dir: Path, payload: dict) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    for key, value in payload.items():
        if key == "manifest":
            continue
        (cache_dir / f"{key}.json").write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    (cache_dir / "manifest.json").write_text(
        json.dumps(payload.get("manifest") or {}, indent=2),
        encoding="utf-8",
    )


def fetch_l5rdb(cache_dir: Path, skip: bool = False) -> dict:
    cached = load_cache(cache_dir)
    if skip and cached:
        print(f"L5R DB cache: {len(cached['decks'])} decks (fetch skipped).")
        return cached
    print("Discovering L5R DB public API…")
    supabase, anon = discover_client()
    print(f"  {supabase}")
    decks = rest_pages(supabase, anon, "decks", "select=*&is_public=eq.true&order=updated_at.desc")
    deck_cards = rest_pages(supabase, anon, "deck_cards", "select=*")
    cards = rest_pages(
        supabase,
        anon,
        "cards",
        "select=id,title,formatted_title,type,clan,deck,legality",
    )
    formats = rest_pages(supabase, anon, "formats", "select=id,name,description")
    payload = {
        "decks": decks,
        "deck_cards": deck_cards,
        "cards": cards,
        "formats": formats,
        "manifest": {
            "source": L5RDB_ORIGIN,
            "decks": len(decks),
            "deck_cards": len(deck_cards),
            "cards": len(cards),
            "formats": len(formats),
        },
    }
    save_cache(cache_dir, payload)
    print(f"L5R DB cache saved: {len(decks)} public decks, {len(deck_cards)} rows.")
    return payload


if __name__ == "__main__":
    import sys

    root = Path(__file__).resolve().parents[1]
    dest = root / "LegendOfTheFiveRings" / "l5rdb"
    fetch_l5rdb(dest, skip="--skip" in sys.argv)
