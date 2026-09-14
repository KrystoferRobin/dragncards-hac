"""Pull LoN Fandom card pages + portrait art (lon.fandom.com)."""

from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

API = "https://lon.fandom.com/api.php"
UA = "Toybox-LoN/1.0 (private kitchen-table plugin; +https://lon.fandom.com)"
SKIP_NAME = re.compile(r"(icon|inline|oathbound|forsworn|logo|template|wiki)", re.I)
SET_ALIASES = {
    "oathbound": "Oathbound",
    "forsworn": "Forsworn",
    "inquisitor": "Inquisitor",
    "oathbreaker": "Oathbreaker",
    "ethernauts": "Ethernauts",
    "against the void": "Against the Void",
    "storm break": "Storm Break",
    "travelers": "Travelers",
    "vengeful gods": "Vengeful Gods",
    "doom of the ancient ones": "Doom of the Ancient Ones",
    "dragonbrood": "Dragonbrood",
    "legacies": "Legacies",
    "priestess of the anarchs": "Priestess of the Anarchs",
    "fall of the estarim": "Fall of the Estarim",
    "debt of the ratonga": "Debt of the Ratonga",
    "drakkinshard": "Drakkinshard",
}


def norm(value: str) -> str:
    text = (value or "").casefold()
    text = re.sub(r"[^a-z0-9]+", "", text)
    return text


def get(params: dict) -> dict:
    query = urllib.parse.urlencode(params)
    req = urllib.request.Request(API + "?" + query, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=45) as resp:
        return json.loads(resp.read().decode())


def parse_cardinformation(text: str) -> dict[str, str]:
    match = re.search(r"\{\{CardInformation\|(.*)\n\}\}", text or "", re.S)
    if not match:
        return {}
    fields: dict[str, str] = {}
    for line in match.group(1).splitlines():
        line = line.split("<!--", 1)[0].strip().rstrip("|").strip()
        if "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip().lower()
        val = re.sub(r"\s+", " ", val).strip()
        val = re.sub(r"\{\{[^}]+\}\}", "", val).strip()
        fields[key] = val
    return fields


def list_card_titles() -> list[str]:
    titles: list[str] = []
    cont = None
    while True:
        params = {
            "action": "query",
            "list": "categorymembers",
            "cmtitle": "Category:Cards",
            "cmlimit": "500",
            "format": "json",
        }
        if cont:
            params["cmcontinue"] = cont
        data = get(params)
        titles.extend(m["title"] for m in data["query"]["categorymembers"] if m.get("ns") == 0)
        cont = (data.get("continue") or {}).get("cmcontinue")
        if not cont:
            break
        time.sleep(0.12)
    return titles


def fetch_pages(titles: list[str]) -> list[dict]:
    rows: list[dict] = []
    for index in range(0, len(titles), 25):
        batch = titles[index : index + 25]
        data = get(
            {
                "action": "query",
                "prop": "revisions|images",
                "rvprop": "content",
                "titles": "|".join(batch),
                "format": "json",
            }
        )
        for page in data.get("query", {}).get("pages", {}).values():
            text = ""
            revs = page.get("revisions") or []
            if revs:
                text = revs[0].get("*") or ""
            rows.append(
                {
                    "title": page.get("title") or "",
                    "fields": parse_cardinformation(text),
                    "images": [im["title"].removeprefix("File:") for im in page.get("images") or []],
                }
            )
        time.sleep(0.12)
    return rows


def list_images() -> list[dict]:
    images: list[dict] = []
    cont = None
    while True:
        params = {"action": "query", "list": "allimages", "ailimit": "500", "aiprop": "url|size|mime", "format": "json"}
        if cont:
            params["aicontinue"] = cont
        data = get(params)
        images.extend(data["query"]["allimages"])
        cont = (data.get("continue") or {}).get("aicontinue")
        if not cont:
            break
        time.sleep(0.12)
    return images


def is_portrait(image: dict) -> bool:
    name = image.get("name") or ""
    if SKIP_NAME.search(name):
        return False
    width = int(image.get("width") or 0)
    height = int(image.get("height") or 0)
    if width < 180 or height < 180:
        return False
    if height >= 400 or (height > 350 and width / height < 0.78):
        return False
    return True


def image_key(name: str) -> str:
    stem = Path(name).stem
    stem = re.sub(r"[_-]+", " ", stem)
    stem = re.sub(r"\s+EN$", "", stem, flags=re.I)
    return norm(stem)


def pretty_set(value: str) -> str:
    raw = (value or "").split("|")[0].strip()
    return SET_ALIASES.get(raw.casefold(), raw)


