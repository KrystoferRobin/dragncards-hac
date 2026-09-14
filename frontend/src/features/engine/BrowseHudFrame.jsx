import React, { useCallback, useLayoutEffect, useRef, useState } from "react";
import Draggable from "react-draggable";
import "./BrowseHudFrame.css";

export const BROWSE_FAN_SELECTOR = ".dnc3d-browse-fan, [data-browse-fan]";

const GAP = 12;
const PAD = 8;
const MIN_HUD_H = 80;

function findFanEl() {
  return document.querySelector(BROWSE_FAN_SELECTOR);
}

function computePlacement(hudEl, fanEl) {
  const parent = hudEl.offsetParent || hudEl.parentElement;
  if (!parent) return null;
  const parentRect = parent.getBoundingClientRect();
  const fanRect = fanEl.getBoundingClientRect();
  // Measure unconstrained content, not the current max-height clamp
  // (otherwise we ping-pong between sides after the first shrink).
  const handle = hudEl.querySelector(".browse-hud-handle");
  const body = hudEl.querySelector(".browse-hud-body");
  const naturalH = Math.max(
    (handle?.offsetHeight || 0) + (body?.scrollHeight || 0),
    hudEl.scrollHeight,
    MIN_HUD_H,
  );
  const hudW = hudEl.offsetWidth;

  const spaceBelow = parentRect.bottom - fanRect.bottom - GAP;
  const spaceAbove = fanRect.top - parentRect.top - GAP;
  const fitsBelow = spaceBelow >= naturalH;
  const fitsAbove = spaceAbove >= naturalH;

  let side;
  if (fitsBelow && !fitsAbove) side = "below";
  else if (fitsAbove && !fitsBelow) side = "above";
  else if (fitsBelow && fitsAbove) side = "below";
  else side = spaceBelow >= spaceAbove ? "below" : "above";

  const available = Math.max(side === "below" ? spaceBelow : spaceAbove, MIN_HUD_H);
  const maxHeight = Math.min(naturalH, available, parentRect.height - 2 * PAD);

  let top = side === "below"
    ? fanRect.bottom - parentRect.top + GAP
    : fanRect.top - parentRect.top - maxHeight - GAP;
  let left = (parentRect.width - hudW) / 2;

  left = Math.max(PAD, Math.min(left, parentRect.width - hudW - PAD));
  top = Math.max(PAD, Math.min(top, parentRect.height - maxHeight - PAD));

  return { left, top, maxHeight };
}

export const BrowseHudFrame = ({ resetKey, children, style }) => {
  const nodeRef = useRef(null);
  const userDraggedRef = useRef(false);
  const [anchor, setAnchor] = useState({ left: null, top: null, maxHeight: null });
  const [dragPos, setDragPos] = useState({ x: 0, y: 0 });

  const place = useCallback(() => {
    if (userDraggedRef.current) return;
    const hudEl = nodeRef.current;
    if (!hudEl) return;
    const fanEl = findFanEl();
    if (!fanEl) return;
    const next = computePlacement(hudEl, fanEl);
    if (!next) return;
    setAnchor((prev) => {
      if (
        prev.left != null &&
        Math.abs(prev.left - next.left) < 1 &&
        Math.abs(prev.top - next.top) < 1 &&
        Math.abs((prev.maxHeight || 0) - next.maxHeight) < 1
      ) {
        return prev;
      }
      return next;
    });
  }, []);

  useLayoutEffect(() => {
    userDraggedRef.current = false;
    setDragPos({ x: 0, y: 0 });

    const hudEl = nodeRef.current;
    if (!hudEl) return;

    const ro = new ResizeObserver(() => place());
    ro.observe(hudEl);
    const parent = hudEl.offsetParent;
    if (parent) ro.observe(parent);

    window.addEventListener("resize", place);

    let frames = 0;
    let raf = 0;
    const tick = () => {
      const fan = findFanEl();
      if (!fan && frames < 90) {
        frames += 1;
        raf = requestAnimationFrame(tick);
        return;
      }
      if (fan) {
        try { ro.observe(fan); } catch { /* already observed */ }
        place();
        return;
      }
      // Fan never showed up — park the window at the top of the table
      // rather than leaving it invisible.
      const parent = hudEl.offsetParent || hudEl.parentElement;
      if (!parent) return;
      const parentRect = parent.getBoundingClientRect();
      const hudW = hudEl.offsetWidth;
      const hudH = Math.min(hudEl.offsetHeight, parentRect.height * 0.45);
      setAnchor({
        left: Math.max(PAD, (parentRect.width - hudW) / 2),
        top: PAD,
        maxHeight: hudH,
      });
    };
    raf = requestAnimationFrame(tick);

    return () => {
      ro.disconnect();
      window.removeEventListener("resize", place);
      cancelAnimationFrame(raf);
    };
  }, [resetKey, place]);

  const placed = anchor.left != null;

  return (
    <Draggable
      nodeRef={nodeRef}
      handle=".browse-hud-handle"
      cancel=".browse-hud-no-drag,input,select,textarea,button"
      bounds="parent"
      position={dragPos}
      onStart={(e) => e.stopPropagation()}
      onStop={(_e, data) => {
        userDraggedRef.current = true;
        setDragPos({ x: data.x, y: data.y });
      }}
    >
      <div
        ref={nodeRef}
        className="browse-options-hud"
        onClick={(e) => e.stopPropagation()}
        onMouseDown={(e) => e.stopPropagation()}
        style={{
          position: "absolute",
          left: placed ? anchor.left : 0,
          top: placed ? anchor.top : 0,
          maxHeight: placed ? anchor.maxHeight : undefined,
          visibility: placed ? "visible" : "hidden",
          display: "flex",
          flexDirection: "column",
          overflow: "hidden",
          zIndex: 10000,
          pointerEvents: "auto",
          ...style,
        }}
      >
        {children}
      </div>
    </Draggable>
  );
};
