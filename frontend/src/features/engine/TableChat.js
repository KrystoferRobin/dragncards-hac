import React, { useEffect, useRef, useState } from "react";
import { useSelector } from "react-redux";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faComment } from "@fortawesome/free-regular-svg-icons";
import { faChevronLeft, faChevronRight } from "@fortawesome/free-solid-svg-icons";
import { Z_INDEX } from "./functions/common";
import { useMessages } from "../../contexts/MessagesContext";
import MessageBox from "../messages/MessageBox";
import "./TableChat.css";

export const TableChat = React.memo(() => {
  const touchMode = useSelector((state) => !!state?.playerUi?.userSettings?.touchMode);
  const messages = useMessages();
  const [pinned, setPinned] = useState(false);
  const [hovered, setHovered] = useState(false);
  const [unread, setUnread] = useState(false);
  const ignoreHoverRef = useRef(false);
  const seenChatCountRef = useRef(0);
  const open = pinned || hovered;

  useEffect(() => {
    const chatCount = (messages || []).filter((m) => m.sent_by !== -1).length;
    if (open) {
      seenChatCountRef.current = chatCount;
      setUnread(false);
      return;
    }
    if (chatCount > seenChatCountRef.current) setUnread(true);
  }, [messages, open]);

  const onPointerEnter = (event) => {
    if (touchMode || event.pointerType === "touch") return;
    if (ignoreHoverRef.current) return;
    setHovered(true);
  };

  const onPointerLeave = () => {
    ignoreHoverRef.current = false;
    setHovered(false);
  };

  const onHandleClick = (event) => {
    event.preventDefault();
    event.stopPropagation();
    if (pinned) {
      setPinned(false);
      setHovered(false);
      ignoreHoverRef.current = true;
    } else {
      setPinned(true);
    }
  };

  return (
    <div
      className={`table-chat-drawer${open ? " is-open" : ""}${pinned ? " is-pinned" : ""}`}
      style={{ zIndex: Z_INDEX.ChatHover }}
      onPointerEnter={onPointerEnter}
      onPointerLeave={onPointerLeave}
      onClick={(event) => event.stopPropagation()}
    >
      <button
        type="button"
        className={`table-chat-handle${unread && !open ? " is-unread" : ""}`}
        aria-expanded={open}
        aria-label={pinned ? "Close chat" : "Open chat"}
        title={pinned ? "Click to hide chat" : "Hover to peek, click to keep open"}
        onClick={onHandleClick}
      >
        <FontAwesomeIcon icon={faComment} className="table-chat-handle-icon" />
        <FontAwesomeIcon
          icon={open ? faChevronRight : faChevronLeft}
          className="table-chat-handle-icon"
        />
      </button>
      <div className="table-chat-panel" {...(!open ? { inert: "" } : {})}>
        <MessageBox hover={open} />
      </div>
    </div>
  );
});
