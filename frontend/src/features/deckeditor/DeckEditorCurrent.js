import React, { useEffect, useState } from "react";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faChevronLeft,
  faChevronRight,
  faDownload,
  faPlay,
  faSave,
  faShare,
  faTrash,
} from "@fortawesome/free-solid-svg-icons";
import { cardName, localizeLabel } from "./deckEditorUtils";

export const DeckEditorCurrent = ({
  currentDeck,
  setCurrentDeck,
  currentGroupId,
  setCurrentGroupId,
  modifyDeckList,
  saveCurrentDeck,
  deleteCurrentDeck,
  setDeckPublic,
  setSealedLegal,
  showSealedToggle,
  hidePublic,
  extraSpawnGroups,
  hideAllGroups,
  playDeck,
  playLabel,
  cardDb,
  gameDef,
  language,
  setHoverCard,
  numChanges,
}) => {
  const [showAllGroups, setShowAllGroups] = useState(false);
  const common = [...(gameDef?.deckbuilder?.spawnGroups || []), ...(extraSpawnGroups || [])];

  const allGroups = () => {
    const groups = [];
    const seen = new Set();
    Object.keys(gameDef?.groups || {}).forEach((groupId) => {
      groups.push({ loadGroupId: groupId, label: groupId });
      seen.add(groupId);
      if (groupId.includes("player1")) {
        const playerNversion = groupId.replace("player1", "playerN");
        if (!seen.has(playerNversion)) {
          seen.add(playerNversion);
          groups.push({ loadGroupId: playerNversion, label: groupId.replace("player1", "my") });
        }
      }
    });
    groups.sort((a, b) => (a.label > b.label ? 1 : -1));
    return groups;
  };

  const spawnGroups = showAllGroups && !hideAllGroups ? allGroups() : common;

  useEffect(() => {
    if (currentGroupId || !spawnGroups[0]) return;
    setCurrentGroupId(spawnGroups[0].loadGroupId);
  }, [currentGroupId, spawnGroups, setCurrentGroupId]);

  const exportCurrentDeck = () => {
    const exportList = (currentDeck.load_list || []).map((item) => ({
      ...item,
      _name: cardName(cardDb, item.databaseId),
    }));
    const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(exportList, null, 2));
    const node = document.createElement("a");
    node.setAttribute("href", dataStr);
    node.setAttribute("download", (currentDeck.name || "deck") + ".txt");
    document.body.appendChild(node);
    node.click();
    node.remove();
  };

  const countFor = (groupId) =>
    (currentDeck.load_list || [])
      .filter((item) => item.loadGroupId === groupId)
      .reduce((sum, item) => sum + (parseInt(item.quantity, 10) || 0), 0);

  const totalCount = (currentDeck.load_list || []).reduce(
    (sum, item) => sum + (parseInt(item.quantity, 10) || 0),
    0
  );

  if (!currentDeck?.id) {
    return (
      <div className="flex-1 flex items-center justify-center text-gray-400 text-sm p-4">
        Select a deck on the left, or click + to create one.
      </div>
    );
  }

  const tabItems = (currentDeck.load_list || [])
    .map((item, index) => ({ item, index }))
    .filter(({ item }) => item.loadGroupId === currentGroupId);

  return (
    <div className="flex flex-col min-h-0" style={{ height: "42%" }}>
      <div className="flex items-center gap-2 px-2 py-1 flex-shrink-0">
        <input
          type="text"
          className="rounded text-black px-2 py-0.5 flex-1 min-w-0"
          value={currentDeck.name || ""}
          onChange={(e) => setCurrentDeck({ ...currentDeck, name: e.target.value })}
        />
        <span className="text-xs text-gray-400">{totalCount} cards{numChanges ? ` · ${numChanges} unsaved` : ""}</span>
        <button type="button" className="px-2 py-1 border border-gray-500 rounded hover:bg-gray-600" title="Save" onClick={saveCurrentDeck}>
          <FontAwesomeIcon icon={faSave} />
        </button>
        <button type="button" className="px-2 py-1 border border-gray-500 rounded hover:bg-gray-600" title={playLabel} onClick={playDeck}>
          <FontAwesomeIcon icon={faPlay} />
        </button>
        <button type="button" className="px-2 py-1 border border-gray-500 rounded hover:bg-gray-600" title="Export" onClick={exportCurrentDeck}>
          <FontAwesomeIcon icon={faDownload} />
        </button>
        {showSealedToggle && (
          <button
            type="button"
            className={`px-2 py-1 text-xs border rounded hover:bg-gray-600 ${(currentDeck.formats || []).includes("sealed") ? "bg-green-800 border-green-500" : "border-gray-500"}`}
            title={(currentDeck.formats || []).includes("sealed") ? "Remove sealed-legal tag" : "Mark sealed-legal"}
            onClick={() => setSealedLegal(!((currentDeck.formats || []).includes("sealed")))}
          >
            Sealed
          </button>
        )}
        {!hidePublic && (
          <button
            type="button"
            className={`px-2 py-1 border rounded hover:bg-gray-600 ${currentDeck.public ? "bg-red-800 border-red-500" : "border-gray-500"}`}
            title={currentDeck.public ? "Make private" : "Make public"}
            onClick={() => setDeckPublic(!currentDeck.public)}
          >
            <FontAwesomeIcon icon={faShare} />
          </button>
        )}
        <button type="button" className="px-2 py-1 border border-gray-500 rounded hover:bg-gray-600" title="Delete" onClick={deleteCurrentDeck}>
          <FontAwesomeIcon icon={faTrash} />
        </button>
      </div>
      <div className="flex flex-wrap gap-1 px-2 pb-1 flex-shrink-0">
        {spawnGroups.map((group) => {
          const active = currentGroupId === group.loadGroupId;
          const count = countFor(group.loadGroupId);
          return (
            <button
              key={group.loadGroupId}
              type="button"
              className={`px-2 py-1 text-sm rounded ${active ? "bg-red-800" : "bg-gray-800 hover:bg-gray-700"}`}
              onClick={() => setCurrentGroupId(group.loadGroupId)}
            >
              {localizeLabel(gameDef, language, group.label)} ({count})
            </button>
          );
        })}
        {!hideAllGroups && (
        <button
          type="button"
          className="px-2 py-1 text-xs text-gray-400 hover:text-white"
          onClick={() => setShowAllGroups(!showAllGroups)}
        >
          {showAllGroups ? "Common tabs" : "All groups"}
        </button>
        )}
      </div>
      <div className="flex-1 min-h-0 overflow-auto px-2 pb-2">
        {tabItems.length === 0 && (
          <div className="text-xs text-gray-400">Nothing in this tab yet. Add cards from the list below.</div>
        )}
        {tabItems.map(({ item, index }) => (
          <div
            key={`${item.databaseId}-${index}`}
            className="relative flex items-center bg-gray-800 text-sm px-1 py-0.5 mb-0.5"
            onMouseEnter={() => setHoverCard({ ...cardDb[item.databaseId], leftSide: true })}
            onMouseLeave={() => setHoverCard(null)}
          >
            <button
              type="button"
              className="px-1 mr-1 border border-gray-500 rounded hover:bg-gray-600"
              onClick={() => modifyDeckList({ ...item, quantity: -item.quantity }, index)}
            >
              <FontAwesomeIcon icon={faTrash} />
            </button>
            <span className="truncate flex-1">{item._name || cardName(cardDb, item.databaseId)}</span>
            <button
              type="button"
              className="px-1 border border-gray-500 rounded hover:bg-gray-600"
              onClick={() => modifyDeckList({ ...item, quantity: -1 }, index)}
            >
              <FontAwesomeIcon icon={faChevronLeft} />
            </button>
            <span className="px-2">{item.quantity}</span>
            <button
              type="button"
              className="px-1 border border-gray-500 rounded hover:bg-gray-600"
              onClick={() => modifyDeckList({ ...item, quantity: 1 }, index)}
            >
              <FontAwesomeIcon icon={faChevronRight} />
            </button>
          </div>
        ))}
      </div>
    </div>
  );
};
