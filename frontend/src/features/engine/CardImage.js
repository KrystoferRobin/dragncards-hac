import React from "react";
import { useVisibleFaceSrc } from "./hooks/useVisibleFaceSrc";

export const CardImage = React.memo(({
    cardId,
}) => { 
    const visibleFaceSrc = useVisibleFaceSrc(cardId);
    if (!visibleFaceSrc?.src) return null;
    return(
        <img className="absolute w-full h-full" style={{borderRadius: '0.6dvh'}} src={visibleFaceSrc.src} onError={(e)=>{e.target.onerror = null; e.target.src=visibleFaceSrc.default}} />
    )
})