import React, { useLayoutEffect, useRef, useState } from "react";
import { faReply } from "@fortawesome/free-solid-svg-icons";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";

import "../../css/custom-dropdown.css";
import { Z_INDEX } from "./functions/common";

const MENU_PAD = 8;

export const DropdownShell = ({ mouseX, mouseY, measureKey, children }) => {
  const ref = useRef(null);
  const [pos, setPos] = useState({
    top: Math.max(MENU_PAD, (mouseY || 0) - MENU_PAD),
    left: Math.max(MENU_PAD, (mouseX || 0) + MENU_PAD),
    maxHeight: typeof window === "undefined" ? undefined : Math.max(80, window.innerHeight - MENU_PAD * 2),
  });

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el || mouseX == null || mouseY == null) return;
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const width = el.offsetWidth;
    const height = el.offsetHeight;
    const maxHeight = Math.max(80, vh - MENU_PAD * 2);

    let left = mouseX < vw / 2 ? mouseX + MENU_PAD : mouseX - width - MENU_PAD;
    left = Math.max(MENU_PAD, Math.min(left, vw - width - MENU_PAD));

    let top = mouseY - MENU_PAD;
    if (height > maxHeight) {
      top = MENU_PAD;
    } else {
      top = Math.max(MENU_PAD, Math.min(top, vh - height - MENU_PAD));
    }

    setPos((prev) => (
      prev.top === top && prev.left === left && prev.maxHeight === maxHeight
        ? prev
        : { top, left, maxHeight }
    ));
  }, [mouseX, mouseY, measureKey, children]);

  return (
    <div
      ref={ref}
      className="dropdown"
      style={{
        zIndex: Z_INDEX.DropdownMenu,
        top: pos.top,
        left: pos.left,
        maxHeight: pos.maxHeight,
      }}
    >
      {children}
    </div>
  );
};

export const calcHeightCommon = (el, setMenuHeight) => {
  const height = el.clientHeight+50;
  setMenuHeight(height);
}

export const GoBack = (props) => {
  return (
    <DropdownItem goToMenu={props.goToMenu} leftIcon={<FontAwesomeIcon icon={faReply}/>} clickCallback={props.clickCallback}>
      Go back
    </DropdownItem>
  )
}

export const DropdownItem = (props) => {
  const handleDropDownItemClick = (event) => {
    event.stopPropagation();
    props.clickCallback(props);
  }

  const handleRightIconClick = (event) => {
    event.stopPropagation(); // Prevents triggering the click event of the parent element
    if (props.rightIconClickCallback) {
      props.rightIconClickCallback(props);
    }
  }

  return (
    <a href="#" className="menu-item" onClick={(event) => handleDropDownItemClick(event)}>    
      {props.leftIcon && <span className="icon-button">{props.leftIcon}</span>}
      {props.children}
      {props.rightIconClickCallback ? 
        <span className="icon-right icon-button hover:bg-red-700" onClick={handleRightIconClick}>{props.rightIcon}</span> :
        <span className="icon-right">{props.rightIcon}</span>
      }
    </a>
  );
}

