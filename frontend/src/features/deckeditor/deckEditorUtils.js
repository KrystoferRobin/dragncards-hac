export const makeLoadListItem = (databaseId, quantity, loadGroupId, cardName = null, authorId = null) => {
  const item = { databaseId, quantity, loadGroupId };
  if (cardName) item._name = cardName;
  if (authorId) item.authorId = authorId;
  return item;
};

export const toEditorGroupId = (loadGroupId) =>
  String(loadGroupId || "").replace(/^player[0-9]+/, "playerN");

export const toTableGroupId = (loadGroupId, playerN) =>
  String(loadGroupId || "").replace(/playerN/g, playerN || "player1");

const SKIP_FACE_PROPS = new Set([
  "databaseId",
  "imageUrl",
  "cardBack",
  "loadGroupId",
  "author_alias",
  "author_id",
  "authorId",
  "deckbuilderQuantity",
]);

const humanizeProp = (prop) =>
  String(prop)
    .replace(/_/g, " ")
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .replace(/^./, (c) => c.toUpperCase());

export const collectCatalogColumns = (gameDef, cardDb) => {
  const byProp = new Map();
  const add = (propName, label) => {
    if (!propName || SKIP_FACE_PROPS.has(propName) || String(propName).startsWith("_")) return;
    if (!byProp.has(propName)) byProp.set(propName, { propName, label: label || humanizeProp(propName) });
  };
  (gameDef?.deckbuilder?.columns || []).forEach((col) => add(col.propName, col.label));
  Object.entries(gameDef?.faceProperties || {}).forEach(([prop, meta]) => add(prop, meta?.label));
  const sample = Object.values(cardDb || {})[0]?.A;
  if (sample) Object.keys(sample).forEach((prop) => add(prop, gameDef?.faceProperties?.[prop]?.label));
  return Array.from(byProp.values());
};

export const defaultVisibleColumnProps = (gameDef) => {
  const fromPlugin = (gameDef?.deckbuilder?.columns || []).map((col) => col.propName).filter(Boolean);
  return fromPlugin.length ? fromPlugin : ["name", "type"];
};

export const columnStorageKey = (pluginId) => `dragn.deckEditor.cols.${pluginId || "unknown"}`;

export const readStoredColumns = (pluginId, allowed) => {
  try {
    const raw = localStorage.getItem(columnStorageKey(pluginId));
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return null;
    const allowedSet = new Set(allowed);
    const next = parsed.filter((prop) => allowedSet.has(prop));
    return next.length ? next : null;
  } catch (e) {
    return null;
  }
};

export const writeStoredColumns = (pluginId, props) => {
  if (!pluginId || !props?.length) return;
  try {
    localStorage.setItem(columnStorageKey(pluginId), JSON.stringify(props));
  } catch (e) {
    // ignore quota / private mode
  }
};

export const pruneFiltersToColumns = (filters, visibleProps) => {
  const keep = new Set(visibleProps);
  const next = {};
  Object.entries(filters || {}).forEach(([key, value]) => {
    if (keep.has(key)) next[key] = value;
  });
  return next;
};

export const resolveVisibleColumnProps = (pluginId, gameDef, availableColumns) => {
  const allowed = availableColumns.map((col) => col.propName);
  const stored = readStoredColumns(pluginId, allowed);
  if (stored) return stored;
  const fallback = defaultVisibleColumnProps(gameDef).filter((prop) => allowed.includes(prop));
  return fallback.length ? fallback : allowed.slice(0, 5);
};

export const localizeLabel = (gameDef, language, label) => {
  if (typeof label !== "string") return String(label ?? "");
  if (label.startsWith("id:")) {
    const labelId = label.substring(3);
    return gameDef?.labels?.[labelId]?.[language] || gameDef?.labels?.[labelId]?.English || labelId;
  }
  return label;
};

export const resolveCardImageUrl = (gameDef, language, imageUrl) => {
  if (!imageUrl) return { src: null, fallback: null };
  if (String(imageUrl).startsWith("http")) return { src: imageUrl, fallback: imageUrl };
  const prefixDefault = gameDef?.imageUrlPrefix?.Default || "";
  const prefixLang = language && gameDef?.imageUrlPrefix?.[language] ? gameDef.imageUrlPrefix[language] : "";
  return {
    src: prefixLang ? prefixLang + imageUrl : prefixDefault + imageUrl,
    fallback: prefixDefault + imageUrl,
  };
};

export const cardName = (cardDb, databaseId) =>
  cardDb?.[databaseId]?.A?.name || cardDb?.[databaseId]?.A?._name || databaseId;

export const matchesFilters = (card, filters) => {
  const entries = Object.entries(filters).filter(([, val]) => val != null && String(val).trim() !== "");
  if (!entries.length) return true;
  return entries.every(([propName, filterVal]) => {
    const needle = String(filterVal).toLowerCase();
    const propA = card?.A?.[propName];
    const propB = card?.B?.[propName];
    const match = (prop) =>
      prop !== null && prop !== undefined && prop !== "" && String(prop).toLowerCase().includes(needle);
    return match(propA) || match(propB);
  });
};

export const sortCardIds = (cardIds, cardDb, column, direction, integerType) => {
  const copy = [...cardIds];
  copy.sort((a, b) => {
    const aValue = cardDb[a]?.A?.[column];
    const bValue = cardDb[b]?.A?.[column];
    if (integerType || (typeof aValue === "number" && typeof bValue === "number")) {
      const av = parseInt(aValue, 10) || 0;
      const bv = parseInt(bValue, 10) || 0;
      return direction === "asc" ? av - bv : bv - av;
    }
    const as = aValue == null ? "" : String(aValue);
    const bs = bValue == null ? "" : String(bValue);
    return direction === "asc" ? as.localeCompare(bs) : bs.localeCompare(as);
  });
  return copy;
};

export const parseO8dXml = (xmlText, gameDef) => {
  if (!gameDef?.o8dImport) {
    throw new Error("This game does not support .o8d import.");
  }
  const mapping = gameDef.o8dImport.o8dSectionToLoadGroupId || {};
  const otherLoadGroupId = gameDef.o8dImport.otherGroupId;
  return new Promise((resolve, reject) => {
    const parseString = require("xml2js").parseString;
    parseString(xmlText, (err, deckJSON) => {
      if (err || !deckJSON) {
        reject(err || new Error("Could not parse .o8d file."));
        return;
      }
      const sections = deckJSON.deck?.section || [];
      const loadList = [];
      sections.forEach((section) => {
        const sectionName = section.$?.name;
        const cards = section.card;
        if (!cards) return;
        cards.forEach((card) => {
          loadList.push({
            databaseId: card.$?.id,
            quantity: parseInt(card.$?.qty, 10) || 1,
            loadGroupId: mapping[sectionName] || otherLoadGroupId,
          });
        });
      });
      resolve(loadList);
    });
  });
};
