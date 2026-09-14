"""Shared Game-Set-Cardname path helpers for Toybox image hosting.

Host nginx maps /cards/ onto the images/ tree (see compose.yml). Plugin TSV /
cardBack paths stay {game}/{set}/{Game}-{Set}-{Cardname}.ext — do not put
cards/ in those relative paths. The frontend prepends /cards/ when a path
does not already start with / or http, so plugins do not store a host.

Token / background / lobby URLs are same-origin /cards/... paths.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlparse


TOYBOX_PREFIX = "/cards/"


def folder_slug(name: str) -> str:
    cleaned = (name or "").replace("'", "").replace("\u2019", "")
    cleaned = re.sub(r"[^A-Za-z0-9]+", "-", cleaned).strip("-").lower()
    return cleaned or "set"


def pascal(name: str) -> str:
    cleaned = (name or "").replace("'", "").replace("\u2019", "")
    parts = re.sub(r"[^A-Za-z0-9]+", " ", cleaned).split()
    if not parts:
        return "Card"
    return "".join(part[:1].upper() + part[1:] for part in parts)


def card_rel_path(game_folder: str, game_pascal: str, set_name: str, card_name: str, ext: str) -> str:
    if not ext.startswith("."):
        ext = f".{ext}"
    ext = ext.lower()
    if ext == ".jpeg":
        ext = ".jpg"
    set_folder = folder_slug(set_name)
    stem = f"{game_pascal}-{pascal(set_name)}-{pascal(card_name)}"
    return f"{game_folder}/{set_folder}/{stem}{ext}"


def plugin_art_rel(game_folder: str, game_pascal: str, label: str, ext: str) -> str:
    if not ext.startswith("."):
        ext = f".{ext}"
    ext = ext.lower()
    return f"{game_folder}/_plugin/{game_pascal}-{pascal(label)}{ext}"


def lobby_art_rel(game_folder: str, kind: str) -> str:
    """Literal lobby filenames: {game}/_plugin/banner2.jpg or logo2.jpg."""
    kind = (kind or "").strip().lower()
    if kind in {"banner", "banner2"}:
        filename = "banner2.jpg"
    elif kind in {"logo", "logo2"}:
        filename = "logo2.jpg"
    else:
        raise ValueError(f"lobby art kind must be banner or logo, got {kind!r}")
    return f"{game_folder}/_plugin/{filename}"


def lobby_art_urls(game_folder: str) -> dict[str, str]:
    return {
        "bannerUrl": toybox_url(lobby_art_rel(game_folder, "banner")),
        "logoUrl": toybox_url(lobby_art_rel(game_folder, "logo")),
    }


def apply_lobby_art(payload: dict, game_folder: str) -> dict:
    payload.update(lobby_art_urls(game_folder))
    return payload


def stamp_lobby_art(jsons_dir: Path, game_folder: str) -> None:
    """Write bannerUrl / logoUrl into main.json without clobbering other keys."""
    path = Path(jsons_dir) / "main.json"
    payload: dict = {}
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
    apply_lobby_art(payload, game_folder)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def ext_from_url(url: str, default: str = ".jpg") -> str:
    path = Path(url.split("?", 1)[0])
    suffix = path.suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg"}:
        return ".jpg" if suffix == ".jpeg" else suffix
    return default


def toybox_url(rel: str) -> str:
    rel = (rel or "").replace("\\", "/").lstrip("/")
    if rel.startswith("cards/"):
        rel = rel[len("cards/") :]
    return TOYBOX_PREFIX + rel


def rewrite_toybox_url(url: str) -> str:
    """Turn an absolute Toybox /cards/ URL into a same-origin path. Leave other hosts alone."""
    url = (url or "").strip()
    if not url:
        return url
    parsed = urlparse(url)
    host = (parsed.netloc or "").lower()
    if parsed.scheme not in {"http", "https"} or "toybox" not in host:
        return url
    rest = parsed.path.lstrip("/")
    if rest.startswith("cards/"):
        rest = rest[len("cards/") :]
    return TOYBOX_PREFIX + rest


def clear_image_url_prefix(jsons_dir: Path) -> None:
    """Plugins rely on the frontend /cards/ default; do not store a host prefix."""
    path = Path(jsons_dir) / "imageUrlPrefix.json"
    try:
        path.unlink()
    except FileNotFoundError:
        pass
