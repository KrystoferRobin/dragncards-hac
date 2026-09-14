import React, { useContext, useMemo, useState } from "react";
import { useSelector } from "react-redux";
import BroadcastContext from "../../contexts/BroadcastContext";
import { useIsHost } from "../engine/hooks/useIsHost";
import { usePlayerN } from "../engine/hooks/usePlayerN";
import { usePlugin } from "../engine/hooks/usePlugin";
import { useGameDefinition } from "../engine/hooks/useGameDefinition";
import useProfile from "../../hooks/useProfile";
import { resolveCardImageUrl } from "../deckeditor/deckEditorUtils";
import { DeckEditor } from "../deckeditor/DeckEditor";
import { applyImageUrlPrefix, Z_INDEX } from "../engine/functions/common";
import { matchKeywordReminders } from "../engine/functions/matchKeywordReminders";
import "./LimitedOverlay.css";

const cardName = (cardDb, id) => cardDb?.[id]?.A?.name || id;

const LimitedHoverPreview = ({ card, gameDef, language, mouseOnLeft }) => {
  const face = card?.A;
  if (!face) return null;
  const zoom = face.zoomImageUrl ? applyImageUrlPrefix(face.zoomImageUrl, gameDef, language) : null;
  const img = resolveCardImageUrl(gameDef, language, face.imageUrl);
  const src = zoom?.src || img?.src;
  if (!src) return null;
  const fallback = zoom?.default || img?.fallback;
  const reminders = matchKeywordReminders(face.text, gameDef?.keywordReminders);
  const zoomFactor = gameDef?.cardTypes?.[face.type]?.zoomFactor;
  const landscape = face.height < face.width;
  let height = zoomFactor ? `${zoomFactor * 95}dvh` : "70dvh";
  if (landscape) height = "50dvh";
  else if (reminders.length) height = zoomFactor ? `${zoomFactor * 78}dvh` : "58dvh";

  return (
    <div
      className="limited-hover"
      style={{
        left: mouseOnLeft ? undefined : "3%",
        right: mouseOnLeft ? "3%" : undefined,
        alignItems: mouseOnLeft ? "flex-end" : "flex-start",
        zIndex: Z_INDEX.GiantCard,
      }}
    >
      <img
        src={src}
        alt=""
        onError={(e) => {
          if (fallback && e.target.src !== fallback) e.target.src = fallback;
        }}
        style={{ height }}
      />
      {reminders.length > 0 && (
        <div className="limited-hover-reminders">
          {reminders.map((row) => (
            <div key={row.name}>
              <div className="limited-hover-reminder-name">{row.name}</div>
              <div>{row.reminder}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

const LimitedCard = ({ cardId, cardDb, gameDef, language, pending, onClick, onHover }) => {
  const face = cardDb?.[cardId]?.A;
  const img = resolveCardImageUrl(gameDef, language, face?.imageUrl);
  return (
    <button
      type="button"
      className={`limited-card ${pending ? "is-pending" : ""}`}
      onClick={onClick}
      onMouseEnter={(event) => onHover?.(cardId, event)}
      onMouseMove={(event) => onHover?.(cardId, event)}
      onMouseLeave={() => onHover?.(null)}
    >
      {img?.src ? <img src={img.src} alt={face?.name || cardId} /> : <div className="limited-card-name">{face?.name || cardId}</div>}
      <div className="limited-card-name">{face?.name || cardId}</div>
    </button>
  );
};

export const LimitedOverlay = () => {
  const { gameBroadcast } = useContext(BroadcastContext);
  const limited = useSelector((state) => state?.gameUi?.game?.limited);
  const numPlayers = useSelector((state) => state?.gameUi?.game?.numPlayers);
  const playerInfo = useSelector((state) => state?.gameUi?.playerInfo);
  const plugin = usePlugin();
  const gameDef = useGameDefinition();
  const user = useProfile();
  const language = user?.language || "English";
  const isHost = useIsHost();
  const playerN = usePlayerN();
  const [pendingId, setPendingId] = useState(null);
  const [error, setError] = useState("");
  const [hover, setHover] = useState(null);
  const cardDb = plugin?.card_db || {};

  const handleHover = (cardId, event) => {
    if (!cardId) {
      setHover(null);
      return;
    }
    const mouseOnLeft = event.clientX < window.innerWidth / 2;
    setHover((prev) => {
      if (prev?.cardId === cardId && prev.mouseOnLeft === mouseOnLeft) return prev;
      return { cardId, mouseOnLeft };
    });
  };

  const seatedCount = useMemo(() => {
    return Object.values(playerInfo || {}).filter((info) => info?.id).length;
  }, [playerInfo]);

  if (!limited || !limited.status || limited.status === "playing") return null;

  const mine = playerN ? limited.private?.[playerN] : null;
  const pool = mine?.pool || [];
  const pack = mine?.currentPack || [];
  const waitingOn = limited.waitingOn || [];
  const committed = limited.committed || [];
  const iCommitted = playerN && committed.includes(playerN);

  const start = () => {
    setError("");
    gameBroadcast("limited_start", {});
  };

  const confirmPick = () => {
    if (!pendingId) return;
    setError("");
    gameBroadcast("limited_pick", { databaseId: pendingId });
    setPendingId(null);
  };

  const handleCommit = (deck) => {
    setError("");
    gameBroadcast("limited_commit_deck", { load_list: deck.load_list || [] });
  };

  return (
    <div className="limited-overlay" style={{ zIndex: Z_INDEX.Limited }} onClick={(e) => e.stopPropagation()}>
      <div className="limited-overlay-header">
        <div>
          <div className="font-semibold capitalize">{(limited.mode || "").replace("_", " ")} · {limited.status}</div>
          <div className="text-xs text-gray-300">
            {seatedCount}/{numPlayers} seated
            {limited.status === "drafting" && waitingOn.length > 0 ? ` · waiting on ${waitingOn.join(", ")}` : ""}
            {limited.status === "building" && committed.length ? ` · committed ${committed.length}/${seatedCount}` : ""}
          </div>
        </div>
        {error && <div className="text-red-400 text-sm">{error}</div>}
      </div>
      <div className="limited-overlay-body">
        {limited.status === "waiting" && (
          <div className="m-auto text-center">
            <p className="mb-3">
              {seatedCount < 1
                ? "Sit down, then the host can start. Empty seats are left out of the pod."
                : seatedCount === 1
                  ? "One player seated — you can start a solo draft to test picks and the deck builder."
                  : `${seatedCount} seated. Empty seats will not get packs.`}
            </p>
            {isHost ? (
              <button
                type="button"
                className="px-4 py-2 bg-red-800 rounded disabled:opacity-40"
                disabled={seatedCount < 1}
                onClick={start}
              >
                Start
              </button>
            ) : (
              <p className="text-gray-300">Waiting for the host…</p>
            )}
          </div>
        )}

        {limited.status === "drafting" && !playerN && (
          <div className="m-auto text-gray-300">Draft in progress. Spectators cannot see packs.</div>
        )}

        {limited.status === "drafting" && playerN && (
          <>
            <div className="text-xs text-gray-400 mb-1">Your picks</div>
            <div className="limited-fan">
              {pool.flatMap((item) =>
                Array.from({ length: item.quantity || 1 }, (_, i) => (
                  <LimitedCard
                    key={`${item.databaseId}-${i}`}
                    cardId={item.databaseId}
                    cardDb={cardDb}
                    gameDef={gameDef}
                    language={language}
                    onHover={handleHover}
                  />
                ))
              )}
              {pool.length === 0 && <span className="text-gray-500 text-sm">No picks yet.</span>}
            </div>
            <div className="text-xs text-gray-400 mb-1 mt-2">
              {waitingOn.includes(playerN) ? "Your pack — take one card" : "Waiting for the rest of the table…"}
            </div>
            <div className="limited-pack">
              {pack.map((id, index) => (
                <LimitedCard
                  key={`${id}-${index}`}
                  cardId={id}
                  cardDb={cardDb}
                  gameDef={gameDef}
                  language={language}
                  pending={pendingId === id}
                  onClick={() => waitingOn.includes(playerN) && setPendingId(id)}
                  onHover={handleHover}
                />
              ))}
            </div>
          </>
        )}

        {limited.status === "building" && !playerN && (
          <div className="m-auto text-gray-300">Players are building decks from their limited pools.</div>
        )}

        {limited.status === "building" && playerN && iCommitted && (
          <div className="m-auto">You committed. Waiting for the rest of the table.</div>
        )}

        {limited.status === "building" && playerN && !iCommitted && (
          <DeckEditor
            plugin={plugin}
            mode="limited"
            playerN={playerN}
            pool={pool}
            sessionId={limited.sessionId}
            onCommit={handleCommit}
          />
        )}
      </div>

      {pendingId && (
        <div className="limited-prompt">
          <div className="limited-prompt-card">
            <p className="mb-2">Take {cardName(cardDb, pendingId)}?</p>
            <LimitedCard
              cardId={pendingId}
              cardDb={cardDb}
              gameDef={gameDef}
              language={language}
              onHover={handleHover}
            />
            <div>
              <button type="button" className="yes" onClick={confirmPick}>Yes</button>
              <button type="button" onClick={() => setPendingId(null)}>No</button>
            </div>
          </div>
        </div>
      )}
      {hover?.cardId && (
        <LimitedHoverPreview
          card={cardDb[hover.cardId]}
          gameDef={gameDef}
          language={language}
          mouseOnLeft={hover.mouseOnLeft}
        />
      )}
    </div>
  );
};
