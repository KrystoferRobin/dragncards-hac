import React, { useState } from "react";
import { useSelector } from 'react-redux';
import { DroppableRegion } from "./DroppableRegion";
import { Z_INDEX } from "./functions/common";
import { useCardScaleFactor } from "./hooks/useCardScaleFactor";
import { usePlayerN } from "./hooks/usePlayerN";
import { useGameDefinition } from "./hooks/useGameDefinition";
import { Dnc3DHudBrowse } from "../engine-dnc3d/Dnc3DHudBrowse";

const isNormalInteger = (val) => {
  var n = Math.floor(Number(val));
  return n !== Infinity && n === val && n >= 0;
}

const browseWidth = "96%";
const browseLeft = "2%";

export const useBrowseRegion = () => {
  const playerN = usePlayerN();
  const gameDef = useGameDefinition();
  const cardTypes = gameDef?.cardTypes;
  const maxHeight = 1; //Math.max(...Object.values(cardTypes).map(cardType => cardType?.height || 1));
  const browseGroupId = useSelector(state => state?.gameUi?.game?.playerData?.[playerN]?.browseGroup?.id);
  const cardScaleFactor = useCardScaleFactor();
  return {
    id: "browse",
    type: "fan",
    direction: "horizontal",
    groupId: browseGroupId,
    layerIndex: 9,
    left: browseLeft,
    width: browseWidth,
    height: `${cardScaleFactor*maxHeight*1.1 + 3}dvh`,
    top: "50%",
    disableDropAttachments: true,
  }
}


export const Browse = React.memo(({onDragEnd}) => {
  const playerN = useSelector(state => state?.playerUi?.playerN);
  const groupId = useSelector(state => state?.gameUi?.game?.playerData?.[playerN]?.browseGroup?.id);
  const browseGroupTopN = useSelector(state => state?.gameUi?.game?.playerData?.[playerN]?.browseGroup?.topN);
  const group = useSelector(state => state?.gameUi?.game?.groupById?.[groupId]);
  const region = useBrowseRegion();
  const stackIds = group?.["stackIds"] || [];
  const numStacks = stackIds.length;
  const [filteredStackIds, setFilteredStackIds] = useState(null);

  if (!group) return;

  var browseGroupTopNint = isNormalInteger(browseGroupTopN) ? parseInt(browseGroupTopN) : numStacks;
  if (browseGroupTopNint < 0) browseGroupTopNint = numStacks;
  if (browseGroupTopNint > numStacks) browseGroupTopNint = numStacks;

  const filteredStackIndices = filteredStackIds
    ? filteredStackIds.map(id => stackIds.indexOf(id)).filter(i => i >= 0)
    : [...Array(browseGroupTopNint).keys()];

  return(
    <>
      <Dnc3DHudBrowse onFilterChange={setFilteredStackIds} />
      <div
        data-browse-fan
        className="absolute rounded-lg bg-gray-700"
        style={{
          left: region.left,
          width: region.width,
          top: region.top,
          height: region.height,
          zIndex: 2*Z_INDEX.Card+2,
          boxShadow: "0 0 10px 5px rgba(0,0,0,0.6)"
        }}>
        <div className="relative h-full float-left select-none text-gray-300" style={{width:"1.7dvh"}}>
          <div className="relative w-full h-full">
            <span
              className="absolute pb-2 overflow-hidden"
              style={{fontSize: "1.5dvh", top: "50%", left: "50%", transform: `translate(-50%, -70%) rotate(90deg)`, whiteSpace: "nowrap"}}>
              (Top)
            </span>
          </div>
        </div>
        <div className="h-full" style={{marginLeft: "1.7dvh", width: "calc(100% - 1.7dvh)"}}>
          <DroppableRegion
            groupId={groupId}
            region={region}
            selectedStackIndices={filteredStackIndices}
            onDragEnd={onDragEnd}
          />
        </div>
      </div>
    </>
  )
})
