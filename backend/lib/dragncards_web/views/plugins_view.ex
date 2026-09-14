defmodule DragnCardsWeb.PluginsView do
  use DragnCardsWeb, :view

  defp display_author(author) when is_binary(author) do
    case String.trim(author) do
      "" -> nil
      trimmed -> trimmed
    end
  end

  defp display_author(_), do: nil

  def render("index.json", %{plugins: plugins}) do
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
        count_30d: if count_30d == nil do 0 else count_30d end
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
      author
    } = plugin
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
        logo_url: logo_url
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
