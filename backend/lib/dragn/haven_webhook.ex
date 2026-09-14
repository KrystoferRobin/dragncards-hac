defmodule DragnCards.HavenWebhook do
  @moduledoc """
  Posts LFG availability and tournament news to a Haven chat webhook (Discord-style `{content}`).
  """

  require Logger

  alias DragnCards.Repo
  alias DragnCards.Plugins.Plugin
  alias DragnCards.Users

  def notify_lfg(post, poster_user) do
    url = webhook_url()

    if url == "" do
      :ok
    else
      plugin = DragnCards.Repo.get(DragnCards.Plugins.Plugin, post.plugin_id)
      plugin_name = if plugin, do: plugin.name, else: "a card game"
      poster = poster_user.alias || "Someone"
      content = format_lfg(post, poster, plugin_name, plugin && plugin.id)
      post_content(url, content, "DragnCards LFG")
    end
  end

  def notify_tournament(tournament, event, extra \\ nil) do
    url = webhook_url()

    if url == "" do
      :ok
    else
      plugin = Repo.get(Plugin, tournament.plugin_id)
      plugin_name = if plugin, do: plugin.name, else: "a card game"
      content = format_tournament(tournament, event, plugin_name, extra)
      post_content(url, content, "DragnCards Tournaments")
    end
  rescue
    e ->
      Logger.error("Haven tournament webhook failed: #{inspect(e)}")
      :error
  end

  defp webhook_url do
    (System.get_env("HAVEN_LFG_WEBHOOK_URL") || "") |> String.trim()
  end

  defp public_url do
    (System.get_env("DRAGNCARDS_PUBLIC_URL") || "")
    |> String.trim()
    |> String.trim_trailing("/")
  end

  defp format_lfg(post, poster, plugin_name, plugin_id) do
    window = format_window(post.available_from, post.available_to)
    players = post.num_players_wanted
    exp = post.experience_level || "any"
    desc = (post.description || "") |> String.trim()
    link = lfg_link(plugin_id)

    lines = [
      "🃏 Looking for a game: **#{plugin_name}**",
      "#{poster} is available #{window} (#{players} players, #{exp})"
    ]

    lines = if desc != "", do: lines ++ [desc], else: lines
    lines = if link, do: lines ++ [link], else: lines
    Enum.join(lines, "\n")
  end

  defp lfg_link(nil), do: nil

  defp lfg_link(id) do
    case public_url() do
      "" -> nil
      base -> "#{base}/plugin/#{id}"
    end
  end

  defp format_window(from, to) do
    "#{fmt(from)} – #{fmt(to)} UTC"
  end

  defp fmt(nil), do: "?"
  defp fmt(%DateTime{} = dt), do: Calendar.strftime(dt, "%a %d %b %H:%M")
  defp fmt(%NaiveDateTime{} = dt), do: Calendar.strftime(dt, "%a %d %b %H:%M")
  defp fmt(other), do: to_string(other)

  defp format_tournament(t, :announced, plugin_name, _) do
    host = Users.get_alias(t.created_by)
    link = tournament_link(t)
    extra = (t.notes || "") |> String.trim()

    lines = [
      "🏆 Tournament open: **#{plugin_name}** — #{t.name}",
      "#{host} is running #{format_label(t.format)} / #{structure_label(t.structure)} (Bo#{t.best_of}, tables of #{t.match_size}).",
      "Join in the tournament lobby."
    ]

    lines = if extra != "", do: lines ++ [extra], else: lines
    lines = if link, do: lines ++ [link], else: lines
    Enum.join(lines, "\n")
  end

  defp format_tournament(t, :started, plugin_name, _) do
    Enum.join(
      [
        "🏆 **#{plugin_name}** — #{t.name} has started.",
        tournament_link(t)
      ]
      |> Enum.reject(&is_nil/1),
      "\n"
    )
  end

  defp format_tournament(t, :round, plugin_name, _) do
    Enum.join(
      [
        "🏆 **#{plugin_name}** — #{t.name}: round #{t.round} pairings are up.",
        tournament_link(t)
      ]
      |> Enum.reject(&is_nil/1),
      "\n"
    )
  end

  defp format_tournament(t, :finalists, plugin_name, eligible) do
    names =
      (eligible || [])
      |> Enum.map(fn p -> Users.get_alias(p.user_id) end)
      |> Enum.join(", ")

    Enum.join(
      [
        "🏆 **#{plugin_name}** — #{t.name}: finalists are #{names}.",
        tournament_link(t)
      ]
      |> Enum.reject(&is_nil/1),
      "\n"
    )
  end

  defp format_tournament(t, :winner, plugin_name, _) do
    winner = Users.get_alias(t.winner_id)

    Enum.join(
      [
        "🏆 **#{plugin_name}** — #{t.name}: **#{winner}** wins.",
        tournament_link(t)
      ]
      |> Enum.reject(&is_nil/1),
      "\n"
    )
  end

  defp format_tournament(t, :cancelled, plugin_name, _) do
    Enum.join(
      [
        "🏆 **#{plugin_name}** — #{t.name} ended early.",
        tournament_link(t)
      ]
      |> Enum.reject(&is_nil/1),
      "\n"
    )
  end

  defp format_tournament(t, _, plugin_name, _) do
    "🏆 **#{plugin_name}** — #{t.name}"
  end

  defp format_label("sealed_draft"), do: "sealed draft"
  defp format_label(other), do: other || "constructed"

  defp structure_label("two_loss_out"), do: "two-loss-out"
  defp structure_label("single_elim"), do: "single elimination"
  defp structure_label("double_elim"), do: "double elimination"
  defp structure_label("round_robin"), do: "round robin"
  defp structure_label(other), do: other || "swiss"

  defp tournament_link(t) do
    case public_url() do
      "" -> nil
      base -> "#{base}/tournament/#{t.id}"
    end
  end

  defp post_content(url, content, username) do
    headers = [{"Content-Type", "application/json"}]
    body = Jason.encode!(%{content: content, username: username})

    case HTTPoison.post(url, body, headers, recv_timeout: 8000, timeout: 8000) do
      {:ok, %{status_code: code}} when code in 200..299 ->
        :ok

      {:ok, %{status_code: code, body: resp}} ->
        Logger.error("Haven LFG webhook HTTP #{code}: #{inspect(resp)}")
        :error

      {:error, err} ->
        Logger.error("Haven LFG webhook failed: #{inspect(err)}")
        :error
    end
  end
end
