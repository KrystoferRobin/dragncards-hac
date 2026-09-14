import React, { useState } from "react";
import { Redirect } from "react-router";
import axios from "axios";
import ReactModal from "react-modal";
import Button from "../../components/basic/Button";
import { useAuthOptions } from "../../hooks/useAuthOptions";
import { LimitedRoomSetup } from "../limited/LimitedRoomSetup";

ReactModal.setAppElement("#root");

const STRUCTURES = [
  { value: "two_loss_out", label: "Two-loss-out" },
  { value: "swiss", label: "Swiss" },
  { value: "single_elim", label: "Single elimination" },
  { value: "double_elim", label: "Double elimination" },
  { value: "round_robin", label: "Round robin" },
];

export const CreateTournamentModal = ({ isOpen, closeModal, plugin }) => {
  const authOptions = useAuthOptions();
  const counts = plugin?.match_player_counts?.length ? plugin.match_player_counts : [2];
  const [name, setName] = useState(`${plugin?.name || "Game"} tournament`);
  const [limited, setLimited] = useState(null);
  const [structure, setStructure] = useState("two_loss_out");
  const [bestOf, setBestOf] = useState(1);
  const [matchSize, setMatchSize] = useState(counts[0]);
  const [podSize, setPodSize] = useState(Math.min(8, counts[counts.length - 1] || 8));
  const [notes, setNotes] = useState("");
  const [announceRounds, setAnnounceRounds] = useState(false);
  const [announceFinalists, setAnnounceFinalists] = useState(true);
  const [announceWinner, setAnnounceWinner] = useState(true);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [createdId, setCreatedId] = useState(null);

  if (createdId != null) {
    return <Redirect push to={`/tournament/${createdId}`} />;
  }

  const format = limited?.mode && limited.mode !== "constructed" ? limited.mode : "constructed";

  const submit = async () => {
    setError("");
    setLoading(true);
    try {
      const res = await axios.post(
        "/be/api/v1/tournaments",
        {
          tournament: {
            plugin_id: plugin.id,
            name,
            format,
            structure,
            best_of: bestOf,
            match_size: matchSize,
            pod_size: podSize,
            notes,
            announce_rounds: announceRounds,
            announce_finalists: announceFinalists,
            announce_winner: announceWinner,
            config: format === "constructed" ? {} : {
              passDirection: limited?.passDirection,
              draftProducts: limited?.draftProducts || [],
              sealedProducts: limited?.sealedProducts || [],
            },
          },
        },
        authOptions
      );
      const id = res.data?.tournament?.tournament?.id;
      setCreatedId(id);
    } catch (err) {
      setError(err.response?.data?.error?.message || "Could not create tournament");
    }
    setLoading(false);
  };

  return (
    <ReactModal
      closeTimeoutMS={200}
      isOpen={isOpen}
      onRequestClose={closeModal}
      contentLabel="Create tournament"
      overlayClassName="fixed inset-0 bg-black-50 z-50"
      className="insert-auto p-5 bg-gray-700 border mx-auto my-12 rounded-lg outline-none text-white"
      style={{ content: { width: "420px", maxHeight: "90vh", overflow: "auto" } }}
    >
      <h1 className="mb-2 text-xl">Create tournament</h1>
      <label className="block text-sm mb-2">
        Name
        <input className="w-full text-black rounded px-2 py-1 mt-1" value={name} onChange={(e) => setName(e.target.value)} />
      </label>
      <LimitedRoomSetup plugin={plugin} value={limited} onChange={setLimited} />
      <label className="block text-sm mb-2">
        Structure
        <select className="w-full text-black rounded px-2 py-1 mt-1" value={structure} onChange={(e) => setStructure(e.target.value)}>
          {STRUCTURES.map((s) => (
            <option key={s.value} value={s.value}>{s.label}</option>
          ))}
        </select>
      </label>
      <label className="block text-sm mb-2">
        Match length
        <select className="w-full text-black rounded px-2 py-1 mt-1" value={bestOf} onChange={(e) => setBestOf(parseInt(e.target.value, 10))}>
          <option value={1}>Best of 1</option>
          <option value={3}>Best of 3</option>
        </select>
      </label>
      <label className="block text-sm mb-2">
        Match table size
        <select className="w-full text-black rounded px-2 py-1 mt-1" value={matchSize} onChange={(e) => setMatchSize(parseInt(e.target.value, 10))}>
          {counts.map((n) => (
            <option key={n} value={n}>{n} players</option>
          ))}
        </select>
      </label>
      {format !== "constructed" && (
        <label className="block text-sm mb-2">
          Draft pod size (max 8)
          <input
            type="number"
            min="2"
            max="8"
            className="w-full text-black rounded px-2 py-1 mt-1"
            value={podSize}
            onChange={(e) => setPodSize(parseInt(e.target.value, 10) || 8)}
          />
        </label>
      )}
      <label className="block text-sm mb-2">
        Announcement note
        <textarea className="w-full text-black rounded px-2 py-1 mt-1" rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} />
      </label>
      <label className="block text-sm mb-1">
        <input type="checkbox" className="mr-2" checked={announceRounds} onChange={(e) => setAnnounceRounds(e.target.checked)} />
        Announce each round in club chat
      </label>
      <label className="block text-sm mb-1">
        <input type="checkbox" className="mr-2" checked={announceFinalists} onChange={(e) => setAnnounceFinalists(e.target.checked)} />
        Announce finalists
      </label>
      <label className="block text-sm mb-3">
        <input type="checkbox" className="mr-2" checked={announceWinner} onChange={(e) => setAnnounceWinner(e.target.checked)} />
        Announce the winner
      </label>
      {error && <div className="text-red-300 text-sm mb-2">{error}</div>}
      <Button onClick={submit} disabled={loading}>{loading ? "Creating…" : "Create and announce"}</Button>
    </ReactModal>
  );
};

export default CreateTournamentModal;
