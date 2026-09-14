import React, { useState } from "react";
import { useHistory, useParams } from "react-router-dom";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faArrowLeft } from "@fortawesome/free-solid-svg-icons";
import { RotatingLines } from "react-loader-spinner";
import { DeckEditor } from "./DeckEditor";
import { useLoadPluginPayload } from "./useLoadPluginPayload";
import CreateRoomModal from "../lobby/CreateRoomModal";
import useIsLoggedIn from "../../hooks/useIsLoggedIn";

export const DeckEditorPage = ({ match }) => {
  const params = useParams() || {};
  const pluginId = params.pluginId || match?.params?.pluginId;
  const history = useHistory();
  const isLoggedIn = useIsLoggedIn();
  const { plugin, isLoading, percentLoaded, error } = useLoadPluginPayload(pluginId);
  const [startDeck, setStartDeck] = useState(null);

  const handleStartTable = (deck) => {
    setStartDeck(deck);
  };

  if (isLoading || !plugin) {
    return (
      <div className="flex flex-col h-full items-center justify-center text-white bg-gray-900 gap-4" style={{ minHeight: "calc(100vh - 48px)" }}>
        <div className="relative flex items-center justify-center">
          <RotatingLines height={80} width={80} strokeColor="white" />
          <div className="absolute text-sm">{percentLoaded}%</div>
        </div>
        {error && <div className="text-red-400">{error}</div>}
        <div className="text-gray-400 text-sm">Loading card database…</div>
      </div>
    );
  }

  return (
    <div className="bg-gray-900" style={{ height: "calc(100vh - 48px)" }}>
      <DeckEditor
        plugin={{ ...plugin, id: plugin.id || parseInt(pluginId, 10) }}
        mode="lobby"
        onStartTable={handleStartTable}
        headerLeft={
          <button
            type="button"
            className="px-2 py-1 border border-gray-500 rounded hover:bg-gray-700"
            onClick={() => history.push("/lobby")}
            title="Back to lobby"
          >
            <FontAwesomeIcon icon={faArrowLeft} />
          </button>
        }
      />
      <CreateRoomModal
        isOpen={Boolean(startDeck)}
        isLoggedIn={isLoggedIn}
        closeModal={() => setStartDeck(null)}
        replayUuid={null}
        externalData={
          startDeck
            ? { domain: "dragn", type: "deck", id: startDeck.id }
            : null
        }
        plugin={{
          id: plugin.id,
          version: plugin.version,
          name: plugin.name || plugin.game_def?.pluginName,
        }}
      />
    </div>
  );
};

export default DeckEditorPage;
