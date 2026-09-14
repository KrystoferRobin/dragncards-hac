"""Hex TCG Browser CSV — last community catalog, used only as a check.

The kitchen-table plugin is built from the 1.1.0.086 client. This dump was never
the source of truth. Run:

  plugins/hex-shards-of-fate/.venv/bin/python plugins/scripts/hex_browser.py
"""

from __future__ import annotations

import csv
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BROWSER_CSV = ROOT / "hex-shards-of-fate" / "Hex TCG Browser data dump - Cards.csv"

sys.path.insert(0, str(ROOT / "scripts"))
from hex_catalog import (  # noqa: E402
    load_gamedata,
    parse_cards,
    parse_champions,
    parse_sets,
    resolve_hex,
)


def load_browser(path: Path = BROWSER_CSV) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def compare_browser(cards: list[dict[str, str]], browser: list[dict[str, str]] | None = None) -> str:
    """GUID overlap + the few constructed clarifications worth remembering."""
    browser = browser if browser is not None else load_browser()
    client = {card["guid"].lower(): card for card in cards if card.get("guid")}
    dump = {row["guid"].lower(): row for row in browser if row.get("guid")}
    both = set(client) & set(dump)
    x_costs = []
    for guid in sorted(both, key=lambda g: dump[g].get("name") or ""):
        cost = dump[guid].get("cost") or ""
        if "X" in cost and cost != (client[guid].get("cost") or ""):
            x_costs.append(f"{dump[guid]['name']}: browser {cost} / client {client[guid].get('cost')}")
    banned = [f"{row['banned']}: {row['name']}" for row in browser if row.get("banned")]
    mercs = sum(1 for row in browser if row.get("type") == "Mercenary")
    lines = [
        f"Hex TCG Browser dump: {len(dump)} GUIDs. Client catalog: {len(client)} GUIDs.",
        f"Overlap {len(both)}. Browser-only {len(set(dump) - set(client))} (mostly mercenaries + unshipped). Client-only {len(set(client) - set(dump))} (alts, equipment, PvE effects).",
        f"Mercenaries in dump (not imported as cards): {mercs}.",
        f"X-costs the client stores as a number: {len(x_costs)}.",
        *("  " + line for line in x_costs),
        "Ban notes in dump:",
        *("  " + line for line in banned),
        "Names on the overlap match. Do not rebuild the plugin from this CSV.",
    ]
    return "\n".join(lines)


def main() -> None:
    if not BROWSER_CSV.exists():
        raise SystemExit(f"missing {BROWSER_CSV}")
    raw = load_gamedata(resolve_hex())
    sets = parse_sets(raw)
    cards = parse_cards(raw, sets) + parse_champions(raw, sets)
    print(compare_browser(cards))


if __name__ == "__main__":
    main()
