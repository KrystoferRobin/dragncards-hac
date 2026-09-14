defmodule DragnCards.HavenWebhook do
  @moduledoc """
  Posts LFG availability to a Haven chat webhook (Discord-style `{content}`).
  """

  require Logger

  def notify_lfg(post, poster_user) do
    url = webhook_url()

    if url == "" do
      :ok
    else
      plugin = DragnCards.Repo.get(DragnCards.Plugins.Plugin, post.plugin_id)
      plugin_name = if plugin, do: plugin.name, else: "a card game"
      poster = poster_user.alias || "Someone"
      content = format_lfg(post, poster, plugin_name, plugin && plugin.id)
      post_content(url, content)
    end
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

  defp post_content(url, content) do
    headers = [{"Content-Type", "application/json"}]
    body = Jason.encode!(%{content: content, username: "DragnCards LFG"})

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
