import React, { useState } from "react";
import { Redirect } from "react-router";
import axios from "axios";
import ReactModal from "react-modal";
import Button from "../../components/basic/Button";
import useProfile from "../../hooks/useProfile";
import { PleaseLogIn } from "./PleaseLogIn";
import { LimitedRoomSetup } from "../limited/LimitedRoomSetup";

ReactModal.setAppElement("#root");

export const CreateRoomModal = ({ 
  isOpen, 
  isLoggedIn, 
  closeModal, 
  replayUuid,
  externalData,
  plugin,
}) => {
  const [isError, setIsError] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [roomSlugCreated, setRoomSlugCreated] = useState(null);
  const [limited, setLimited] = useState(null);
  const myUser = useProfile();
  const myUserID = myUser?.id;

  const createRoom = async (privacyType) => {
    const data = { 
      room: { 
        name: "", 
        user: myUserID, 
        privacy_type: privacyType,
      },
      game_options: {
        plugin_id: plugin.id,
        plugin_version: plugin.version,
        plugin_name: plugin.name,
        replay_uuid: replayUuid,
        external_data: externalData,
        limited: limited && limited.mode && limited.mode !== "constructed" ? limited : null,
      }
    };
    setIsLoading(true);
    setIsError(false);
    try {
      const res = await axios.post("/be/api/v1/games", data);
      setIsLoading(false);
      if (res.status !== 201) {
        throw new Error("Room not created");
      }
      const room = res.data.success.room;
      setRoomSlugCreated(room.slug);
    } catch (err) {
      setIsLoading(false);
      setIsError(true);
    }
  };

  if (roomSlugCreated != null) {
    return <Redirect push to={`/room/${roomSlugCreated}`} />;
  }

  const wide = Boolean(plugin?.limited);

  return (
    <ReactModal
      closeTimeoutMS={200}
      isOpen={isOpen}
      onRequestClose={closeModal}
      contentLabel="Create New Game"
      overlayClassName="fixed inset-0 bg-black-50 z-50"
      className="insert-auto p-5 bg-gray-700 border mx-auto my-12 rounded-lg outline-none"
      style={{
        overlay: {
        },
        content: {
          width: wide ? "420px" : "300px",
        }
      }}>

      <h1 className="mb-2">Create Room</h1>
      {isLoggedIn ?
        <div className="mb-4">
          {plugin?.limited && (
            <LimitedRoomSetup plugin={plugin} value={limited} onChange={setLimited} />
          )}
          <Button onClick={() => createRoom("public")} className="mt-2" disabled={isLoading}>
            Public
          </Button>
          <Button onClick={() => createRoom("private")} className="mt-2" disabled={isLoading}>
            Private
          </Button>
          <Button isCancel onClick={closeModal} className="mt-2">
            Cancel
          </Button>
        </div>
        :
        <PleaseLogIn/>
      }
      {isError && (
        <div className="mt-2 bg-red-200 p-2 rounded border">
          Error creating room. Are you logged in?
        </div>
      )}
    </ReactModal>
  );
};
export default CreateRoomModal;
