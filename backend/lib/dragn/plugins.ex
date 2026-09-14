defmodule DragnCards.Plugins do
  @moduledoc """
  The Plugins context.
  """

  import Ecto.Query, warn: false
  alias DragnCards.Repo

  alias DragnCards.{Plugins.Plugin, Users.User, UserPluginPermission, Rooms.RoomLog}

  @doc """
  Returns the list of plugins.

  ## Examples

      iex> list_plugins()
      [%Plugin{}, ...]
  """
  def list_plugins_info(user_id) do
    admin_query = from u in User,
      where: u.id == ^user_id and u.admin == true,
      select: u.id

    is_admin = Repo.exists?(admin_query)

    now = DateTime.utc_now()
    one_day_ago = DateTime.add(now, -86400)

    thirty_days_ago = DateTime.add(now, -30*86400)

    # Subquery to count games created in the last 24 hours for each plugin
    game_count_query_24hr = from rl in RoomLog,
      where: rl.inserted_at > ^one_day_ago,
      group_by: rl.plugin_id,
      select: %{plugin_id: rl.plugin_id, count: count(rl.id)}

    game_count_query_30d = from rl in RoomLog,
      where: rl.inserted_at > ^thirty_days_ago,
      group_by: rl.plugin_id,
      select: %{plugin_id: rl.plugin_id, count: count(rl.id)}

    query = from p in Plugin,
      join: u in User,
      on: [id: p.author_id],
      left_join: upp in UserPluginPermission,
      on: upp.private_access == p.id and upp.user_id == ^user_id,
      left_join: gc24hr in subquery(game_count_query_24hr),
      on: gc24hr.plugin_id == p.id,
      left_join: gc30d in subquery(game_count_query_30d),
      on: gc30d.plugin_id == p.id,
      order_by: [desc: :version],
      where: p.public == true or p.author_id == ^user_id or ^is_admin or not is_nil(upp.id),
      select: {
        p.author_id,
        u.alias,
        p.id,
        p.name,
        p.version,
        p.num_favorites,
        p.public,
        p.inserted_at,
        p.updated_at,
        p.game_def["announcements"],
        p.game_def["tutorialUrl"],
        p.game_def["bannerUrl"],
        p.game_def["logoUrl"],
        p.game_def["author"],
        gc24hr.count,
        gc30d.count
      }

    Repo.all(query)
  end



  def get_plugin_info(id, user_id) do
    admin_query = from u in User,
      where: u.id == ^user_id and u.admin == true,
      select: u.id

    is_admin = Repo.exists?(admin_query)

    query = from p in Plugin,
    join: u in User,
    on: [id: p.author_id],
    left_join: upp in UserPluginPermission,
    on: upp.private_access == p.id and upp.user_id == ^user_id,
    order_by: [desc: :version],
    where: p.id == ^id and (p.public == true or p.author_id == ^user_id or ^is_admin or not is_nil(upp.id)),
    select: {
      p.author_id,
      u.alias,
      p.id,
      p.name,
      p.version,
      p.num_favorites,
      p.public,
      p.updated_at,
      p.game_def["announcements"],
      p.game_def["tutorialUrl"],
      p.game_def["bannerUrl"],
      p.game_def["logoUrl"],
      p.game_def["author"],
      p.game_def
    }

    case Repo.one(query) do
      nil ->
        nil

      {
        author_id,
        author_alias,
        plugin_id,
        name,
        version,
        num_favorites,
        public,
        updated_at,
        announcements,
        tutorial_url,
        banner_url,
        logo_url,
        author,
        game_def
      } ->
        {
          author_id,
          author_alias,
          plugin_id,
          name,
          version,
          num_favorites,
          public,
          updated_at,
          announcements,
          tutorial_url,
          banner_url,
          logo_url,
          author,
          lobby_links(game_def),
          limited_info(game_def),
          match_player_counts(game_def)
        }
    end
  end

  def list_plugins do
    Repo.all(Plugin)
  end

  def get_game_def(id) do
    query = from p in Plugin,
    where: [id: ^id],
    select: {
      p.game_def
    }
    case Repo.one(query) do
      nil -> nil
      query_result -> elem(query_result, 0)
    end
  end

  def get_author_id(id) do
    query = from p in Plugin,
    where: [id: ^id],
    select: {
      p.author_id
    }
    case Repo.one(query) do
      nil -> nil
      query_result -> elem(query_result, 0)
    end
  end

  def get_card_db(id) do
    query = from p in Plugin,
    where: [id: ^id],
    select: {
      p.card_db
    }
    case Repo.one(query) do
      nil -> nil
      query_result -> elem(query_result, 0)
    end
  end

  def get_plugin_version(id) do
    query = from p in Plugin,
    where: [id: ^id],
    select: {
      p.version
    }
    case Repo.one(query) do
      nil -> nil
      query_result -> elem(query_result, 0)
    end
  end

  def get_plugin_name(id) do
    query = from p in Plugin,
    where: [id: ^id],
    select: {
      p.name
    }
    case Repo.one(query) do
      nil -> nil
      query_result -> elem(query_result, 0)
    end
  end

  @doc """
  Gets a single plugin.

  Raises `Ecto.NoResultsError` if the Plugin does not exist.

  ## Examples

      iex> get_plugin!(123)
      %Plugin{}

      iex> get_plugin!(456)
      ** (Ecto.NoResultsError)

  """
  def get_plugin!(id), do: Repo.get!(Plugin, id)

  @doc """
  Creates a plugin.

  ## Examples

      iex> create_plugin(%{field: value})
      {:ok, %Plugin{}}

      iex> create_plugin(%{field: bad_value})
      {:error, %Ecto.Changeset{}}

  """
  def create_plugin(attrs \\ %{}) do
    %Plugin{}
    |> Plugin.changeset(attrs)
    |> Repo.insert()
  end

  @doc """
  Updates a plugin.

  ## Examples

      iex> update_plugin(plugin, %{field: new_value})
      {:ok, %Plugin{}}

      iex> update_plugin(plugin, %{field: bad_value})
      {:error, %Ecto.Changeset{}}

  """
  def update_plugin(%Plugin{} = plugin, attrs) do
    plugin
    |> Plugin.changeset(attrs)
    |> Repo.update()
  end

  @doc """
  Deletes a plugin.

  ## Examples

      iex> delete_plugin(plugin)
      {:ok, %Plugin{}}

      iex> delete_plugin(plugin)
      {:error, %Ecto.Changeset{}}

  """
  def delete_plugin(%Plugin{} = plugin) do
    Repo.delete(plugin)
  end

  @doc """
  Returns an `%Ecto.Changeset{}` for tracking plugin changes.

  ## Examples

      iex> change_plugin(plugin)
      %Ecto.Changeset{data: %Plugin{}}

  """
  def change_plugin(%Plugin{} = plugin, attrs \\ %{}) do
    Plugin.changeset(plugin, attrs)
  end

  @max_lobby_links 8

  @doc """
  Lobby buttons from main.json: `tutorialUrl` (label Tutorial) plus up to eight
  extra links from `referenceLinks` and/or `referenceLinkNUrl` + `referenceLinkNLabel`.
  """
  def lobby_links(game_def) when is_map(game_def) do
    tutorial = trim_link(get_def(game_def, "tutorialUrl"))

    acc =
      if tutorial do
        [%{"label" => "Tutorial", "url" => tutorial}]
      else
        []
      end

    acc
    |> Kernel.++(links_from_array(get_def(game_def, "referenceLinks")))
    |> Kernel.++(links_from_numbered(game_def))
    |> Enum.reject(&(&1["url"] in [nil, ""]))
    |> Enum.uniq_by(& &1["url"])
    |> Enum.take(@max_lobby_links)
  end

  def lobby_links(_), do: []

  def limited_info(game_def) when is_map(game_def) do
    case game_def["limited"] do
      %{} = lim ->
        products =
          Enum.map(lim["products"] || %{}, fn {id, product} ->
            %{
              "id" => id,
              "label" => product["label"] || id,
              "kind" => product["kind"] || "booster",
              "set" => product["set"]
            }
          end)

        sealed_decks =
          (game_def["preBuiltDecks"] || %{})
          |> Enum.filter(fn {_id, deck} -> deck["sealed"] == true end)
          |> Enum.map(fn {id, deck} ->
            %{"id" => id, "label" => deck["label"] || id, "kind" => "prebuilt"}
          end)

        %{
          "passDirection" => lim["passDirection"] || "clockwise",
          "products" => products,
          "defaults" => lim["defaults"] || %{},
          "sealedDecks" => sealed_decks
        }

      _ ->
        nil
    end
  end

  def limited_info(_), do: nil

  def match_player_counts(game_def) when is_map(game_def) do
    (game_def["playerCountMenu"] || [])
    |> Enum.map(& &1["numPlayers"])
    |> Enum.filter(&is_integer/1)
    |> Enum.uniq()
    |> Enum.sort()
  end

  def match_player_counts(_), do: []

  defp links_from_array(list) when is_list(list) do
    Enum.flat_map(list, &normalize_link/1)
  end

  defp links_from_array(_), do: []

  defp links_from_numbered(game_def) do
    Enum.flat_map(1..@max_lobby_links, fn i ->
      url =
        trim_link(
          get_def(game_def, "referenceLink#{i}Url") ||
            get_def(game_def, "referencelink#{i}Url")
        )

      label =
        get_def(game_def, "referenceLink#{i}Label") ||
          get_def(game_def, "referencelink#{i}Label") ||
          "Link #{i}"

      if url do
        text =
          case label do
            l when is_binary(l) -> String.trim(l)
            _ -> ""
          end

        [%{"label" => fallback_label(text, i), "url" => url}]
      else
        link = get_def(game_def, "referenceLink#{i}") || get_def(game_def, "referencelink#{i}")
        normalize_link(link)
      end
    end)
  end

  defp normalize_link(%{"url" => url} = link), do: wrap_link(url, link["label"])
  defp normalize_link(%{url: url} = link), do: wrap_link(url, Map.get(link, :label) || Map.get(link, "label"))
  defp normalize_link([url, label]), do: wrap_link(url, label)
  defp normalize_link(url) when is_binary(url), do: wrap_link(url, nil)
  defp normalize_link(_), do: []

  defp wrap_link(url, label) do
    url = trim_link(url)

    if url do
      text =
        case label do
          l when is_binary(l) -> String.trim(l)
          _ -> ""
        end

      [%{"label" => fallback_label(text, 1), "url" => url}]
    else
      []
    end
  end

  defp fallback_label("", i), do: "Link #{i}"
  defp fallback_label("nil", i), do: "Link #{i}"
  defp fallback_label(label, _i), do: label

  defp trim_link(nil), do: nil

  defp trim_link(url) do
    case url |> to_string() |> String.trim() do
      "" -> nil
      trimmed -> trimmed
    end
  end

  defp get_def(map, key) when is_binary(key) do
    Map.get(map, key)
  end
end
