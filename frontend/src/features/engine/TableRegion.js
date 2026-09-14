import React from "react";
import { useSelector } from 'react-redux';
import { Group } from "./Group";
import { DEFAULT_CARD_Z_INDEX, convertToPercentage } from "./functions/common";
import { usePlayerN } from "./hooks/usePlayerN";
import { useLayout } from "./hooks/useLayout";
import { useDoActionList } from "./hooks/useDoActionList";
import { useGroupProp } from "./hooks/useGroupProp";
import { useSiteL10n } from "../../hooks/useSiteL10n";

const isProvinceGroup = (groupId) => /Province[1-4]$/.test(groupId || "");
const isPlayerFavorGroup = (groupId) => /Favor$/.test(groupId || "") && groupId !== "sharedFavor";

export const TableRegion = React.memo(({
  region,
  onDragEnd
}) => {
  console.log("Rendering TableRegion", region);
  const playerN = usePlayerN();
  const layout = useLayout();
  const doActionList = useDoActionList();
  const siteL10n = useSiteL10n();
  const destroyed = useGroupProp(region.groupId, "destroyed");
  const browseGroupId = useSelector(state => state?.gameUi?.game?.playerData?.[playerN]?.browseGroup?.id);
  const hideGroup = (region.groupId === browseGroupId);
  const draggingStackId = useSelector(state => state?.playerUi?.dragging?.stackId);
  const droppableId = region.groupId + "--" + region.type + "--" + region.direction; 
  const draggingFromThisDroppableId = useSelector(state => state?.playerUi?.dragging?.fromDroppableId === droppableId);
  var zIndex = undefined;
  if (region.layerIndex > 0) zIndex = DEFAULT_CARD_Z_INDEX * region.layerIndex + 2;
  // if (draggingFromThisDroppableId == droppableId) zIndex = 10*DEFAULT_CARD_Z_INDEX + 2;
  console.log("TableRegion 1", draggingStackId);
  const regionStyle = {
    ...region?.style,
    top: convertToPercentage(region.top),
    left: convertToPercentage(region.left),
    width: convertToPercentage(region.width),
    height: convertToPercentage(region.height),
    zIndex: zIndex,
  }
  if (layout?.testBorders) {
    regionStyle.border = "1px solid red";
  }
  if (destroyed) {
    regionStyle.boxShadow = "inset 0 0 0 2px rgba(180, 40, 40, 0.85)";
    regionStyle.background = regionStyle.background
      ? regionStyle.background
      : "rgba(90, 16, 16, 0.28)";
  }
  const handleWreck = (event) => {
    event.stopPropagation();
    if (!playerN) {
      alert(siteL10n("pleaseSit"));
      return;
    }
    doActionList(
      ["TOGGLE_PROVINCE_DESTROYED", region.groupId],
      `Toggle destroyed on ${region.groupId}`
    );
  };
  const handleClaimFavor = (event) => {
    event.stopPropagation();
    if (!playerN) {
      alert(siteL10n("pleaseSit"));
      return;
    }
    doActionList(
      ["CLAIM_FAVOR", playerN],
      "Claim Imperial Favor"
    );
  };
  return (
    <div
      className="absolute"
      //onMouseEnter={(e) => {e.stopPropagation();}}
      style={regionStyle}
    >
      {hideGroup ? null :
        <Group
          groupId={region.groupId}
          region={region}
          onDragEnd={onDragEnd}
        />
      }
      {isProvinceGroup(region.groupId) &&
        <button
          type="button"
          title={destroyed ? "Restore this province" : "Destroy this province"}
          aria-pressed={!!destroyed}
          onClick={handleWreck}
          className="absolute flex items-center justify-center select-none"
          style={{
            left: "0.15dvh",
            bottom: "0.15dvh",
            width: "1.7dvh",
            height: "1.7dvh",
            padding: 0,
            borderRadius: "0.25dvh",
            border: destroyed ? "1px solid rgba(220,80,80,0.95)" : "1px solid rgba(180,180,180,0.45)",
            background: destroyed ? "rgba(140,24,24,0.92)" : "rgba(20,20,20,0.72)",
            color: destroyed ? "#ffd0d0" : "#d4d4d4",
            fontSize: "1.35dvh",
            lineHeight: 1,
            zIndex: DEFAULT_CARD_Z_INDEX + 8,
            cursor: "pointer",
          }}
        >
          ×
        </button>
      }
      {isPlayerFavorGroup(region.groupId) &&
        <button
          type="button"
          title="Claim the Imperial Favor"
          onClick={handleClaimFavor}
          className="absolute flex items-center justify-center select-none"
          style={{
            left: "0.15dvh",
            bottom: "0.15dvh",
            width: "1.7dvh",
            height: "1.7dvh",
            padding: 0,
            borderRadius: "0.25dvh",
            border: "1px solid rgba(212,175,55,0.7)",
            background: "rgba(20,20,20,0.72)",
            color: "#e8d48a",
            fontSize: "1.15dvh",
            fontWeight: 700,
            lineHeight: 1,
            zIndex: DEFAULT_CARD_Z_INDEX + 8,
            cursor: "pointer",
          }}
        >
          F
        </button>
      }
    </div>
  )
})