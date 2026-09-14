import React, { useState } from "react";
import { Link } from "react-router-dom";
import axios from "axios";
import { useSelector } from "react-redux";
import { useAuthOptions } from "../../hooks/useAuthOptions";
import useProfile from "../../hooks/useProfile";
import { Z_INDEX } from "../engine/functions/common";

export const TournamentMatchBar = () => {
  const tournamentId = useSelector((state) => state?.gameUi?.game?.tournamentId);
  const matchId = useSelector((state) => state?.gameUi?.game?.tournamentMatchId);
  const playerInfo = useSelector((state) => state?.gameUi?.playerInfo);
  const user = useProfile();
  const authOptions = useAuthOptions();
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);

  if (!tournamentId || !matchId) return null;

  const seats = Object.values(playerInfo || {}).filter((info) => info?.id);
  const seatedHere = seats.some((info) => info.id === user?.id);

  const report = async (winnerId) => {
    setError("");
    try {
      await axios.post(
        `/be/api/v1/tournaments/${tournamentId}/report`,
        { match_id: matchId, winner_id: winnerId },
        authOptions
      );
      setDone(true);
    } catch (err) {
      setError(err.response?.data?.error?.message || "Could not report");
    }
  };

  return (
    <div
      className="absolute left-0 right-0 top-0 px-3 py-1 bg-yellow-900 text-yellow-50 text-sm flex items-center gap-3 flex-wrap"
      style={{ zIndex: Z_INDEX.TopBarHover }}
    >
      <Link className="underline font-semibold" to={`/tournament/${tournamentId}`}>Tournament lobby</Link>
      {seatedHere && !done && seats.map((info) => (
        <button
          key={info.id}
          type="button"
          className="underline"
          onClick={() => report(info.id)}
        >
          {info.alias || info.id} won
        </button>
      ))}
      {done && <span>Result reported.</span>}
      {error && <span className="text-red-200">{error}</span>}
    </div>
  );
};
