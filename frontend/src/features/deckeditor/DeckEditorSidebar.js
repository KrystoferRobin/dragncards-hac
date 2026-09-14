import React, { useMemo, useRef, useState } from "react";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faPlus, faUpload } from "@fortawesome/free-solid-svg-icons";
import { localizeLabel } from "./deckEditorUtils";

export const DeckEditorSidebar = ({
  myDecks,
  currentDeck,
  setCurrentDeck,
  createNewDeck,
  importLoadList,
  loadPrecon,
  preconEntries,
  gameDef,
  language,
  filters,
  setFilters,
  filterColumns,
}) => {
  const fileRef = useRef(null);
  const columns = filterColumns || [];
  const [preconQuery, setPreconQuery] = useState("");

  const handleFile = (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (e) => {
      try {
        const parsed = JSON.parse(e.target.result);
        if (!Array.isArray(parsed)) throw new Error("Deck file must be a JSON list.");
        importLoadList(parsed, file.name.replace(/\.(txt|json|o8d)$/i, "") || "Imported");
      } catch (err) {
        alert(err.message || "Could not read that deck file.");
      }
    };
    reader.readAsText(file);
    event.target.value = "";
  };

  return (
    <div className="flex flex-col h-full w-64 flex-shrink-0 border-r border-gray-700 bg-gray-900">
      <div className="px-2 pt-2 pb-1 text-sm font-semibold">Your decks</div>
      <div className="px-2 pb-2 flex gap-1">
        <button
          type="button"
          className="px-2 py-1 border border-gray-500 rounded hover:bg-gray-600"
          title="New deck"
          onClick={() => createNewDeck([])}
        >
          <FontAwesomeIcon icon={faPlus} />
        </button>
        <button
          type="button"
          className="px-2 py-1 border border-gray-500 rounded hover:bg-gray-600"
          title="Import JSON list"
          onClick={() => fileRef.current?.click()}
        >
          <FontAwesomeIcon icon={faUpload} />
        </button>
        <input ref={fileRef} type="file" accept=".txt,.json" hidden onChange={handleFile} />
      </div>
      <div className="flex-1 min-h-0 overflow-auto px-2 pb-2" style={{ minHeight: "18%" }}>
        {(!myDecks || myDecks.length === 0) && (
          <div className="text-xs text-gray-400">No saved decks yet. Click + to start one.</div>
        )}
        {myDecks?.map((deck) => (
          <button
            key={deck.id}
            type="button"
            className={`block w-full text-left text-sm px-2 py-1 mb-1 rounded truncate ${
              deck.id === currentDeck?.id ? "bg-red-800" : "bg-gray-800 hover:bg-gray-700"
            }`}
            onClick={() => setCurrentDeck(deck)}
            title={deck.name}
          >
            {deck.name || "Untitled"}
            {deck.public ? <span className="ml-1 text-xs text-yellow-300">public</span> : null}
          </button>
        ))}
      </div>
      <PreconList
        entries={preconEntries}
        query={preconQuery}
        setQuery={setPreconQuery}
        loadPrecon={loadPrecon}
        gameDef={gameDef}
        language={language}
      />
      <div className="flex-[2] min-h-0 flex flex-col border-t border-gray-700">
        <div className="px-2 pt-2 pb-1 text-sm font-semibold flex-shrink-0">Filters</div>
        <div className="flex-1 min-h-0 overflow-y-auto px-2 pb-2">
          {columns.map((col) => (
            <label key={col.propName} className="block text-xs mb-1">
              <span className="text-gray-300">{localizeLabel(gameDef, language, col.label)}</span>
              <input
                type="text"
                className="w-full mt-0.5 rounded text-black px-1 py-0.5"
                value={filters[col.propName] || ""}
                onChange={(e) => {
                  const value = e.target.value;
                  setFilters((prev) => {
                    const next = { ...prev };
                    if (value === "") delete next[col.propName];
                    else next[col.propName] = value;
                    return next;
                  });
                }}
              />
            </label>
          ))}
        </div>
      </div>
    </div>
  );
};

const PreconList = ({ entries, query, setQuery, loadPrecon, gameDef, language }) => {
  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return (entries || []).filter((entry) => {
      if (!needle) return true;
      const label = localizeLabel(gameDef, language, entry.label);
      const path = (entry.path || []).map((part) => localizeLabel(gameDef, language, part)).join(" ");
      return `${label} ${path}`.toLowerCase().includes(needle);
    });
  }, [entries, query, gameDef, language]);

  if (!entries?.length) return null;

  const groups = [];
  filtered.forEach((entry) => {
    const heading = (entry.path || []).map((part) => localizeLabel(gameDef, language, part)).join(" / ");
    const last = groups[groups.length - 1];
    if (!last || last.heading !== heading) groups.push({ heading, items: [entry] });
    else last.items.push(entry);
  });

  return (
    <div className="flex-1 min-h-0 flex flex-col border-t border-gray-700">
      <div className="px-2 pt-2 pb-1 text-sm font-semibold flex-shrink-0">Preconstructed</div>
      <div className="px-2 pb-1 text-xs text-gray-400 flex-shrink-0">
        Opens a copy you can edit. The server list stays as it is.
      </div>
      {entries.length > 8 && (
        <div className="px-2 pb-1 flex-shrink-0">
          <input
            type="text"
            className="w-full rounded text-black px-1 py-0.5 text-xs"
            placeholder="Find a starter"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
      )}
      <div className="flex-1 min-h-0 overflow-auto px-2 pb-2">
        {filtered.length === 0 && <div className="text-xs text-gray-400">No starters match.</div>}
        {groups.map((group) => (
          <div key={group.heading || "root"} className="mb-1">
            {group.heading ? <div className="text-xs text-gray-500 px-1 pt-1">{group.heading}</div> : null}
            {group.items.map((entry) => (
              <button
                key={entry.id}
                type="button"
                className="block w-full text-left text-sm px-2 py-1 mb-0.5 rounded truncate bg-gray-800 hover:bg-gray-700"
                title={`Load ${localizeLabel(gameDef, language, entry.label)} as a new deck`}
                onClick={() => loadPrecon(entry.id)}
              >
                {localizeLabel(gameDef, language, entry.label)}
              </button>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
};
