import React, { useCallback, useEffect, useState } from "react";
import { Link, useHistory } from "react-router-dom";
import axios from "axios";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faArrowLeft, faTrophy } from "@fortawesome/free-solid-svg-icons";
import LobbyContainer from "../lobby/LobbyContainer";
import { LobbyButton } from "../../components/basic/LobbyButton";
import useProfile from "../../hooks/useProfile";
import { useAuthOptions } from "../../hooks/useAuthOptions";
import useChannel from "../../hooks/useChannel";
import "./TournamentLobby.css";

const structureLabel = (s) => ({
  two_loss_out: "Two-loss-out",
  swiss: "Swiss",
  single_elim: "Single elimination",
  double_elim: "Double elimination",
  round_robin: "Round robin",
}[s] || s);

const formatLabel = (s) => ({
  constructed: "Constructed",
  sealed: "Sealed",
  draft: "Draft",
  sealed_draft: "Sealed draft",
}[s] || s);

export const TournamentLobby = () => {
  const history = useHistory();
  const user = useProfile();
  const authOptions = useAuthOptions();
  const parts = window.location.pathname.split("/");
  const id = parts[parts.indexOf("tournament") + 1];
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const res = await axios.get(`/be/api/v1/tournaments/${id}`, authOptions);
      setData(res.data.tournament);
      setError("");
    } catch (err) {
      setError(err.response?.data?.error?.message || "Tournament not found");
    }
  }, [id, authOptions]);

  useEffect(() => { load(); }, [load]);

  const onChannelMessage = useCallback((event) => {
    if (event === "tournament_update") load();
  }, [load]);
  useChannel(id ? `tournament:${id}` : "tournament:0", onChannelMessage, user?.id);

  const post = async (path, body = {}) => {
    setBusy(true);
    setError("");
    try {
      const res = await axios.post(`/be/api/v1/tournaments/${id}/${path}`, body, authOptions);
      setData(res.data.tournament);
    } catch (err) {
      setError(err.response?.data?.error?.message || "Request failed");
    }
    setBusy(false);
  };

  if (!data && !error) return null;
  if (error && !data) {
    return (
      <LobbyContainer maxWidth="900px">
        <div className="text-white">{error}</div>
      </LobbyContainer>
    );
  }

  const t = data.tournament;
  const you = data.you || {};
  const players = data.players || [];
  const matches = data.matches || [];
  const openMatches = matches.filter((m) => m.kind === "match" && (m.status === "playing" || m.status === "pending"));
  const pods = matches.filter((m) => m.kind === "pod");

  return (
    <LobbyContainer maxWidth="960px">
      <div className="flex items-center text-white text-xl mb-4">
        <div className="mr-2" style={{ width: "50px", height: "50px" }}>
          <LobbyButton onClick={() => history.push(`/plugin/${t.plugin_id}`)}>
            <FontAwesomeIcon icon={faArrowLeft} />
          </LobbyButton>
        </div>
        <div>
          <div className="flex items-center gap-2">
            <FontAwesomeIcon icon={faTrophy} className="text-yellow-400" />
            {t.name}
          </div>
          <div className="text-xs">
            {t.plugin_name} · {formatLabel(t.format)} · {structureLabel(t.structure)} · Bo{t.best_of} · tables of {t.match_size} · {t.status}
            {t.round ? ` · round ${t.round}` : ""}
          </div>
        </div>
      </div>

      {error && <div className="text-red-300 text-sm mb-3">{error}</div>}

      <div className="tournament-actions mb-4">
        {t.status === "registration" && user?.id && !you.registered && you.status !== "banned" && (
          <button type="button" className="tournament-gold-btn" disabled={busy} onClick={() => post("register")}>Register</button>
        )}
        {t.status === "registration" && you.registered && (
          <button type="button" className="px-3 py-2 bg-gray-600 rounded text-white" disabled={busy} onClick={() => post("unregister")}>Leave</button>
        )}
        {you.is_organizer && t.status === "registration" && (
          <button type="button" className="tournament-gold-btn" disabled={busy} onClick={() => post("start")}>Start tournament</button>
        )}
        {you.is_organizer && t.status === "in_progress" && (
          <button type="button" className="px-3 py-2 bg-gray-600 rounded text-white" disabled={busy} onClick={() => post("next_round")}>Force next round</button>
        )}
        {you.is_organizer && !["completed", "cancelled"].includes(t.status) && (
          <button type="button" className="px-3 py-2 bg-red-900 rounded text-white" disabled={busy} onClick={() => window.confirm("End this tournament early?") && post("cancel")}>End tournament</button>
        )}
      </div>

      {t.winner_alias && (
        <div className="text-yellow-300 mb-4 text-lg">{t.winner_alias} wins.</div>
      )}

      <div className="tournament-grid">
        <div>
          <h2 className="text-white text-lg mb-2">Players</h2>
          <table className="tournament-table">
            <thead>
              <tr><th>Player</th><th>W</th><th>L</th><th></th></tr>
            </thead>
            <tbody>
              {players.map((p) => (
                <tr key={p.user_id} className={p.status !== "registered" && p.status !== "active" ? "opacity-60" : ""}>
                  <td>{p.alias} <span className="text-xs text-gray-400">{p.status}</span></td>
                  <td>{p.wins}</td>
                  <td>{p.losses}</td>
                  <td>
                    {you.is_organizer && p.user_id !== user?.id && !["kicked", "banned", "completed", "cancelled"].includes(p.status) && t.status !== "completed" && t.status !== "cancelled" && (
                      <>
                        <button type="button" className="text-xs underline mr-2" onClick={() => post("kick", { user_id: p.user_id })}>Kick</button>
                        <button type="button" className="text-xs underline" onClick={() => post("kick", { user_id: p.user_id, ban: true })}>Ban</button>
                      </>
                    )}
                  </td>
                </tr>
              ))}
              {players.length === 0 && (
                <tr><td colSpan={4} className="text-gray-400">No one has registered yet.</td></tr>
              )}
            </tbody>
          </table>
        </div>
        <div>
          <h2 className="text-white text-lg mb-2">Tables</h2>
          {pods.length > 0 && (
            <div className="mb-3">
              <div className="text-sm text-gray-300 mb-1">Draft pods</div>
              {pods.map((m) => (
                <MatchRow key={m.id} match={m} />
              ))}
            </div>
          )}
          {openMatches.length === 0 && matches.filter((m) => m.kind === "match").length === 0 && (
            <div className="text-gray-400 text-sm">Pairings appear when the host starts.</div>
          )}
          {matches.filter((m) => m.kind === "match").map((m) => (
            <MatchRow
              key={m.id}
              match={m}
              canReport={you.is_organizer || (m.player_ids || []).includes(user?.id)}
              onReport={(winnerId) => post("report", { match_id: m.id, winner_id: winnerId })}
            />
          ))}
        </div>
      </div>
    </LobbyContainer>
  );
};

const MatchRow = ({ match, canReport, onReport }) => {
  const names = (match.player_aliases || []).join(" vs ");
  return (
    <div className="tournament-match">
      <div>
        {match.kind === "pod" ? "Pod" : `R${match.round}`} · {names || "Bye"}
        {match.winner_alias ? ` — ${match.winner_alias} won` : ` — ${match.status}`}
      </div>
      {match.room_slug && (
        <Link className="underline" to={`/room/${match.room_slug}`}>Open table</Link>
      )}
      {canReport && match.status === "playing" && match.kind === "match" && (match.player_ids || []).map((uid, i) => (
        <button
          key={uid}
          type="button"
          className="text-xs underline ml-2"
          onClick={() => onReport(uid)}
        >
          {match.player_aliases[i]} won
        </button>
      ))}
    </div>
  );
};

export default TournamentLobby;
