import {
  loadArkhamDb,
  loadMarvelCdb,
  loadRangersDb,
  loadRingsDb,
} from "../engine/hooks/useImportViaUrl";

const noopActionList = () => {};

export const importDeckFromUrl = ({ pluginName, cardDb, onLoadList }) => {
  const url = prompt("Paste a RingsDB, ArkhamDB, arkham.build, MarvelCDB, or RangersDB URL");
  if (!url) return;

  const merge = (list) => onLoadList(list || []);
  const name = pluginName || "";

  if (name.includes("LotR Living Card Game") || url.includes("ringsdb.com")) {
    if (!url.includes("ringsdb.com")) {
      alert("Only importing from RingsDB is supported for this game.");
      return;
    }
    const domain = url.includes("test.ringsdb.com") ? "test" : "ringsdb";
    const type = url.includes("/decklist/") ? "decklist" : url.includes("/deck/") ? "deck" : null;
    if (!type) {
      alert("Invalid RingsDB URL.");
      return;
    }
    const parts = url.split("/");
    const id = parts[parts.findIndex((e) => e === type) + 2];
    return loadRingsDb(merge, noopActionList, "playerN", domain, type, id);
  }

  if (name.includes("Arkham Horror") || url.includes("arkhamdb.com") || url.includes("arkham.build")) {
    let type = null;
    let typeIndexMod = 2;
    if (url.includes("arkhamdb.com") && url.includes("/decklist/")) type = "decklist";
    else if (url.includes("arkhamdb.com") && url.includes("/deck/")) type = "deck";
    else if (url.includes("arkham.build") && url.includes("/view/")) {
      type = "view";
      typeIndexMod = 1;
    } else if (url.includes("arkham.build") && url.includes("/share/")) {
      type = "share";
      typeIndexMod = 1;
    }
    if (!type) {
      alert("Invalid ArkhamDB / arkham.build URL.");
      return;
    }
    const parts = url.split("/");
    const id = parts[parts.findIndex((e) => e === type) + typeIndexMod];
    return loadArkhamDb(merge, noopActionList, "playerN", type, id);
  }

  if (name.includes("Marvel Champions") || url.includes("marvelcdb.com")) {
    if (!url.includes("marvelcdb.com")) {
      alert("Only importing from MarvelCDB is supported for this game.");
      return;
    }
    const type = url.includes("/decklist/") ? "decklist" : url.includes("/deck/") ? "deck" : null;
    if (!type) {
      alert("Invalid MarvelCDB URL.");
      return;
    }
    const parts = url.split("/");
    const id = parts[parts.findIndex((e) => e === type) + 2];
    return loadMarvelCdb(merge, noopActionList, "playerN", "marvelcdb", type, id, cardDb);
  }

  if (name.includes("Earthborne Rangers") || url.includes("rangersdb.com")) {
    if (!url.includes("rangersdb.com")) {
      alert("Only importing from RangersDB is supported for this game.");
      return;
    }
    const parts = url.split("/");
    const id = parts[parts.findIndex((e) => e === "decks") + 2];
    return loadRangersDb(merge, noopActionList, "playerN", "rangersdb", "decks", id, cardDb);
  }

  alert("Importing via URL is not yet supported for this game.");
};
