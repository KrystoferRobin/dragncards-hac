import React from "react";
import { useSelector } from 'react-redux';
import { CSSTransition } from 'react-transition-group';
import { DropdownItem, DropdownShell } from "./DropdownMenuHelpers";
import "../../css/custom-dropdown.css";

export const DropdownMenuFirstPlayer = React.memo(({
  mouseX,
  mouseY,
  menuHeight,
  handleDropdownClick,
  calcHeight,
  activeMenu,
}) => {
  const numPlayers = useSelector(state => state.gameUi.game.numPlayers);  
  const dropdownMenu = useSelector(state => state?.playerUi?.dropdownMenu)

  return (
    <DropdownShell mouseX={mouseX} mouseY={mouseY} measureKey={activeMenu}>
      <div className="menu-title">{dropdownMenu.title}</div>

      <CSSTransition onEnter={calcHeight} timeout={500} classNames="menu-primary" unmountOnExit
        in={activeMenu === "main"}>
        <div className="menu">
          {Array.from(Array(numPlayers), (e, i) => {
            const title = "Player " + (i + 1);
            const playerI = "player" + (i + 1);
            const actionList = [
              ["LOG", "$ALIAS_N", " set the first player to ", playerI, "."],
              ["SET", "/firstPlayer", playerI]
            ]
            return <DropdownItem action={actionList} title={title} clickCallback={handleDropdownClick}>{title}</DropdownItem>
          })}
        </div>
      </CSSTransition>
      
    </DropdownShell>
  );
})