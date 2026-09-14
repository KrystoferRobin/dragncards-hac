import React, { useEffect, useMemo, useState } from "react";
import { parsePlaintextDeck, searchCards, unresolvedToItem } from "./parsePlaintextDeck";
import { cardName } from "./deckEditorUtils";

export const DeckEditorPlaintextImport = ({
  open,
  initialText = "",
  cardDb,
  gameDef,
  language,
  hasCurrentDeck,
  onClose,
  onImport,
}) => {
  const [text, setText] = useState(initialText);
  const [deckName, setDeckName] = useState("");
  const [result, setResult] = useState(null);
  const [picks, setPicks] = useState({});
  const [queries, setQueries] = useState({});
  const [asNewDeck, setAsNewDeck] = useState(!hasCurrentDeck);

  useEffect(() => {
    if (!open) return;
    setText(initialText);
    setDeckName("");
    setResult(null);
    setPicks({});
    setQueries({});
    setAsNewDeck(!hasCurrentDeck);
  }, [open, hasCurrentDeck, initialText]);

  const spawnGroups = gameDef?.deckbuilder?.spawnGroups || [];

  const parsed = result;
  const remaining = useMemo(() => {
    if (!parsed) return [];
    return parsed.unresolved.filter((row) => !picks[row.key]);
  }, [parsed, picks]);

  if (!open) return null;

  const runParse = () => {
    const next = parsePlaintextDeck(text, cardDb, gameDef, language);
    setResult(next);
    setPicks({});
    setQueries({});
    if (next.name) setDeckName(next.name);
  };

  const resolvedItems = () => {
    if (!parsed) return [];
    const extras = parsed.unresolved
      .filter((row) => picks[row.key])
      .map((row) => unresolvedToItem({ ...row, loadGroupId: row.loadGroupId }, picks[row.key], cardDb, spawnGroups));
    return [...parsed.matched, ...extras];
  };

  const apply = (forceNew) => {
    const list = resolvedItems();
    if (!list.length) return;
    onImport(list, deckName.trim() || parsed?.name || "Imported", forceNew || asNewDeck);
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-60 p-4">
      <div className="bg-gray-800 border border-gray-600 rounded-lg w-full max-w-3xl max-h-[90vh] flex flex-col text-white">
        <div className="px-4 py-3 border-b border-gray-600 flex items-center gap-2">
          <div>
            <div className="font-semibold">Import plaintext list</div>
            <div className="text-xs text-gray-400">
              Paste a typed list (4x Name, 2 Name, Name). Cards the library cannot place stay here so you can match them.
            </div>
          </div>
          <button type="button" className="ml-auto px-2 py-1 border border-gray-500 rounded hover:bg-gray-700" onClick={onClose}>
            Close
          </button>
        </div>
        <div className="flex-1 min-h-0 overflow-auto p-4 space-y-3">
          <label className="block text-xs text-gray-300">
            Deck name
            <input
              type="text"
              className="w-full mt-1 rounded text-black px-2 py-1"
              value={deckName}
              onChange={(e) => setDeckName(e.target.value)}
              placeholder="Imported"
            />
          </label>
          <textarea
            className="w-full h-40 rounded text-black px-2 py-1 font-mono text-sm"
            value={text}
            onChange={(e) => {
              setText(e.target.value);
              setResult(null);
            }}
            placeholder={"Legality: Ivory\nThe Impregnable Fortress of the Crab\n2x Ashigaru Fort\n3x Hida Gojiro"}
          />
          <div className="flex flex-wrap items-center gap-2">
            <button type="button" className="px-3 py-1 border border-gray-500 rounded hover:bg-gray-700" onClick={runParse}>
              Parse list
            </button>
            {hasCurrentDeck && (
              <label className="text-xs text-gray-300 flex items-center gap-1">
                <input type="checkbox" checked={asNewDeck} onChange={(e) => setAsNewDeck(e.target.checked)} />
                Save as a new deck (do not add onto the one that is open)
              </label>
            )}
          </div>
          {parsed && (
            <div className="text-sm space-y-3">
              <div className="text-gray-300">
                {parsed.matched.length} matched
                {remaining.length ? ` · ${remaining.length} need a match` : ""}
                {parsed.skipped.length ? ` · ${parsed.skipped.length} skipped` : ""}
                {parsed.legality ? ` · legality hint: ${parsed.legality}` : ""}
              </div>
              {remaining.map((row) => (
                <UnresolvedRow
                  key={row.key}
                  row={row}
                  cardDb={cardDb}
                  query={queries[row.key] ?? row.query}
                  onQuery={(value) => setQueries((prev) => ({ ...prev, [row.key]: value }))}
                  onPick={(id) => setPicks((prev) => ({ ...prev, [row.key]: id }))}
                />
              ))}
              {parsed.unresolved.filter((row) => picks[row.key]).map((row) => (
                <div key={row.key} className="text-xs text-green-300">
                  Matched “{row.line}” to {cardName(cardDb, picks[row.key])}
                </div>
              ))}
            </div>
          )}
        </div>
        <div className="px-4 py-3 border-t border-gray-600 flex justify-end gap-2">
          <button type="button" className="px-3 py-1 border border-gray-500 rounded hover:bg-gray-700" onClick={onClose}>
            Cancel
          </button>
          <button
            type="button"
            className="px-3 py-1 border border-red-500 bg-red-800 rounded hover:bg-red-700 disabled:opacity-40"
            disabled={!parsed || !resolvedItems().length}
            onClick={() => apply(false)}
          >
            Import {parsed ? resolvedItems().length : 0} cards
            {remaining.length ? ` (skip ${remaining.length})` : ""}
          </button>
        </div>
      </div>
    </div>
  );
};

const UnresolvedRow = ({ row, cardDb, query, onQuery, onPick }) => {
  const suggestions = useMemo(() => {
    const fromSearch = searchCards(cardDb, query, 8).map((id) => ({
      databaseId: id,
      name: cardName(cardDb, id),
      packName: cardDb[id]?.A?.packName || "",
      type: cardDb[id]?.A?.type || "",
    }));
    const seen = new Set(fromSearch.map((item) => item.databaseId));
    const extras = (row.candidates || []).filter((item) => !seen.has(item.databaseId));
    return [...fromSearch, ...extras].slice(0, 10);
  }, [cardDb, query, row.candidates]);

  return (
    <div className="border border-gray-600 rounded p-2 bg-gray-900">
      <div className="text-sm">
        <span className="text-yellow-300">{row.status === "ambiguous" ? "Several matches" : "Not found"}</span>
        <span className="text-gray-400"> · {row.quantity}× </span>
        <span>{row.line}</span>
      </div>
      <input
        type="text"
        className="w-full mt-2 rounded text-black px-2 py-1 text-sm"
        value={query}
        onChange={(e) => onQuery(e.target.value)}
        placeholder="Search the library to match this line"
      />
      <div className="mt-1 max-h-36 overflow-auto">
        {suggestions.length === 0 && <div className="text-xs text-gray-500">No library cards match that search.</div>}
        {suggestions.map((item) => (
          <button
            key={item.databaseId}
            type="button"
            className="block w-full text-left text-xs px-2 py-1 rounded hover:bg-gray-700"
            onClick={() => onPick(item.databaseId)}
          >
            {item.name}
            <span className="text-gray-400">
              {item.packName ? ` · ${item.packName}` : ""}
              {item.type ? ` · ${item.type}` : ""}
            </span>
          </button>
        ))}
      </div>
    </div>
  );
};
