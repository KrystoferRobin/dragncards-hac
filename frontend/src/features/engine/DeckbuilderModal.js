import React from "react";
import ReactModal from "react-modal";
import { useDispatch, useSelector } from "react-redux";
import { setShowModal, setTyping } from "../store/playerUiSlice";
import { usePlugin } from "./hooks/usePlugin";
import { useImportLoadList } from "./hooks/useImportLoadList";
import { usePlayerN } from "./hooks/usePlayerN";
import { Z_INDEX } from "./functions/common";
import { DeckEditor } from "../deckeditor/DeckEditor";
import { toTableGroupId } from "../deckeditor/deckEditorUtils";

export const DeckbuilderModal = React.memo(() => {
  const dispatch = useDispatch();
  const plugin = usePlugin();
  const playerN = usePlayerN();
  const pluginId = useSelector((state) => state?.gameUi?.game?.pluginId);
  const importLoadList = useImportLoadList();

  dispatch(setTyping(true));

  const close = () => {
    dispatch(setShowModal(null));
    dispatch(setTyping(false));
  };

  const playAtTable = (deck) => {
    if (!playerN) {
      alert("Sit down before loading a deck onto the table.");
      return;
    }
    const formatted = (deck.load_list || []).map((item) => ({
      ...item,
      loadGroupId: toTableGroupId(item.loadGroupId, playerN),
    }));
    importLoadList(formatted);
    close();
  };

  return (
    <ReactModal
      closeTimeoutMS={200}
      isOpen={true}
      onRequestClose={close}
      contentLabel="Deck editor"
      overlayClassName="fixed inset-0 bg-black-50"
      className="relative flex insert-auto overflow-hidden bg-gray-900 border mx-auto my-4 rounded-lg outline-none"
      style={{
        overlay: { zIndex: Z_INDEX.Modal },
        content: {
          width: "96vw",
          height: "92dvh",
          maxHeight: "92dvh",
        },
      }}
    >
      <DeckEditor
        plugin={{ ...plugin, id: plugin?.id || pluginId }}
        mode="table"
        playerN={playerN}
        onPlayAtTable={playAtTable}
        onClose={close}
      />
    </ReactModal>
  );
});
