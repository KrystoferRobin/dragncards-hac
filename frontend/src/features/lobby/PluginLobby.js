import React, { useState, useEffect } from "react";
import { useHistory } from "react-router-dom";
import CreateRoomModal from "./CreateRoomModal";
import { CreateTournamentModal } from "../tournament/CreateTournamentModal";
import LobbyTable from "./LobbyTable";
import useProfile from "../../hooks/useProfile";
import useIsLoggedIn from "../../hooks/useIsLoggedIn";
import { Announcements } from "./Announcements";
import { LobbyButton } from "../../components/basic/LobbyButton";
import LobbyContainer from "./LobbyContainer";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faArrowLeft } from "@fortawesome/free-solid-svg-icons";
import axios from "axios";
import LfgSection from "./LfgSection";
import { pluginDisplayAuthor } from "./pluginDisplayAuthor";
import "./PluginLobby.css";
import "../tournament/TournamentLobby.css";

const openLobbyLink = (url) => {
  let href = (url || "").trim();
  if (!href) return;
  if (!/^https?:\/\//i.test(href) && !href.startsWith("/")) {
    href = "https://" + href;
  }
  window.open(href, "_blank", "noopener,noreferrer");
};

const pluginLobbyLinks = (plugin) => {
  if (Array.isArray(plugin?.lobby_links) && plugin.lobby_links.length > 0) {
    return plugin.lobby_links.slice(0, 8);
  }
  const tutorial = (plugin?.tutorial_url || "").trim();
  return tutorial ? [{ label: "Tutorial", url: tutorial }] : [];
};

export const PluginLobby = () => {
  const isLoggedIn = useIsLoggedIn();
  const user = useProfile();
  const history = useHistory();
  const [plugin, setPlugin] = useState(null);
  const [showModal, setShowModal] = useState(null);
  const [replayUuid, setReplayUuid] = useState(null);
  const [externalData, setExternalData] = useState(null);
  const [isLoading, setIsLoading] = useState(true);

  const url = window.location.href;
  const splitUrl = url.split( '/' );
  const pluginIndex = splitUrl.findIndex((e) => e === "plugin")
  const pluginStr = splitUrl[pluginIndex + 1];
  const pluginId = parseInt(pluginStr);

  const getPlugin = async () => {
    try {
      const res = await axios.get(`/be/api/plugins/visible/${pluginId}/${user?.id ? user.id : 0}`);
      setPlugin(res.data.data);
    } catch (err) {
      console.log("PluginLobby err", err);
    }
    setIsLoading(false);
  }

  useEffect(() => {
    getPlugin();
  }, [user]);

  useEffect(() => {
    const href = window.location.href;
    if (href.includes("/load/")) {
      const loadIndex = splitUrl.findIndex((e) => e === "load")
      setReplayUuid(splitUrl[loadIndex + 1]);
      setShowModal("createRoom");
    }
    if (href.includes("/external/")) {
      const externalIndex = splitUrl.findIndex((e) => e === "external")
      setExternalData({
        domain: splitUrl[externalIndex + 1],
        type: splitUrl[externalIndex + 2],
        id: splitUrl[externalIndex + 3],
      });
      setShowModal("createRoom");
    }
  }, []);

  if (isLoading) return null;
  if (!isLoading && !plugin) return <div className="text-white">Plugin either does not exist or you do not have the necessary permissions to view it.</div>;

  const handleCreateRoomClick = () => {
    if (isLoggedIn) {
      if (user?.email_confirmed_at) setShowModal("createRoom");
      else alert("You must confirm your email before you can start a game.")
    } else {
      history.push("/login")
    }
  }

  const links = pluginLobbyLinks(plugin);

  return (
    <LobbyContainer maxWidth="1200px">
      <div className="flex items-center text-white text-xl mb-4">
        <div className="mr-2" style={{width: "50px", height: "50px"}}>
          <LobbyButton onClick={()=>history.push("/lobby")}>
            <FontAwesomeIcon icon={faArrowLeft} />
          </LobbyButton>
        </div>
        <div>
          {plugin?.name}
          <div className="text-xs">by {pluginDisplayAuthor(plugin)}</div>
        </div>
      </div>

      <div className="plugin-lobby-grid">
        <div className="plugin-lobby-side">
          {links.map((link, index) => (
            <button
              key={`${link.url}-${index}`}
              type="button"
              onClick={() => openLobbyLink(link.url)}
              className="plugin-lobby-side-btn bg-gray-600-30 hover:bg-red-600-30 text-white rounded-lg text-lg py-4"
              title={link.url}
            >
              {link.label || "Link"}
            </button>
          ))}
        </div>

        <div className="plugin-lobby-main">
          <Announcements plugin={plugin}/>
          <div className="mt-3">
            <LobbyTable plugin={plugin}/>
          </div>
        </div>

        <div className="plugin-lobby-side">
          {plugin?.open_tournament?.id && (
            <button
              type="button"
              onClick={() => history.push(`/tournament/${plugin.open_tournament.id}`)}
              className="plugin-lobby-side-btn plugin-lobby-tournament-btn rounded-lg text-lg py-4"
            >
              {plugin.open_tournament.status === "registration" ? "Join tournament" : "Tournament lobby"}
            </button>
          )}
          {user?.admin && !plugin?.open_tournament?.id && (
            <button
              type="button"
              onClick={() => isLoggedIn ? setShowModal("createTournament") : history.push("/login")}
              className="plugin-lobby-side-btn plugin-lobby-tournament-btn rounded-lg text-lg py-4"
            >
              Create tournament
            </button>
          )}
          <button
            type="button"
            onClick={() => handleCreateRoomClick()}
            className="plugin-lobby-side-btn bg-gray-600-30 hover:bg-red-600-30 text-white rounded-lg text-lg py-4"
          >
            {isLoggedIn ? "Create Room" : "Log in to create a room"}
          </button>
          <LfgSection plugin={plugin}/>
        </div>
      </div>

      <CreateRoomModal
        isOpen={showModal === "createRoom"}
        isLoggedIn={isLoggedIn}
        closeModal={() => setShowModal(null)}
        replayUuid={replayUuid}
        externalData={externalData}
        plugin={plugin}
      />
      <CreateTournamentModal
        isOpen={showModal === "createTournament"}
        closeModal={() => setShowModal(null)}
        plugin={plugin}
      />
    </LobbyContainer>
  );
};
export default PluginLobby;