def load_or_fetch(cache_dir: Path, refresh: bool = False) -> dict:
    cache_dir.mkdir(parents=True, exist_ok=True)
    catalog_path = cache_dir / "catalog.json"
    if catalog_path.exists() and not refresh:
        return json.loads(catalog_path.read_text(encoding="utf-8"))
    print("Fetching lon.fandom.com Category:Cards …")
    titles = list_card_titles()
    pages = fetch_pages(titles)
    images = list_images()
    catalog = {"pages": pages, "images": images}
    catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
    print(f"  wiki pages {len(pages)}  images {len(images)}")
    return catalog


def download_portraits(catalog: dict, dest: Path) -> dict[str, Path]:
    dest.mkdir(parents=True, exist_ok=True)
    found: dict[str, Path] = {}
    portraits = [img for img in catalog.get("images") or [] if is_portrait(img)]
    for image in portraits:
        key = image_key(image["name"])
        if not key:
            continue
        ext = Path(image["name"]).suffix.lower() or ".png"
        path = dest / f"{key}{ext}"
        if not path.exists():
            req = urllib.request.Request(image["url"], headers={"User-Agent": UA})
            try:
                path.write_bytes(urllib.request.urlopen(req, timeout=45).read())
                time.sleep(0.08)
            except Exception as exc:
                print(f"  wiki art fail {image['name']}: {exc}")
                continue
        found.setdefault(key, path)
    return found


def _digits(value: str) -> str:
    return re.sub(r"[^0-9]", "", value or "")


def _page_for(card: dict, by_name: dict[str, list[dict]]) -> dict | None:
    hits = by_name.get(norm(card.get("name") or "")) or []
    if not hits:
        return None
    typ = (card.get("type") or "").casefold()
    typed = [row for row in hits if (row.get("fields") or {}).get("cardtype", "").casefold() == typ]
    return (typed or hits)[0]


def apply_wiki(cards: list[dict], catalog: dict, art: dict[str, Path]) -> dict:
    by_name: dict[str, list[dict]] = {}
    for row in catalog.get("pages") or []:
        if row.get("title"):
            by_name.setdefault(norm(row["title"]), []).append(row)
    matched = 0
    filled_cost = filled_set = filled_trait = filled_arch = overwritten_stats = 0
    art_hits = 0
    mismatches: list[str] = []
    for card in cards:
        key = norm(card.get("name") or "")
        wiki_art = art.get(key)
        if wiki_art:
            card["wikiArt"] = str(wiki_art)
            art_hits += 1
        page = _page_for(card, by_name)
        if not page:
            continue
        matched += 1
        fields = page.get("fields") or {}
        wiki_type = (fields.get("cardtype") or "").casefold()
        same_type = not wiki_type or wiki_type == (card.get("type") or "").casefold()
        if fields.get("cost") and (not card.get("cost") or same_type):
            card["cost"] = _digits(fields["cost"]) or fields["cost"]
            filled_cost += 1
        if fields.get("trait") and (not card.get("faction") or same_type):
            card["faction"] = fields["trait"]
            filled_trait += 1
        if fields.get("archetype") and not card.get("archetype"):
            card["archetype"] = fields["archetype"]
            filled_arch += 1
        wiki_set = pretty_set(fields.get("expansion") or "")
        if wiki_set in SET_ALIASES.values() and (not card.get("packName") or card.get("packName") == "Norrath"):
            card["packName"] = wiki_set
            filled_set += 1
        if same_type:
            wiki_atk = _digits(fields.get("attack") or "")
            if wiki_atk:
                if card.get("attack") and str(card["attack"]) != wiki_atk:
                    mismatches.append(f"{card['name']} {card.get('type')}: dump ATK {card.get('attack')} -> wiki {wiki_atk}")
                card["attack"] = wiki_atk
                overwritten_stats += 1
            wiki_def = _digits(fields.get("defense") or "")
            if wiki_def:
                card["defense"] = wiki_def
            wiki_hp = _digits(fields.get("health") or "")
            if wiki_hp:
                card["health"] = wiki_hp
            wiki_dmg = _digits(fields.get("dmgbonus") or "")
            if wiki_dmg:
                card["damage"] = wiki_dmg
    return {
        "wiki_pages": len(by_name),
        "matched": matched,
        "art": art_hits,
        "filled_cost": filled_cost,
        "filled_set": filled_set,
        "filled_trait": filled_trait,
        "filled_arch": filled_arch,
        "overwritten_stats": overwritten_stats,
        "atk_mismatches": len(mismatches),
        "mismatch_samples": mismatches[:20],
        "wiki_sets": dict(Counter(pretty_set((row.get("fields") or {}).get("expansion") or "") or "?" for row in catalog.get("pages") or [])),
    }
