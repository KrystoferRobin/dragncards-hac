import React, { useEffect, useMemo, useState } from "react";
import axios from "axios";
import { RotatingLines } from "react-loader-spinner";
import { useAuthOptions } from "../../hooks/useAuthOptions";
import useProfile from "../../hooks/useProfile";
import useDataApi from "../../hooks/useDataApi";
import { DeckEditorSidebar } from "./DeckEditorSidebar";
import { DeckEditorCurrent } from "./DeckEditorCurrent";
import { DeckEditorCatalog } from "./DeckEditorCatalog";
import { DeckEditorHoverCard } from "./DeckEditorHoverCard";
import {
  cardName,
  collectCatalogColumns,
  parseO8dXml,
  pruneFiltersToColumns,
  resolveVisibleColumnProps,
  toEditorGroupId,
  writeStoredColumns,
} from "./deckEditorUtils";
import { importDeckFromUrl } from "./importDeckUrl";
import { collectPreconEntries, preconToLoadList } from "./parsePlaintextDeck";
import { DeckEditorPlaintextImport } from "./DeckEditorPlaintextImport";

export const DeckEditor = ({
  plugin,
  mode,
  playerN,
  onPlayAtTable,
  onStartTable,
  onClose,
  headerLeft,
  pool,
  sessionId,
  onCommit,
}) => {
  const user = useProfile();
  const authOptions = useAuthOptions();
  const gameDef = plugin?.game_def || {};
  const cardDb = plugin?.card_db || {};
  const pluginId = plugin?.id;
  const language = user?.language || "English";
  const spawnGroups = useMemo(() => {
    const groups = [...(gameDef?.deckbuilder?.spawnGroups || [])];
    if (mode === "limited" && !groups.some((g) => g.loadGroupId === "playerNCardPool")) {
      groups.push({ loadGroupId: "playerNCardPool", label: "Card Pool" });
    }
    return groups;
  }, [gameDef, mode]);

  const [currentDeck, setCurrentDeck] = useState({});
  const [currentGroupId, setCurrentGroupId] = useState(spawnGroups[0]?.loadGroupId);
  const [numChanges, setNumChanges] = useState(0);
  const [hoverCard, setHoverCard] = useState(null);
  const [filters, setFilters] = useState({});
  const [status, setStatus] = useState("");
  const [plaintextOpen, setPlaintextOpen] = useState(false);
  const availableColumns = useMemo(() => collectCatalogColumns(gameDef, cardDb), [gameDef, cardDb]);
  const [visibleProps, setVisibleProps] = useState(() =>
    resolveVisibleColumnProps(pluginId, gameDef, availableColumns)
  );

  const visibleColumns = useMemo(() => {
    const byProp = new Map(availableColumns.map((col) => [col.propName, col]));
    return visibleProps.map((prop) => byProp.get(prop)).filter(Boolean);
  }, [availableColumns, visibleProps]);

  const applyVisibleProps = (next) => {
    setVisibleProps(next);
    setFilters((prev) => pruneFiltersToColumns(prev, next));
    writeStoredColumns(pluginId, next);
  };

  const preconEntries = useMemo(() => collectPreconEntries(gameDef), [gameDef]);
  const myDecksUrl = user?.id && pluginId ? `/be/api/v1/decks/${user.id}/${pluginId}` : null;
  const { data, doFetchUrl, doFetchHash } = useDataApi(myDecksUrl || "/be/api/v1/decks/0/0", null, Boolean(myDecksUrl));
  const myDecks = data?.my_decks;

  useEffect(() => {
    if (myDecksUrl) doFetchUrl(myDecksUrl);
  }, [myDecksUrl, user?.id]);

  useEffect(() => {
    applyVisibleProps(resolveVisibleColumnProps(pluginId, gameDef, availableColumns));
  }, [pluginId, gameDef?.pluginName]);

  useEffect(() => {
    if (numChanges > 8 && currentDeck?.id) {
      saveCurrentDeck(false);
    }
  }, [numChanges]);

  const refreshDecks = () => doFetchHash(new Date().toISOString());

  const normalizeList = (list) =>
    (list || []).map((item) => ({
      ...item,
      loadGroupId: toEditorGroupId(item.loadGroupId),
      _name: item._name || cardName(cardDb, item.databaseId),
    }));

  const createNewDeck = async (loadList, name = "Untitled") => {
    const updateData = {
      deck: {
        name,
        author_id: user?.id,
        plugin_id: pluginId,
        load_list: normalizeList(loadList),
        public: false,
        formats: mode === "limited" ? ["limited"] : [],
        limited_session_id: mode === "limited" ? sessionId || null : null,
      },
    };
    const res = await axios.post("/be/api/v1/decks", updateData, authOptions);
    if (res.status === 200) {
      setCurrentDeck(res.data.success.deck);
      setNumChanges(0);
      refreshDecks();
    }
  };

  const saveCurrentDeck = async (announce = true) => {
    if (!currentDeck?.id) return;
    const res = await axios.patch(`/be/api/v1/decks/${currentDeck.id}`, { deck: currentDeck }, authOptions);
    if (res.status === 200) {
      setNumChanges(0);
      refreshDecks();
      if (announce) setStatus("Saved.");
    }
  };

  const setDeckPublic = async (val) => {
    const next = { ...currentDeck, public: val };
    setCurrentDeck(next);
    await axios.patch(`/be/api/v1/decks/${currentDeck.id}`, { deck: next }, authOptions);
    refreshDecks();
    setStatus(val ? "Deck is public." : "Deck is private.");
  };

  const deleteCurrentDeck = async () => {
    if (!window.confirm("Delete this deck?")) return;
    await axios.delete(`/be/api/v1/decks/${currentDeck.id}`, authOptions);
    setCurrentDeck({});
    setNumChanges(0);
    refreshDecks();
  };

  const setSealedLegal = async (val) => {
    const formats = new Set(currentDeck.formats || []);
    if (val) formats.add("sealed");
    else formats.delete("sealed");
    const next = { ...currentDeck, formats: [...formats] };
    setCurrentDeck(next);
    await axios.patch(`/be/api/v1/decks/${currentDeck.id}`, { deck: next }, authOptions);
    refreshDecks();
    setStatus(val ? "Marked sealed-legal." : "Removed sealed tag.");
  };

  const limitedModify = (loadListItem, existingIndex = null) => {
    if (!currentDeck?.id) return;
    const poolGroup = "playerNCardPool";
    const deckCopy = { ...currentDeck, load_list: [...(currentDeck.load_list || [])] };
    const id = loadListItem.databaseId;
    const bump = (groupId, delta) => {
      const idx = deckCopy.load_list.findIndex((item) => item.databaseId === id && item.loadGroupId === groupId);
      if (idx >= 0) {
        deckCopy.load_list[idx] = {
          ...deckCopy.load_list[idx],
          quantity: deckCopy.load_list[idx].quantity + delta,
        };
        if (deckCopy.load_list[idx].quantity <= 0) deckCopy.load_list.splice(idx, 1);
      } else if (delta > 0) {
        deckCopy.load_list.push({
          databaseId: id,
          quantity: delta,
          loadGroupId: groupId,
          _name: loadListItem._name || cardName(cardDb, id),
        });
      }
    };

    if (existingIndex != null) {
      const item = deckCopy.load_list[existingIndex];
      if (!item || item.loadGroupId === poolGroup) return;
      const removeQty = Math.min(Math.abs(loadListItem.quantity || 1), item.quantity || 0);
      if (removeQty <= 0) return;
      bump(item.loadGroupId, -removeQty);
      bump(poolGroup, removeQty);
    } else {
      const toGroup = loadListItem.loadGroupId || currentGroupId;
      if (!toGroup || toGroup === poolGroup) return;
      const poolItem = deckCopy.load_list.find((item) => item.databaseId === id && item.loadGroupId === poolGroup);
      const move = Math.min(Math.abs(loadListItem.quantity || 1), poolItem?.quantity || 0);
      if (move <= 0) return;
      bump(poolGroup, -move);
      bump(toGroup, move);
    }
    setCurrentDeck(deckCopy);
    setNumChanges((n) => n + 1);
  };

  const modifyDeckList = (loadListItem, existingIndex = null) => {
    if (mode === "limited") {
      limitedModify(loadListItem, existingIndex);
      return;
    }
    if (!currentDeck?.id) {
      createNewDeck([loadListItem]);
      return;
    }
    const deckCopy = { ...currentDeck, load_list: [...(currentDeck.load_list || [])] };
    if (existingIndex !== null) {
      deckCopy.load_list[existingIndex] = {
        ...deckCopy.load_list[existingIndex],
        quantity: deckCopy.load_list[existingIndex].quantity + loadListItem.quantity,
      };
      if (deckCopy.load_list[existingIndex].quantity <= 0) {
        deckCopy.load_list.splice(existingIndex, 1);
        setHoverCard(null);
      }
    } else {
      const same = deckCopy.load_list.findIndex(
        (item) => item.databaseId === loadListItem.databaseId && item.loadGroupId === loadListItem.loadGroupId
      );
      if (same >= 0) {
        deckCopy.load_list[same] = {
          ...deckCopy.load_list[same],
          quantity: deckCopy.load_list[same].quantity + loadListItem.quantity,
        };
      } else {
        deckCopy.load_list.push({
          ...loadListItem,
          _name: loadListItem._name || cardName(cardDb, loadListItem.databaseId),
        });
      }
    }
    setCurrentDeck(deckCopy);
    setNumChanges((n) => n + 1);
  };

  const mergeImportedList = (list, name, asNewDeck = false) => {
    const normalized = normalizeList(list);
    if (asNewDeck || !currentDeck?.id) {
      createNewDeck(normalized, name || "Imported");
      setStatus("Opened as a new deck.");
      return;
    }
    const deckCopy = { ...currentDeck, load_list: [...(currentDeck.load_list || [])] };
    if (name && (deckCopy.name === "Untitled" || !deckCopy.name)) deckCopy.name = name;
    normalized.forEach((incoming) => {
      const same = deckCopy.load_list.findIndex(
        (item) => item.databaseId === incoming.databaseId && item.loadGroupId === incoming.loadGroupId
      );
      if (same >= 0) {
        deckCopy.load_list[same] = {
          ...deckCopy.load_list[same],
          quantity: deckCopy.load_list[same].quantity + incoming.quantity,
        };
      } else {
        deckCopy.load_list.push(incoming);
      }
    });
    setCurrentDeck(deckCopy);
    setNumChanges((n) => n + 1);
  };

  const loadPrecon = (deckId) => {
    const precon = preconToLoadList(gameDef, deckId);
    if (!precon) {
      setStatus("That starter is not in this plugin.");
      return;
    }
    if (numChanges > 0 && currentDeck?.id) {
      if (!window.confirm("You have unsaved changes. Load this starter as a new deck anyway?")) return;
    }
    createNewDeck(precon.loadList, `${precon.name} (copy)`);
    setStatus("Loaded a copy. Saving will keep your deck; the starter is unchanged.");
  };

  const handleUrlImport = () => {
    importDeckFromUrl({
      pluginName: gameDef.pluginName || plugin?.name,
      cardDb,
      onLoadList: (list) => mergeImportedList(list, "Imported"),
    });
  };

  const handleO8d = (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = async (e) => {
      try {
        const list = await parseO8dXml(e.target.result, gameDef);
        mergeImportedList(list, file.name.replace(/\.o8d$/i, ""));
      } catch (err) {
        alert(err.message || "Could not import that .o8d file.");
      }
    };
    reader.readAsText(file);
    event.target.value = "";
  };

  const playDeck = async () => {
    if (!currentDeck?.id) return;
    await saveCurrentDeck(false);
    if (mode === "limited" && onCommit) {
      onCommit(currentDeck);
      return;
    }
    if (mode === "table" && onPlayAtTable) {
      onPlayAtTable(currentDeck);
      return;
    }
    if (onStartTable) onStartTable(currentDeck);
  };

  useEffect(() => {
    if (mode !== "limited" || !user?.id || currentDeck?.id || !pool?.length) return;
    const list = pool.map((item) => ({
      databaseId: item.databaseId,
      quantity: item.quantity,
      loadGroupId: "playerNCardPool",
    }));
    createNewDeck(list, "Limited pool");
  }, [mode, user?.id, pool, currentDeck?.id]);

  const remainingById = useMemo(() => {
    if (mode !== "limited") return null;
    const rem = {};
    (currentDeck.load_list || []).forEach((item) => {
      if (item.loadGroupId === "playerNCardPool") {
        rem[item.databaseId] = (rem[item.databaseId] || 0) + (item.quantity || 0);
      }
    });
    return rem;
  }, [mode, currentDeck]);

  const allowedIds = useMemo(() => {
    if (mode !== "limited") return null;
    return (pool || []).map((item) => item.databaseId);
  }, [mode, pool]);

  if (!gameDef?.deckbuilder) {
    return (
      <div className="flex items-center justify-center h-full text-white p-6">
        This plugin has no deckbuilder settings (spawn groups / columns).
      </div>
    );
  }

  if (!Object.keys(cardDb).length) {
    return (
      <div className="flex h-full w-full items-center justify-center bg-gray-900">
        <RotatingLines height={80} width={80} strokeColor="white" />
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full w-full bg-gray-900 text-white min-h-0">
      <div className="flex items-center gap-2 px-3 py-2 border-b border-gray-700 flex-shrink-0">
        {headerLeft}
        <div className="font-semibold truncate">{gameDef.pluginName || plugin?.name}</div>
        <div className="flex-1" />
        {status && <span className="text-xs text-gray-400">{status}</span>}
        {mode !== "limited" && (
          <>
            <button type="button" className="px-2 py-1 text-sm border border-gray-500 rounded hover:bg-gray-700" onClick={handleUrlImport}>
              Import URL
            </button>
            <button
              type="button"
              className="px-2 py-1 text-sm border border-gray-500 rounded hover:bg-gray-700"
              onClick={() => setPlaintextOpen(true)}
            >
              Import text
            </button>
            <label className="px-2 py-1 text-sm border border-gray-500 rounded hover:bg-gray-700 cursor-pointer">
              Import .o8d
              <input type="file" accept=".o8d" hidden onChange={handleO8d} />
            </label>
          </>
        )}
        {onClose && (
          <button type="button" className="px-2 py-1 text-sm border border-gray-500 rounded hover:bg-gray-700" onClick={onClose}>
            Close
          </button>
        )}
      </div>
      <div className="flex flex-1 min-h-0">
        {mode !== "limited" && (
          <DeckEditorSidebar
            myDecks={myDecks}
            currentDeck={currentDeck}
            setCurrentDeck={(deck) => {
              setCurrentDeck(deck);
              setNumChanges(0);
            }}
            createNewDeck={createNewDeck}
            importLoadList={mergeImportedList}
            loadPrecon={loadPrecon}
            preconEntries={preconEntries}
            gameDef={gameDef}
            language={language}
            filters={filters}
            setFilters={setFilters}
            filterColumns={visibleColumns}
          />
        )}
        <div className="flex flex-col flex-1 min-w-0 min-h-0">
          <DeckEditorCurrent
            currentDeck={currentDeck}
            setCurrentDeck={setCurrentDeck}
            currentGroupId={currentGroupId}
            setCurrentGroupId={setCurrentGroupId}
            modifyDeckList={modifyDeckList}
            saveCurrentDeck={() => saveCurrentDeck(true)}
            deleteCurrentDeck={deleteCurrentDeck}
            setDeckPublic={setDeckPublic}
            setSealedLegal={setSealedLegal}
            showSealedToggle={mode !== "limited"}
            hidePublic={mode === "limited"}
            extraSpawnGroups={mode === "limited" ? [{ loadGroupId: "playerNCardPool", label: "Card Pool" }] : []}
            hideAllGroups={mode === "limited"}
            playDeck={playDeck}
            playLabel={mode === "limited" ? "Commit to table" : mode === "table" ? "Load onto table" : "Start a table"}
            cardDb={cardDb}
            gameDef={gameDef}
            language={language}
            setHoverCard={setHoverCard}
            numChanges={numChanges}
          />
          <DeckEditorCatalog
            cardDb={cardDb}
            gameDef={gameDef}
            language={language}
            pluginId={pluginId}
            availableColumns={availableColumns}
            visibleProps={visibleProps}
            applyVisibleProps={applyVisibleProps}
            currentGroupId={currentGroupId}
            modifyDeckList={modifyDeckList}
            setHoverCard={setHoverCard}
            filters={filters}
            allowedIds={allowedIds}
            remainingById={remainingById}
          />
        </div>
      </div>
      <DeckEditorHoverCard card={hoverCard} gameDef={gameDef} language={language} />
      <DeckEditorPlaintextImport
        open={plaintextOpen}
        cardDb={cardDb}
        gameDef={gameDef}
        language={language}
        hasCurrentDeck={Boolean(currentDeck?.id)}
        onClose={() => setPlaintextOpen(false)}
        onImport={mergeImportedList}
      />
    </div>
  );
};
