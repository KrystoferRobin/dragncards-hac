defmodule DragnCards.Tournaments do
  @moduledoc """
  Club tournaments sit above rooms: registration, pods, pairings, results.
  """

  import Ecto.Query, warn: false
  require Logger

  alias DragnCards.Repo
  alias DragnCards.{Users, HavenWebhook}
  alias DragnCards.Plugins.Plugin
  alias DragnCards.Tournaments.{Tournament, TournamentPlayer, TournamentMatch, Pairing}
  alias DragnCardsUtil.NameGenerator
  alias DragnCardsUtil.Slugify
  alias DragnCardsGame.GameUISupervisor
  alias DragnCardsGame.GameUIServer
  alias DragnCards.Rooms
  alias DragnCardsWeb.Endpoint

  @open_statuses ["registration", "limited", "in_progress"]

  def get_tournament(id) when is_integer(id), do: Repo.get(Tournament, id)

  def get_tournament(id) when is_binary(id) do
    case Integer.parse(id) do
      {int, ""} -> Repo.get(Tournament, int) || Repo.get_by(Tournament, slug: id)
      _ -> Repo.get_by(Tournament, slug: id)
    end
  end

  def open_for_plugin(plugin_id) do
    from(t in Tournament,
      where: t.plugin_id == ^plugin_id,
      where: t.status in ^@open_statuses,
      order_by: [desc: t.id],
      limit: 1
    )
    |> Repo.one()
  rescue
    e ->
      Logger.error("open_for_plugin: #{inspect(e)}")
      nil
  end

  def open_plugin_ids do
    from(t in Tournament,
      where: t.status in ^@open_statuses,
      select: t.plugin_id
    )
    |> Repo.all()
    |> MapSet.new()
  rescue
    _ -> MapSet.new()
  end

  def open_by_plugin_id do
    from(t in Tournament,
      where: t.status in ^@open_statuses,
      select: {t.plugin_id, t.id}
    )
    |> Repo.all()
    |> Map.new()
  rescue
    e ->
      Logger.error("open_by_plugin_id: #{inspect(e)}")
      %{}
  end

  def create_tournament(user, attrs) do
    cond do
      is_nil(user) ->
        {:error, :unauthorized}

      user.admin != true ->
        {:error, :forbidden}

      true ->
        plugin_id = parse_int(attrs["plugin_id"] || attrs[:plugin_id])
        plugin = plugin_id && Repo.get(Plugin, plugin_id)

        cond do
          is_nil(plugin) ->
            {:error, :not_found}

          open_for_plugin(plugin_id) ->
            {:error, :already_open}

          true ->
            do_create(user, plugin, attrs)
        end
    end
  end

  def register(user, tournament_id) do
    with {:ok, t} <- fetch_open(tournament_id),
         :ok <- require_status(t, "registration") do
      existing =
        Repo.get_by(TournamentPlayer, tournament_id: t.id, user_id: user.id)

      cond do
        is_nil(user) ->
          {:error, :unauthorized}

        existing && existing.status == "banned" ->
          {:error, :banned}

        existing && existing.status in ["registered", "active"] ->
          {:ok, lobby(t)}

        existing ->
          existing
          |> TournamentPlayer.changeset(%{status: "registered", losses: 0, wins: 0})
          |> Repo.update()
          |> case do
            {:ok, _} ->
              broadcast(t)
              {:ok, lobby(t)}

            {:error, cs} ->
              {:error, cs}
          end

        true ->
          %TournamentPlayer{}
          |> TournamentPlayer.changeset(%{
            tournament_id: t.id,
            user_id: user.id,
            status: "registered"
          })
          |> Repo.insert()
          |> case do
            {:ok, _} ->
              broadcast(t)
              {:ok, lobby(t)}

            {:error, cs} ->
              {:error, cs}
          end
      end
    end
  end

  def unregister(user, tournament_id) do
    with {:ok, t} <- fetch_open(tournament_id),
         :ok <- require_status(t, "registration") do
      case Repo.get_by(TournamentPlayer, tournament_id: t.id, user_id: user.id) do
        nil ->
          {:ok, lobby(t)}

        %{status: "banned"} ->
          {:error, :banned}

        player ->
          Repo.delete(player)
          broadcast(t)
          {:ok, lobby(t)}
      end
    end
  end

  def kick(user, tournament_id, target_user_id, ban? \\ false) do
    with {:ok, t} <- fetch(tournament_id),
         :ok <- require_organizer(user, t) do
      player = Repo.get_by(TournamentPlayer, tournament_id: t.id, user_id: target_user_id)

      if is_nil(player) do
        {:error, :not_found}
      else
        out = Pairing.out_losses(t.structure)
        status = if ban?, do: "banned", else: "kicked"

        player
        |> TournamentPlayer.changeset(%{
          status: status,
          losses: max(player.losses || 0, out)
        })
        |> Repo.update()

        forfeit_open_matches(t, target_user_id, user.id)
        maybe_finish_or_continue(t)
        t = Repo.get!(Tournament, t.id)
        broadcast(t)
        {:ok, lobby(t)}
      end
    end
  end

  def cancel(user, tournament_id) do
    with {:ok, t} <- fetch(tournament_id),
         :ok <- require_organizer(user, t) do
      if t.status in ["completed", "cancelled"] do
        {:error, :closed}
      else
        from(m in TournamentMatch,
          where: m.tournament_id == ^t.id,
          where: m.status in ["pending", "playing"]
        )
        |> Repo.update_all(set: [status: "cancelled"])

        t
        |> Tournament.changeset(%{status: "cancelled"})
        |> Repo.update()

        t = Repo.get!(Tournament, t.id)
        HavenWebhook.notify_tournament(t, :cancelled)
        broadcast(t)
        {:ok, lobby(t)}
      end
    end
  end

  def start(user, tournament_id) do
    with {:ok, t} <- fetch(tournament_id),
         :ok <- require_organizer(user, t),
         :ok <- require_status(t, "registration") do
      players = registered_players(t.id)

      if length(players) < 2 do
        {:error, :not_enough_players}
      else
        Enum.each(players, fn p ->
          p
          |> TournamentPlayer.changeset(%{status: "active"})
          |> Repo.update()
        end)

        t =
          if t.format == "constructed" do
            pair_match_round(t, 1)
          else
            start_limited(t)
          end

        HavenWebhook.notify_tournament(t, :started)
        broadcast(t)
        {:ok, lobby(t)}
      end
    end
  end

  def next_round(user, tournament_id) do
    with {:ok, t} <- fetch(tournament_id),
         :ok <- require_organizer(user, t) do
      if t.status != "in_progress" do
        {:error, :wrong_status}
      else
        t = pair_match_round(t, t.round + 1)
        broadcast(t)
        {:ok, lobby(t)}
      end
    end
  end

  def report_winner(user, tournament_id, match_id, winner_id) do
    with {:ok, t} <- fetch(tournament_id) do
      match = Repo.get(TournamentMatch, match_id)

      cond do
        is_nil(match) or match.tournament_id != t.id ->
          {:error, :not_found}

        match.status == "reported" ->
          {:error, :already_reported}

        match.kind != "match" ->
          {:error, :not_a_match}

        winner_id not in (match.player_ids || []) ->
          {:error, :not_in_match}

        not can_report?(user, t, match) ->
          {:error, :forbidden}

        true ->
          apply_result(t, match, winner_id, user.id)
          t = maybe_finish_or_continue(Repo.get!(Tournament, t.id))
          broadcast(t)
          {:ok, lobby(t)}
      end
    end
  end

  def record_limited_commit(tournament_id, user_id, pool, load_list) do
    t = get_tournament(tournament_id)

    if t && t.status == "limited" do
      case Repo.get_by(TournamentPlayer, tournament_id: t.id, user_id: user_id) do
        nil ->
          :ok

        player ->
          player
          |> TournamentPlayer.changeset(%{pool: pool || [], load_list: load_list || []})
          |> Repo.update()

          maybe_advance_from_limited(t)
      end
    else
      :ok
    end
  rescue
    e ->
      Logger.error("record_limited_commit failed: #{inspect(e)}")
      :ok
  end

  def lobby(tournament_or_id) do
    t =
      case tournament_or_id do
        %Tournament{} = rec -> rec
        id -> get_tournament(id)
      end

    if is_nil(t) do
      nil
    else
      players = players_of(t.id)
      matches = matches_of(t.id)
      aliases = alias_map(Enum.map(players, & &1.user_id) ++ List.flatten(Enum.map(matches, & &1.player_ids)) ++ [t.created_by, t.winner_id])
      plugin = Repo.get(Plugin, t.plugin_id)

      %{
        tournament: serialize_tournament(t, plugin, aliases),
        players: Enum.map(players, &serialize_player(&1, aliases)),
        matches: Enum.map(matches, &serialize_match(&1, aliases))
      }
    end
  end

  def lobby_for_user(tournament_or_id, user) do
    case lobby(tournament_or_id) do
      nil ->
        nil

      data ->
        t = data.tournament
        you_player = Enum.find(data.players, &(&1.user_id == (user && user.id)))

        Map.put(data, :you, %{
          is_organizer: organizer?(user, %{created_by: t.created_by}),
          registered: you_player != nil && you_player.status in ["registered", "active"],
          status: you_player && you_player.status
        })
    end
  end

  # --- internals ---

  defp do_create(user, plugin, attrs) do
    name = String.trim(to_string(attrs["name"] || attrs[:name] || "#{plugin.name} tournament"))
    format = attrs["format"] || attrs[:format] || "constructed"
    structure = attrs["structure"] || attrs[:structure] || "two_loss_out"
    best_of = parse_int(attrs["best_of"] || attrs[:best_of]) || 1
    counts = match_counts(plugin)
    counts = if counts == [], do: [2], else: counts
    default_size = List.first(counts) || 2
    max_seats = min(8, List.last(counts) || 8)
    match_size = parse_int(attrs["match_size"] || attrs[:match_size]) || default_size
    pod_size = parse_int(attrs["pod_size"] || attrs[:pod_size]) || max_seats
    pod_size = max(2, min(max_seats, pod_size))
    slug = unique_slug(name)

    limited? = format != "constructed"
    game_def = plugin.game_def || %{}

    cond do
      limited? and is_nil(game_def["limited"]) ->
        {:error, :format_not_supported}

      match_size not in counts ->
        {:error, :bad_match_size}

      true ->
        cs =
          %Tournament{}
          |> Tournament.changeset(%{
            plugin_id: plugin.id,
            created_by: user.id,
            name: name,
            slug: slug,
            status: "registration",
            format: format,
            structure: structure,
            best_of: best_of,
            match_size: match_size,
            pod_size: pod_size,
            config: attrs["config"] || attrs[:config] || %{},
            notes: attrs["notes"] || attrs[:notes],
            announce_rounds: truthy?(attrs["announce_rounds"] || attrs[:announce_rounds]),
            announce_finalists: truthy?(attrs["announce_finalists"] || attrs[:announce_finalists], true),
            announce_winner: truthy?(attrs["announce_winner"] || attrs[:announce_winner], true)
          })

        case Repo.insert(cs) do
          {:ok, t} ->
            HavenWebhook.notify_tournament(t, :announced)
            broadcast(t)
            {:ok, lobby(t)}

          {:error, %Ecto.Changeset{errors: errors} = cs} ->
            if Keyword.has_key?(errors, :plugin_id) do
              {:error, :already_open}
            else
              {:error, cs}
            end
        end
    end
  end

  defp start_limited(t) do
    players = active_players(t.id)
    ids = Enum.map(players, & &1.user_id)
    {pods, byes} = Pairing.tables(ids, t.pod_size)

    Enum.each(byes, fn uid ->
      bump_player(t.id, uid, :byes, 1)
    end)

    Enum.each(pods, fn pod_ids ->
      {:ok, match} =
        %TournamentMatch{}
        |> TournamentMatch.changeset(%{
          tournament_id: t.id,
          kind: "pod",
          round: 0,
          status: "playing",
          player_ids: pod_ids
        })
        |> Repo.insert()

      spawn_room(t, match, pod_ids, :limited)
    end)

    t
    |> Tournament.changeset(%{status: "limited", round: 0})
    |> Repo.update()
    |> elem(1)
  end

  defp pair_match_round(t, round) do
    players = active_players(t.id)
    eligible = Pairing.eligible(players, t.structure)

    cond do
      Pairing.finished?(eligible) ->
        complete(t, List.first(eligible))

      true ->
        ids = Enum.map(eligible, & &1.user_id)
        {tables, byes} = Pairing.tables(ids, t.match_size)

        Enum.each(byes, fn uid ->
          bump_player(t.id, uid, :byes, 1)
        end)

        Enum.each(tables, fn table_ids ->
          {:ok, match} =
            %TournamentMatch{}
            |> TournamentMatch.changeset(%{
              tournament_id: t.id,
              kind: "match",
              round: round,
              status: "playing",
              player_ids: table_ids
            })
            |> Repo.insert()

          spawn_room(t, match, table_ids, :match)
        end)

        t
        |> Tournament.changeset(%{status: "in_progress", round: round})
        |> Repo.update()
        |> elem(1)
        |> tap(fn updated ->
          if updated.announce_rounds, do: HavenWebhook.notify_tournament(updated, :round)
        end)
    end
  end

  defp maybe_advance_from_limited(t) do
    players = active_players(t.id)
    pods = matches_of(t.id) |> Enum.filter(&(&1.kind == "pod" and &1.status == "playing"))

    committed =
      Enum.filter(players, fn p -> (p.load_list || []) != [] end)
      |> Enum.map(& &1.user_id)
      |> MapSet.new()

    Enum.each(pods, fn pod ->
      if Enum.all?(pod.player_ids, &MapSet.member?(committed, &1)) do
        pod
        |> TournamentMatch.changeset(%{status: "reported"})
        |> Repo.update()
      end
    end)

    still =
      from(m in TournamentMatch,
        where: m.tournament_id == ^t.id,
        where: m.kind == "pod",
        where: m.status in ["pending", "playing"]
      )
      |> Repo.exists?()

    unless still do
      t = Repo.get!(Tournament, t.id)
      pair_match_round(t, 1)
      broadcast(t)
    end
  end

  defp spawn_room(t, match, player_ids, kind) do
    host = Users.get_user(List.first(player_ids)) || Users.get_user(t.created_by)
    plugin = Repo.get(Plugin, t.plugin_id)
    game_name = NameGenerator.generate()
    num_players = length(player_ids)

    limited =
      if kind == :limited and t.format != "constructed" do
        Map.merge(t.config || %{}, %{
          "mode" => t.format,
          "numPlayers" => num_players,
          "tournamentId" => t.id
        })
      else
        nil
      end

    options = %{
      "privacyType" => "private",
      "pluginId" => t.plugin_id,
      "pluginVersion" => plugin && plugin.version,
      "pluginName" => plugin && plugin.name,
      "numPlayers" => num_players,
      "tournamentId" => t.id,
      "tournamentMatchId" => match.id,
      "limited" => limited
    }

    GameUISupervisor.start_game(game_name, host, options)
    room = Rooms.get_room_by_name(game_name)

    if room do
      match
      |> TournamentMatch.changeset(%{room_slug: room.slug, status: "playing"})
      |> Repo.update()

      Enum.with_index(player_ids, 1)
      |> Enum.each(fn {uid, i} ->
        try do
          GameUIServer.set_seat(room.slug, uid, "player#{i}", uid)
        rescue
          e -> Logger.error("tournament seat #{i}: #{inspect(e)}")
        end
      end)
    else
      Logger.error("Failed to create tournament room for match #{match.id}")
    end
  end

  defp apply_result(t, match, winner_id, reporter_id) do
    match
    |> TournamentMatch.changeset(%{
      status: "reported",
      winner_id: winner_id,
      reported_by: reporter_id
    })
    |> Repo.update()

    Enum.each(match.player_ids || [], fn uid ->
      if uid == winner_id do
        bump_player(t.id, uid, :wins, 1)
      else
        bump_player(t.id, uid, :losses, 1)
      end
    end)
  end

  defp forfeit_open_matches(t, target_user_id, reporter_id) do
    from(m in TournamentMatch,
      where: m.tournament_id == ^t.id,
      where: m.kind == "match",
      where: m.status in ["pending", "playing"]
    )
    |> Repo.all()
    |> Enum.filter(&(target_user_id in (&1.player_ids || [])))
    |> Enum.each(fn match ->
      others = Enum.reject(match.player_ids || [], &(&1 == target_user_id))

      cond do
        length(others) == 1 ->
          apply_result(t, match, hd(others), reporter_id)

        length(others) > 1 ->
          match
          |> TournamentMatch.changeset(%{
            player_ids: others,
            status: "playing"
          })
          |> Repo.update()

        true ->
          match
          |> TournamentMatch.changeset(%{status: "cancelled"})
          |> Repo.update()
      end
    end)
  end

  defp maybe_finish_or_continue(t) do
    t = Repo.get!(Tournament, t.id)

    if t.status in ["completed", "cancelled"] do
      t
    else
      open? =
        from(m in TournamentMatch,
          where: m.tournament_id == ^t.id,
          where: m.kind == "match",
          where: m.round == ^t.round,
          where: m.status in ["pending", "playing"]
        )
        |> Repo.exists?()

      if open? do
        t
      else
        players = active_players(t.id)
        eligible = Pairing.eligible(players, t.structure)

        cond do
          Pairing.finished?(eligible) ->
            complete(t, List.first(eligible))

          t.status == "limited" ->
            t

          true ->
            maybe_announce_finalists(t, eligible)
            pair_match_round(t, t.round + 1)
        end
      end
    end
  end

  defp maybe_announce_finalists(t, eligible) do
    if t.announce_finalists and length(eligible) <= t.match_size and length(eligible) >= 2 do
      HavenWebhook.notify_tournament(t, :finalists, eligible)
    end
  end

  defp complete(t, winner_player) do
    winner_id = winner_player && winner_player.user_id

    t
    |> Tournament.changeset(%{status: "completed", winner_id: winner_id})
    |> Repo.update()

    t = Repo.get!(Tournament, t.id)
    if t.announce_winner, do: HavenWebhook.notify_tournament(t, :winner)
    t
  end

  defp bump_player(tournament_id, user_id, field, delta) do
    player = Repo.get_by(TournamentPlayer, tournament_id: tournament_id, user_id: user_id)

    if player do
      player
      |> TournamentPlayer.changeset(%{field => Map.get(player, field) + delta})
      |> Repo.update()
    end
  end

  defp registered_players(tid) do
    from(p in TournamentPlayer,
      where: p.tournament_id == ^tid,
      where: p.status in ["registered", "active"]
    )
    |> Repo.all()
  end

  defp active_players(tid) do
    from(p in TournamentPlayer, where: p.tournament_id == ^tid, where: p.status == "active")
    |> Repo.all()
  end

  defp players_of(tid) do
    from(p in TournamentPlayer, where: p.tournament_id == ^tid, order_by: [asc: p.inserted_at])
    |> Repo.all()
  end

  defp matches_of(tid) do
    from(m in TournamentMatch, where: m.tournament_id == ^tid, order_by: [asc: m.id])
    |> Repo.all()
  end

  defp fetch(id) do
    case get_tournament(id) do
      nil -> {:error, :not_found}
      t -> {:ok, t}
    end
  end

  defp fetch_open(id) do
    with {:ok, t} <- fetch(id) do
      if t.status in @open_statuses, do: {:ok, t}, else: {:error, :closed}
    end
  end

  defp require_status(t, status) do
    if t.status == status, do: :ok, else: {:error, :wrong_status}
  end

  defp require_organizer(user, t) do
    if organizer?(user, t), do: :ok, else: {:error, :forbidden}
  end

  def organizer?(user, t) when is_map(t) do
    user != nil and (user.admin == true or user.id == t.created_by)
  end

  defp can_report?(user, t, match) do
    organizer?(user, t) or (user != nil and user.id in (match.player_ids || []))
  end

  defp broadcast(t) do
    Endpoint.broadcast("tournament:#{t.id}", "tournament_update", %{id: t.id})
  end

  defp match_counts(plugin) do
    (get_in(plugin.game_def || %{}, ["playerCountMenu"]) || [])
    |> Enum.map(& &1["numPlayers"])
    |> Enum.filter(&is_integer/1)
    |> Enum.uniq()
    |> Enum.sort()
  end

  defp unique_slug(name) do
    base = Slugify.slugify(name)
    base = if base == "" or base == "-", do: "tournament", else: base
    "#{base}-#{String.slice(Ecto.UUID.generate(), 0, 8)}"
  end

  defp parse_int(nil), do: nil
  defp parse_int(n) when is_integer(n), do: n
  defp parse_int(n) when is_binary(n) do
    case Integer.parse(n) do
      {i, _} -> i
      :error -> nil
    end
  end
  defp parse_int(_), do: nil

  defp truthy?(val, default \\ false)
  defp truthy?(nil, default), do: default
  defp truthy?(true, _), do: true
  defp truthy?(false, _), do: false
  defp truthy?("true", _), do: true
  defp truthy?("false", _), do: false
  defp truthy?(_, default), do: default

  defp alias_map(ids) do
    ids
    |> Enum.filter(&is_integer/1)
    |> Enum.uniq()
    |> Enum.reduce(%{}, fn id, acc -> Map.put(acc, id, Users.get_alias(id)) end)
  end

  defp serialize_tournament(t, plugin, aliases) do
    %{
      id: t.id,
      slug: t.slug,
      name: t.name,
      plugin_id: t.plugin_id,
      plugin_name: plugin && plugin.name,
      status: t.status,
      format: t.format,
      structure: t.structure,
      best_of: t.best_of,
      match_size: t.match_size,
      pod_size: t.pod_size,
      round: t.round,
      created_by: t.created_by,
      created_by_alias: Map.get(aliases, t.created_by),
      notes: t.notes,
      config: t.config,
      announce_rounds: t.announce_rounds,
      announce_finalists: t.announce_finalists,
      announce_winner: t.announce_winner,
      winner_id: t.winner_id,
      winner_alias: Map.get(aliases, t.winner_id)
    }
  end

  defp serialize_player(p, aliases) do
    %{
      user_id: p.user_id,
      alias: Map.get(aliases, p.user_id),
      status: p.status,
      wins: p.wins,
      losses: p.losses,
      byes: p.byes
    }
  end

  defp serialize_match(m, aliases) do
    %{
      id: m.id,
      kind: m.kind,
      round: m.round,
      status: m.status,
      room_slug: m.room_slug,
      player_ids: m.player_ids,
      player_aliases: Enum.map(m.player_ids || [], &Map.get(aliases, &1)),
      winner_id: m.winner_id,
      winner_alias: Map.get(aliases, m.winner_id)
    }
  end
end
