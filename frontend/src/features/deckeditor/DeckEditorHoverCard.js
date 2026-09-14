import React from "react";
import { resolveCardImageUrl } from "./deckEditorUtils";

export const DeckEditorHoverCard = ({ card, gameDef, language }) => {
  if (!card?.A?.imageUrl) return null;
  const faceA = resolveCardImageUrl(gameDef, language, card.A.imageUrl);
  const faceB = card.B?.imageUrl ? resolveCardImageUrl(gameDef, language, card.B.imageUrl) : null;
  const twoFaced = Boolean(faceB?.src);

  const frame = (url, fallback, extraTop) => (
    <img
      alt=""
      src={url || fallback}
      onError={(e) => {
        if (fallback && e.target.src !== fallback) e.target.src = fallback;
      }}
      className="fixed pointer-events-none"
      style={{
        top: extraTop,
        right: "0.75rem",
        height: twoFaced ? "46vh" : "58vh",
        maxWidth: "22vw",
        borderRadius: "5%",
        zIndex: 40000000,
        objectFit: "contain",
        boxShadow: "0 0 24px 8px rgba(0,0,0,0.65)",
      }}
    />
  );

  return (
    <>
      {faceA.src && frame(faceA.src, faceA.fallback, "0.6rem")}
      {faceB?.src && frame(faceB.src, faceB.fallback, "calc(0.6rem + 46vh + 0.35rem)")}
    </>
  );
};
