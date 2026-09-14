defmodule DragnCardsWeb.PluginsView do
  use DragnCardsWeb, :view

  defp display_author(author) when is_binary(author) do
    case String.trim(author) do
      "" -> nil
      trimmed -> trimmed
    end
  end

  defp display_author(_), do: nil

  def render("index.json", %{plugins: plugins} = assigns) do
    open = Map.get(assigns, :open_tournaments, %{})
    %{data: Enum.map(plugins, fn plugin ->
      {
        author_id,
        author_alias,
        plugin_id,
        name,
        version,
        num_favorites,
        public,
        inserted_at,
        updated_at,
        announcements,
        tutorial_url,
        banner_url,
        logo_url,
        author,
        count_24hr,
        count_30d
      } = plugin
      %{
        id: plugin_id,
        name: name,
        num_favorites: num_favorites,
        public: public,
        inserted_at: inserted_at,
        updated_at: updated_at,
        author_id: author_id,
        author_alias: author_alias,
        author: display_author(author),
        version: version,
        announcements: announcements,
        tutorial_url: tutorial_url,
        banner_url: banner_url,
        logo_url: logo_url,
        count_24hr: if count_24hr == nil do 0 else count_24hr end,
        count_30d: if count_30d == nil do 0 else count_30d end,
        open_tournament_id: Map.get(open, plugin_id)
      }
    end)}
    #%{data: render_many(plugins, PluginsView, "plugin.json")} # This wasn't working for some reason
  end
  def render("single.json", %{plugin: plugin}) do
    plugin
    #%{data: render_many(plugins, PluginsView, "plugin.json")} # This wasn't working for some reason
  end

  def render("single_info.json", %{plugin: plugin}) do
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
      lobby_links,
      limited,
      match_player_counts
    } = plugin
    open = DragnCards.Tournaments.open_for_plugin(plugin_id)
    %{data:
      %{
        id: plugin_id,
        name: name,
        num_favorites: num_favorites,
        public: public,
        updated_at: updated_at,
        author_id: author_id,
        author_alias: author_alias,
        author: display_author(author),
        version: version,
        announcements: announcements,
        tutorial_url: tutorial_url,
        banner_url: banner_url,
        logo_url: logo_url,
        lobby_links: lobby_links,
        limited: limited,
        match_player_counts: match_player_counts,
        open_tournament: if open do
          %{id: open.id, slug: open.slug, name: open.name, status: open.status}
        else
          nil
        end
      }
    }
  end
#  def render("show.json", %{plugin: plugin}) do
#    %{data: render_one(plugin, PluginsView, "plugin.json")}
#  end

#  def render("plugin.json", %{plugin: plugin}) do
#    %{
#      plugin_id: plugin.plugin_id,
#      plugin_name: plugin.plugin_name,
#      num_favorites: plugin.num_favorites,
#      user_id: plugin.user_id,
#    }
#  end
end
