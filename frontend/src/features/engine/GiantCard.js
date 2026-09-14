import React, { useEffect, useMemo, useState } from "react";
import useProfile from "../../hooks/useProfile";
import { useDispatch, useSelector } from "react-redux";
import { useVisibleFace } from "./hooks/useVisibleFace";
import { useVisibleFaceSrc } from "./hooks/useVisibleFaceSrc";
import { useActiveCardId } from "./hooks/useActiveCardId";
import { useGameDefinition } from "./hooks/useGameDefinition";
import { useTouchAction } from "./hooks/useTouchAction";
import { setActiveCardId } from "../store/playerUiSlice";
import { useActiveCard } from "./hooks/useActiveCard";
import { useLayout } from "./hooks/useLayout";
import { useCardRotation } from "./hooks/useCardRotation";
import { applyImageUrlPrefix, Z_INDEX } from "./functions/common";
import { matchKeywordReminders } from "./functions/matchKeywordReminders";

const reminderPanelStyle = {
  marginTop: "0.7dvh",
  backgroundColor: "#242526",
  border: "1px solid #474a4d",
  borderRadius: 8,
  padding: "1dvh 1.2dvh",
  maxHeight: "28dvh",
  overflow: "hidden",
  boxShadow: "0 0 50px 20px black",
  color: "#dadce1",
  fontSize: "1.55dvh",
  lineHeight: 1.35,
  pointerEvents: "none",
  width: "100%",
  display: "flex",
  flexDirection: "column",
  gap: "0.7dvh",
};

export const GiantCard = React.memo(() => {
  const gameDef = useGameDefinition();
  const dispatch = useDispatch();
  const touchAction = useTouchAction();
  const touchMode = useSelector(state => state?.playerUi?.userSettings?.touchMode);
  const activeCardId = useActiveCardId();
  const activeCard = useActiveCard();
  const [initialActiveCard, setInitialActiveCard] = useState(activeCard);
  const visibleFace = useVisibleFace(activeCardId);
  const screenLeftRight = useSelector((state) => state?.playerUi?.screenLeftRight);
  const visibleFaceSrc = useVisibleFaceSrc(activeCardId);
  const user = useProfile();
  const dropdownMenu = useSelector(state => state?.playerUi?.dropdownMenu);

  console.log("Rendering GiantCard", visibleFace, visibleFaceSrc);

  useEffect(() => {
    if (activeCard && initialActiveCard && (activeCard.id == initialActiveCard.id) && (activeCard.groupId !== initialActiveCard.groupId)) {
      console.log("cardaction giant", activeCard, initialActiveCard);
      dispatch(setActiveCardId(null));
    } else {
      setInitialActiveCard(activeCard);
    }
  }, [activeCard, dispatch]);

  const layout = useLayout();
  const cardRotation = useCardRotation(activeCardId);
  const showRotationOfActiveCard = layout?.showRotationOfActiveCard || [];
  const rotationStyle = showRotationOfActiveCard.includes(cardRotation)
    ? { transform: `rotate(${cardRotation}deg)` }
    : {};
  const reminders = useMemo(() => {
    if (!visibleFace || visibleFace.type === "Rules") return [];
    return matchKeywordReminders(visibleFace.text, gameDef?.keywordReminders);
  }, [visibleFace, gameDef?.keywordReminders]);

  if (!visibleFace || !activeCardId || touchAction || (dropdownMenu && !touchMode)) return null;
  const zoomSrc = visibleFace?.zoomImageUrl
    ? applyImageUrlPrefix(visibleFace.zoomImageUrl, gameDef, user?.language)
    : null;
  const previewSrc = zoomSrc?.src || visibleFaceSrc?.src;
  const previewFallback = zoomSrc?.default || visibleFaceSrc?.default;
  const cardType = visibleFace?.type;
  const zoomFactor = gameDef?.cardTypes?.[cardType]?.zoomFactor;
  const landscape = visibleFace.height < visibleFace.width;
  let height = zoomFactor ? `${zoomFactor * 95}dvh` : "70dvh";
  if (landscape) height = "50dvh";
  else if (reminders.length) height = zoomFactor ? `${zoomFactor * 78}dvh` : "58dvh";

  const onHoverLeft = screenLeftRight === "left";
  const onHoverRight = screenLeftRight === "right";

  return (
    <div
      className="absolute"
      style={{
        right: onHoverLeft ? "3%" : "",
        left: onHoverRight ? "3%" : "",
        top: "1%",
        zIndex: Z_INDEX.GiantCard,
        display: "flex",
        flexDirection: "column",
        alignItems: onHoverLeft ? "flex-end" : "flex-start",
        maxHeight: "98dvh",
        pointerEvents: "none",
      }}
    >
      <img
        src={previewSrc}
        alt=""
        onError={(e) => {
          e.target.onerror = null;
          e.target.src = previewFallback;
        }}
        style={{
          borderRadius: "5%",
          boxShadow: "0 0 50px 20px black",
          height: height,
          display: "block",
          ...rotationStyle,
        }}
      />
      {reminders.length > 0 && (
        <div style={reminderPanelStyle}>
          {reminders.map((row) => (
            <div key={row.name}>
              <div style={{ fontWeight: 700, color: "#e8eaed", marginBottom: "0.15dvh" }}>{row.name}</div>
              <div>{row.reminder}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
});

export default GiantCard;
