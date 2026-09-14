import { useEffect } from "react";
import { useSelector } from "react-redux";
import { applyImageUrlPrefix } from "../features/engine/functions/common";
import { useGameDefinition } from "../features/engine/hooks/useGameDefinition";
import useProfile from "./useProfile";

const preloadImages = (imageUrls) => {
  imageUrls.forEach((url) => {
    const img = new Image();
    img.src = url;
  });
};

export const usePreloadCardImages = () => {
  const user = useProfile();
  const gameDef = useGameDefinition();
  const cardById = useSelector(state => state?.gameUi?.game?.cardById) || {};
  const imgUrls = Object.values(cardById).filter(card => card?.stackIndex === 0 || card?.stackIndex === 1).map(card => card?.sides?.A?.imageUrl);
  const imgUrlsWithPrefix = imgUrls
    .filter(Boolean)
    .map((url) => applyImageUrlPrefix(url, gameDef, user?.language).src)
    .filter(Boolean);
  
  const serializedImgUrls = JSON.stringify(imgUrlsWithPrefix.sort());

  useEffect(() => {
    preloadImages(imgUrlsWithPrefix);
  }, [serializedImgUrls]);
};