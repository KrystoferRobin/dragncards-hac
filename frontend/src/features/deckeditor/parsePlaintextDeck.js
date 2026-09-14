import { cardName, localizeLabel, toEditorGroupId } from "./deckEditorUtils.js";

const META_LINE = /^(name|deck|title|author|creator|player|notes?|comments?|format|legality|edition|legal)\s*:\s*(.*)$/i;
const QTY_PREFIX = /^(\d+)\s*[xX×]\s+(.+)$/;
const QTY_SPACE = /^(\d+)\s+(.+)$/;
const QTY_SUFFIX = /^(.+?)\s+[xX×]\s*(\d+)$/;
const SB_PREFIX = /^(?:sb|sideboard)\s*:\s*(.+)$/i;
const SET_TRAIL = /\s*[(\[]([^)\]]+)[)\]]\s*$/;
const COMMENT = /^\s*(?:#|\/\/|;)/;

const SECTION_HINTS = [
  ["stronghold", "stronghold"],
  ["sensei", "sensei"],
  ["wind", "wind"],
  ["dynasty", "dynasty"],
  ["fate", "fate"],
  ["sideboard", "sideboard"],
  ["side board", "sideboard"],
  ["command", "command"],
  ["crypt", "crypt"],
  ["library", "deck"],
  ["main deck", "deck"],
  ["draw deck", "deck"],
  ["ashheap", "ash"],
  ["play", "play"],
  ["deck", "deck"],
];

export const normalizeCardName = (value) =>
  String(value || "")
    .replace(/\u2019/g, "'")
    .replace(/`/g, "'")
    .replace(/&#\d+;/g, " ")
    .replace(/&[a-z]+;/gi, " ")
    .replace(/\s*\(\d+\)\s*$/g, "")
    .replace(/\s*-\s*exp(\d*)\s*$/i, " exp$1")
    .replace(/\s*-\s*inexp\s*$/i, " inexp")
    .replace(/experienced/gi, "exp")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();

export const buildCardIndex = (cardDb) => {
  const byId = new Map();
  const byNorm = new Map();
  Object.entries(cardDb || {}).forEach(([id, card]) => {
    byId.set(String(id).toLowerCase(), id);
    const names = [card?.A?.name, card?.A?._name, card?.B?.name].filter(Boolean);
    names.forEach((name) => {
      const key = normalizeCardName(name);
      if (!key) return;
      const list = byNorm.get(key) || [];
      if (!list.includes(id)) list.push(id);
      byNorm.set(key, list);
    });
  });
  return { byId, byNorm };
};

const groupToken = (loadGroupId) =>
  normalizeCardName(String(loadGroupId || "").replace(/^player[nN0-9]+/, ""));

export const resolveLoadGroup = (cardDb, databaseId, sectionGroupId, spawnGroups) => {
  if (sectionGroupId) return toEditorGroupId(sectionGroupId);
  const fromCard = cardDb?.[databaseId]?.A?.loadGroupId;
  if (fromCard) return toEditorGroupId(fromCard);
  return toEditorGroupId(spawnGroups?.[0]?.loadGroupId || "playerNDeck");
};

const matchSection = (line, spawnGroups) => {
  const trimmed = String(line || "").trim().replace(/:+\s*$/, "");
  const withoutCount = trimmed.replace(/\s*\(\d+\)\s*$/, "").trim();
  const key = normalizeCardName(withoutCount);
  if (!key || key.length > 40) return null;

  for (const group of spawnGroups || []) {
    const label = normalizeCardName(String(group.label || "").replace(/^id:/, "").replace(/^my\s+/, ""));
    const token = groupToken(group.loadGroupId);
    if (key === label || key === token || key === normalizeCardName(`my ${token}`)) {
      return group.loadGroupId;
    }
  }

  for (const [hint, token] of SECTION_HINTS) {
    if (key !== hint && key !== `${hint} deck` && key !== `my ${hint}`) continue;
    const found = (spawnGroups || []).find((group) => groupToken(group.loadGroupId).includes(token));
    return found?.loadGroupId || null;
  }
  return null;
};

const parseQtyName = (raw) => {
  const text = String(raw || "").trim();
  let qty = 1;
  let name = text;
  let sb = false;
  let working = text;
  const side = working.match(SB_PREFIX);
  if (side) {
    sb = true;
    working = side[1].trim();
  }
  const prefixX = working.match(QTY_PREFIX);
  const prefixN = working.match(QTY_SPACE);
  const suffixX = working.match(QTY_SUFFIX);
  if (prefixX) {
    qty = parseInt(prefixX[1], 10) || 1;
    name = prefixX[2].trim();
  } else if (prefixN && !/^\d+$/.test(prefixN[2])) {
    qty = parseInt(prefixN[1], 10) || 1;
    name = prefixN[2].trim();
  } else if (suffixX) {
    qty = parseInt(suffixX[2], 10) || 1;
    name = suffixX[1].trim();
  }
  let setHint = "";
  const setMatch = name.match(SET_TRAIL);
  if (setMatch && /[a-z]/i.test(setMatch[1]) && !/^\d+$/.test(setMatch[1].trim())) {
    setHint = setMatch[1].trim();
    name = name.replace(SET_TRAIL, "").trim();
  }
  return { qty, name, setHint, sb };
};

const cardPack = (card) =>
  normalizeCardName(card?.A?.packName || card?.A?.set || card?.A?.setName || "");

const cardLegal = (card) => normalizeCardName(card?.A?.legal || card?.A?.legality || "");

const scoreCandidate = (card, { setHint, legality }) => {
  let score = 0;
  const pack = cardPack(card);
  const legal = cardLegal(card);
  const setKey = normalizeCardName(setHint);
  const legalKey = normalizeCardName(legality);
  if (setKey && pack === setKey) score += 8;
  else if (setKey && pack.includes(setKey)) score += 5;
  if (legalKey && legal.includes(legalKey)) score += 4;
  const rawName = String(card?.A?.name || "");
  if (/\(1\)\s*$/.test(rawName)) score += 1;
  return score;
};

const pickBest = (ids, cardDb, hints) => {
  if (!ids.length) return { id: null, rest: [] };
  if (ids.length === 1) return { id: ids[0], rest: [] };
  const ranked = [...ids].sort((a, b) => scoreCandidate(cardDb[b], hints) - scoreCandidate(cardDb[a], hints));
  const top = scoreCandidate(cardDb[ranked[0]], hints);
  const second = ranked[1] ? scoreCandidate(cardDb[ranked[1]], hints) : -1;
  if (top > second) return { id: ranked[0], rest: ranked.slice(1) };
  const allParenVariants = ranked.every((id) => /\(\d+\)\s*$/.test(String(cardDb[id]?.A?.name || "")));
  const sameTitle = ranked.every(
    (id) => normalizeCardName(cardDb[id]?.A?.name) === normalizeCardName(cardDb[ranked[0]]?.A?.name)
  );
  if (sameTitle && allParenVariants) return { id: ranked[0], rest: ranked.slice(1) };
  return { id: null, rest: ranked };
};

export const searchCards = (cardDb, query, limit = 8) => {
  const needle = normalizeCardName(query);
  if (!needle) return [];
  const starts = [];
  const contains = [];
  Object.entries(cardDb || {}).forEach(([id, card]) => {
    if (starts.length >= limit) return;
    const name = normalizeCardName(card?.A?.name || card?.A?._name);
    if (!name) return;
    if (name === needle || name.startsWith(needle)) starts.push(id);
    else if (name.includes(needle)) contains.push(id);
  });
  return [...starts, ...contains].slice(0, limit);
};

const candidateInfo = (cardDb, id) => ({
  databaseId: id,
  name: cardName(cardDb, id),
  packName: cardDb[id]?.A?.packName || cardDb[id]?.A?.set || "",
  legal: cardDb[id]?.A?.legal || "",
  type: cardDb[id]?.A?.type || "",
});

const findSideboardGroup = (spawnGroups) =>
  (spawnGroups || []).find((group) => /side/i.test(group.loadGroupId) || /side/i.test(group.label || ""))
    ?.loadGroupId || null;

export const collectPreconEntries = (gameDef) => {
  const decks = gameDef?.preBuiltDecks || {};
  const seen = new Set();
  const entries = [];

  const walk = (menu, path) => {
    if (!menu) return;
    (menu.deckLists || []).forEach((item) => {
      if (!item?.deckListId || !decks[item.deckListId]) return;
      seen.add(item.deckListId);
      entries.push({
        id: item.deckListId,
        label: item.label || decks[item.deckListId].label || item.deckListId,
        path,
      });
    });
    (menu.subMenus || []).forEach((sub) => {
      walk(sub, [...path, sub.label || "More"]);
    });
  };

  walk(gameDef?.deckMenu, []);
  Object.keys(decks).forEach((id) => {
    if (seen.has(id)) return;
    entries.push({ id, label: decks[id].label || id, path: [] });
  });
  return entries;
};

export const preconToLoadList = (gameDef, deckId) => {
  const deck = gameDef?.preBuiltDecks?.[deckId];
  if (!deck) return null;
  return {
    name: deck.label || deckId,
    loadList: (deck.cards || []).map((card) => ({
      ...card,
      loadGroupId: toEditorGroupId(card.loadGroupId),
    })),
  };
};

export const parsePlaintextDeck = (text, cardDb, gameDef, language = "English") => {
  const spawnGroups = (gameDef?.deckbuilder?.spawnGroups || []).map((group) => ({
    ...group,
    label: localizeLabel(gameDef, language, group.label),
  }));
  const index = buildCardIndex(cardDb);
  const sideGroup = findSideboardGroup(spawnGroups);

  const trimmed = String(text || "").trim();
  if (!trimmed) {
    return { name: "", legality: "", matched: [], unresolved: [], skipped: [] };
  }

  if (trimmed.startsWith("[") || trimmed.startsWith("{")) {
    try {
      const parsed = JSON.parse(trimmed);
      const list = Array.isArray(parsed) ? parsed : parsed.load_list || parsed.cards;
      if (Array.isArray(list)) {
        return {
          name: parsed.name || "",
          legality: "",
          matched: list
            .filter((item) => item?.databaseId)
            .map((item) => ({
              quantity: parseInt(item.quantity, 10) || 1,
              databaseId: item.databaseId,
              loadGroupId: resolveLoadGroup(cardDb, item.databaseId, item.loadGroupId, spawnGroups),
              _name: item._name || cardName(cardDb, item.databaseId),
              line: item.databaseId,
            })),
          unresolved: [],
          skipped: [],
        };
      }
    } catch (e) {
      // fall through to line parser
    }
  }

  let name = "";
  let legality = "";
  let sectionGroupId = null;
  const matched = [];
  const unresolved = [];
  const skipped = [];
  let unresolvedSeq = 0;

  String(text)
    .split(/\r?\n/)
    .forEach((rawLine) => {
      const line = rawLine.trim();
      if (!line || COMMENT.test(line)) return;

      const meta = line.match(META_LINE);
      if (meta) {
        const key = meta[1].toLowerCase();
        const value = meta[2].trim();
        if (["name", "deck", "title"].includes(key) && value) name = value;
        if (["format", "legality", "edition", "legal"].includes(key) && value) legality = value;
        if (["author", "creator", "player", "note", "notes", "comment", "comments"].includes(key)) return;
        return;
      }

      const section = matchSection(line, spawnGroups);
      if (section) {
        sectionGroupId = section;
        return;
      }

      const parsed = parseQtyName(line);
      if (!parsed.name) {
        skipped.push(line);
        return;
      }

      const groupHint = parsed.sb ? sideGroup || sectionGroupId : sectionGroupId;
      const byId = index.byId.get(parsed.name.toLowerCase());
      let ids = byId ? [byId] : index.byNorm.get(normalizeCardName(parsed.name)) || [];
      const picked = pickBest(ids, cardDb, { setHint: parsed.setHint, legality });

      if (picked.id) {
        matched.push({
          quantity: parsed.qty,
          databaseId: picked.id,
          loadGroupId: resolveLoadGroup(cardDb, picked.id, groupHint, spawnGroups),
          _name: cardName(cardDb, picked.id),
          line,
        });
        return;
      }

      const suggestions = (picked.rest.length ? picked.rest : searchCards(cardDb, parsed.name, 8)).map((id) =>
        candidateInfo(cardDb, id)
      );
      unresolvedSeq += 1;
      unresolved.push({
        key: `u${unresolvedSeq}`,
        line,
        quantity: parsed.qty,
        query: parsed.name,
        setHint: parsed.setHint,
        loadGroupId: groupHint ? toEditorGroupId(groupHint) : "",
        status: ids.length ? "ambiguous" : "unmatched",
        candidates: suggestions,
      });
    });

  return { name, legality, matched, unresolved, skipped };
};

export const unresolvedToItem = (row, databaseId, cardDb, spawnGroups) => ({
  quantity: row.quantity,
  databaseId,
  loadGroupId: resolveLoadGroup(cardDb, databaseId, row.loadGroupId, spawnGroups),
  _name: cardName(cardDb, databaseId),
  line: row.line,
});
