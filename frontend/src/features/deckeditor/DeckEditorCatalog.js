import React, { useEffect, useMemo, useRef, useState } from "react";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faColumns, faSort, faSortDown, faSortUp } from "@fortawesome/free-solid-svg-icons";
import {
  defaultVisibleColumnProps,
  localizeLabel,
  makeLoadListItem,
  matchesFilters,
  sortCardIds,
} from "./deckEditorUtils";

const ROW_HEIGHT = 28;
const ADD_COL_WIDTH = 72;
const CHAR_PX = 8;
const COL_PAD = 28;
const MIN_COL = 56;
const AUTO_FIT_LIMIT = 20;

const measureColumnWidth = (headerLen, maxContentLen) => {
  const fitted = maxContentLen < AUTO_FIT_LIMIT ? maxContentLen : AUTO_FIT_LIMIT;
  const chars = Math.max(headerLen, fitted, 2);
  return Math.max(MIN_COL, chars * CHAR_PX + COL_PAD);
};

export const DeckEditorCatalog = ({
  cardDb,
  gameDef,
  language,
  pluginId,
  availableColumns,
  visibleProps,
  applyVisibleProps,
  currentGroupId,
  modifyDeckList,
  setHoverCard,
  filters,
}) => {
  const deckbuilder = gameDef?.deckbuilder || {};
  const defaultProps = useMemo(() => defaultVisibleColumnProps(gameDef), [gameDef]);
  const [pickerOpen, setPickerOpen] = useState(false);
  const pickerRef = useRef(null);
  const columns = useMemo(() => {
    const byProp = new Map((availableColumns || []).map((col) => [col.propName, col]));
    return (visibleProps || []).map((prop) => byProp.get(prop)).filter(Boolean);
  }, [availableColumns, visibleProps]);
  const scrollRef = useRef(null);
  const [scrollTop, setScrollTop] = useState(0);
  const [viewportHeight, setViewportHeight] = useState(360);
  const [sortConfig, setSortConfig] = useState({ column: null, direction: null });
  const [userWidths, setUserWidths] = useState({});
  const dragRef = useRef(null);

  const allIds = useMemo(() => {
    return Object.keys(cardDb || {}).filter((cardId) => {
      const qty = cardDb[cardId]?.A?.deckbuilderQuantity;
      return qty === undefined || qty === null || parseInt(qty, 10) !== 0;
    });
  }, [cardDb]);

  const filteredIds = useMemo(() => {
    return allIds.filter((cardId) => matchesFilters(cardDb[cardId], filters));
  }, [allIds, cardDb, filters]);

  const sortedIds = useMemo(() => {
    if (!sortConfig.column) return filteredIds;
    const integerType = gameDef?.faceProperties?.[sortConfig.column]?.type === "integer";
    return sortCardIds(filteredIds, cardDb, sortConfig.column, sortConfig.direction, integerType);
  }, [filteredIds, cardDb, sortConfig, gameDef]);

  const autoWidths = useMemo(() => {
    const widths = {};
    columns.forEach((col) => {
      const header = localizeLabel(gameDef, language, col.label) || "";
      let maxLen = 0;
      for (let i = 0; i < allIds.length; i++) {
        const value = cardDb[allIds[i]]?.A?.[col.propName];
        if (value == null || value === "") continue;
        const len = String(value).length;
        if (len > maxLen) maxLen = len;
        if (maxLen >= 40) break;
      }
      widths[col.propName] = measureColumnWidth(header.length, maxLen);
    });
    return widths;
  }, [allIds, cardDb, columns, gameDef, language]);

  const colWidth = (propName) => userWidths[propName] || autoWidths[propName] || MIN_COL;

  const tableWidth = ADD_COL_WIDTH + columns.reduce((sum, col) => sum + colWidth(col.propName), 0);

  useEffect(() => {
    setUserWidths({});
  }, [gameDef?.pluginName, columns.map((c) => c.propName).join("|")]);

  useEffect(() => {
    if (!pickerOpen) return;
    const onDown = (event) => {
      if (pickerRef.current && !pickerRef.current.contains(event.target)) setPickerOpen(false);
    };
    window.addEventListener("mousedown", onDown);
    return () => window.removeEventListener("mousedown", onDown);
  }, [pickerOpen]);

  const toggleColumn = (propName) => {
    const prev = visibleProps || [];
    if (prev.includes(propName)) {
      if (prev.length === 1) return;
      applyVisibleProps(prev.filter((prop) => prop !== propName));
      return;
    }
    const order = (availableColumns || []).map((col) => col.propName);
    applyVisibleProps(order.filter((prop) => prop === propName || prev.includes(prop)));
  };

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const measure = () => setViewportHeight(el.clientHeight || 360);
    measure();
    const ro = typeof ResizeObserver !== "undefined" ? new ResizeObserver(measure) : null;
    if (ro) ro.observe(el);
    window.addEventListener("resize", measure);
    return () => {
      if (ro) ro.disconnect();
      window.removeEventListener("resize", measure);
    };
  }, []);

  useEffect(() => {
    const onMove = (event) => {
      const drag = dragRef.current;
      if (!drag) return;
      const next = Math.max(MIN_COL, drag.startWidth + (event.clientX - drag.startX));
      setUserWidths((prev) => ({ ...prev, [drag.propName]: next }));
    };
    const onUp = () => {
      dragRef.current = null;
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
  }, []);

  const start = Math.max(0, Math.floor(scrollTop / ROW_HEIGHT) - 2);
  const visibleCount = Math.ceil(viewportHeight / ROW_HEIGHT) + 6;
  const slice = sortedIds.slice(start, start + visibleCount);

  const handleSort = (column) => {
    setSortConfig((prev) => ({
      column,
      direction: prev.column === column && prev.direction === "asc" ? "desc" : "asc",
    }));
  };

  const startResize = (event, propName) => {
    event.preventDefault();
    event.stopPropagation();
    dragRef.current = {
      propName,
      startX: event.clientX,
      startWidth: colWidth(propName),
    };
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  };

  const addCard = (cardId, quantity) => {
    if (!currentGroupId) return;
    const sideA = cardDb[cardId]?.A;
    modifyDeckList(makeLoadListItem(cardId, quantity, currentGroupId, sideA?.name, cardDb[cardId]?.author_id));
  };

  const divider = "border-r border-gray-600";

  return (
    <div className="flex flex-col min-h-0 flex-1 border-t border-gray-700">
      <div className="flex items-center px-0 py-1 text-xs text-gray-400 bg-gray-900">
        <div className="relative flex-shrink-0 flex items-center justify-center" style={{ width: ADD_COL_WIDTH }} ref={pickerRef}>
          <button
            type="button"
            className={`px-2 py-1 border rounded text-white ${pickerOpen ? "bg-red-800 border-red-500" : "border-gray-500 hover:bg-gray-700"}`}
            title="Choose columns"
            onClick={() => setPickerOpen((open) => !open)}
          >
            <FontAwesomeIcon icon={faColumns} />
          </button>
          {pickerOpen && (
            <div className="absolute left-0 top-full mt-1 z-20 w-56 max-h-72 overflow-auto bg-gray-800 border border-gray-600 rounded shadow-lg p-2 text-white">
              <div className="flex items-center justify-between mb-2">
                <span className="font-semibold">Columns</span>
                <button
                  type="button"
                  className="text-gray-300 hover:text-white"
                  onClick={() =>
                    applyVisibleProps(
                      defaultProps.filter((prop) => (availableColumns || []).some((col) => col.propName === prop))
                    )
                  }
                >
                  Defaults
                </button>
              </div>
              {availableColumns.map((col) => (
                <label key={col.propName} className="flex items-center gap-2 py-0.5 cursor-pointer hover:bg-gray-700 px-1 rounded">
                  <input
                    type="checkbox"
                    checked={visibleProps.includes(col.propName)}
                    onChange={() => toggleColumn(col.propName)}
                  />
                  <span className="truncate">{localizeLabel(gameDef, language, col.label)}</span>
                </label>
              ))}
            </div>
          )}
        </div>
        <span className="flex-1">
          {sortedIds.length.toLocaleString()} cards
          {Object.values(filters).some((v) => v) ? ` (filtered from ${allIds.length.toLocaleString()})` : ""}
        </span>
        <span className="pr-2">Double-click a row to add 1 · +1 / +4 add that many · drag a column edge to resize</span>
      </div>
      <div
        ref={scrollRef}
        className="flex-1 min-h-0 overflow-auto"
        onScroll={(e) => setScrollTop(e.target.scrollTop)}
      >
        <div style={{ width: tableWidth, minWidth: "100%" }}>
          <div
            className="sticky top-0 z-10 flex text-xs bg-gray-800 border-b border-gray-600"
            style={{ width: tableWidth }}
          >
            <div className={`flex-shrink-0 px-1 py-1 ${divider}`} style={{ width: ADD_COL_WIDTH }} />
            {columns.map((col) => {
              const isSorted = sortConfig.column === col.propName;
              const width = colWidth(col.propName);
              return (
                <div
                  key={col.propName}
                  className={`relative flex-shrink-0 px-2 py-1 text-white ${divider}`}
                  style={{ width }}
                >
                  <button
                    type="button"
                    className="flex items-center w-full text-left hover:text-red-300"
                    onClick={() => handleSort(col.propName)}
                  >
                    <span className="truncate mr-1">{localizeLabel(gameDef, language, col.label)}</span>
                    <FontAwesomeIcon icon={isSorted ? (sortConfig.direction === "asc" ? faSortUp : faSortDown) : faSort} />
                  </button>
                  <div
                    className="absolute top-0 right-0 h-full cursor-col-resize"
                    style={{ width: 8 }}
                    onMouseDown={(event) => startResize(event, col.propName)}
                  />
                </div>
              );
            })}
          </div>
          <div style={{ height: sortedIds.length * ROW_HEIGHT, position: "relative", width: tableWidth }}>
            {slice.map((cardId, i) => {
              const card = cardDb[cardId];
              const sideA = card?.A;
              if (!sideA) return null;
              const color = deckbuilder.colorKey ? deckbuilder.colorValues?.[sideA[deckbuilder.colorKey]] : null;
              return (
                <div
                  key={cardId}
                  className="absolute left-0 flex items-center text-xs text-white hover:bg-gray-600 cursor-pointer"
                  style={{
                    top: (start + i) * ROW_HEIGHT,
                    height: ROW_HEIGHT,
                    width: tableWidth,
                    color: color || undefined,
                  }}
                  onMouseEnter={() => setHoverCard(card)}
                  onMouseLeave={() => setHoverCard(null)}
                  onDoubleClick={() => addCard(cardId, 1)}
                >
                  <div
                    className={`flex-shrink-0 flex items-center justify-center gap-1 px-1 ${divider}`}
                    style={{ width: ADD_COL_WIDTH, height: ROW_HEIGHT }}
                  >
                    {[1, 4].map((n) => (
                      <button
                        key={n}
                        type="button"
                        className="w-7 h-6 leading-none border border-gray-500 rounded hover:bg-gray-400 text-center"
                        onClick={(e) => {
                          e.stopPropagation();
                          addCard(cardId, n);
                        }}
                      >
                        +{n}
                      </button>
                    ))}
                  </div>
                  {columns.map((col) => {
                    const content = sideA[col.propName];
                    const centered =
                      (typeof content === "string" && content.length === 1) ||
                      (content !== "" && content != null && !isNaN(+content));
                    return (
                      <div
                        key={col.propName}
                        className={`flex-shrink-0 px-2 truncate ${divider} ${centered ? "text-center" : ""}`}
                        style={{ width: colWidth(col.propName) }}
                        title={content == null ? "" : String(content)}
                      >
                        {content}
                      </div>
                    );
                  })}
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
};
