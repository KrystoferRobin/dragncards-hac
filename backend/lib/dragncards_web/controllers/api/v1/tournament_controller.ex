defmodule DragnCardsWeb.API.V1.TournamentController do
  use DragnCardsWeb, :controller

  alias DragnCards.Tournaments

  def show(conn, %{"id" => id}) do
    user = Pow.Plug.current_user(conn)

    case Tournaments.lobby_for_user(id, user) do
      nil ->
        conn |> put_status(404) |> json(%{error: %{message: "Tournament not found"}})

      lobby ->
        json(conn, %{tournament: lobby})
    end
  end

  def open_for_plugin(conn, %{"plugin_id" => plugin_id}) do
    user = Pow.Plug.current_user(conn)

    case Tournaments.open_for_plugin(parse_int(plugin_id)) do
      nil ->
        json(conn, %{tournament: nil})

      t ->
        json(conn, %{tournament: Tournaments.lobby_for_user(t, user)})
    end
  end

  def create(conn, %{"tournament" => params}) do
    user = Pow.Plug.current_user(conn)

    case Tournaments.create_tournament(user, params) do
      {:ok, lobby} ->
        conn |> put_status(:created) |> json(%{tournament: lobby})

      {:error, :unauthorized} ->
        conn |> put_status(401) |> json(%{error: %{message: "Not authenticated"}})

      {:error, :forbidden} ->
        conn |> put_status(403) |> json(%{error: %{message: "Club admins only"}})

      {:error, :already_open} ->
        conn |> put_status(422) |> json(%{error: %{message: "This game already has an open tournament"}})

      {:error, :format_not_supported} ->
        conn |> put_status(422) |> json(%{error: %{message: "This plugin has no limited recipes"}})

      {:error, :bad_match_size} ->
        conn |> put_status(422) |> json(%{error: %{message: "Match size is not in this plugin's player counts"}})

      {:error, :not_found} ->
        conn |> put_status(404) |> json(%{error: %{message: "Plugin not found"}})

      {:error, changeset} ->
        conn |> put_status(422) |> json(%{error: %{message: "Could not create tournament", errors: format_errors(changeset)}})
    end
  end

  def register(conn, %{"id" => id}) do
    mutate(conn, fn user -> Tournaments.register(user, id) end)
  end

  def unregister(conn, %{"id" => id}) do
    mutate(conn, fn user -> Tournaments.unregister(user, id) end)
  end

  def start(conn, %{"id" => id}) do
    mutate(conn, fn user -> Tournaments.start(user, id) end)
  end

  def next_round(conn, %{"id" => id}) do
    mutate(conn, fn user -> Tournaments.next_round(user, id) end)
  end

  def cancel(conn, %{"id" => id}) do
    mutate(conn, fn user -> Tournaments.cancel(user, id) end)
  end

  def kick(conn, %{"id" => id, "user_id" => user_id} = params) do
    ban? = params["ban"] == true or params["ban"] == "true"
    mutate(conn, fn user -> Tournaments.kick(user, id, parse_int(user_id), ban?) end)
  end

  def report(conn, %{"id" => id, "match_id" => match_id, "winner_id" => winner_id}) do
    mutate(conn, fn user -> Tournaments.report_winner(user, id, parse_int(match_id), parse_int(winner_id)) end)
  end

  defp mutate(conn, fun) do
    user = Pow.Plug.current_user(conn)

    case user do
      nil ->
        conn |> put_status(401) |> json(%{error: %{message: "Not authenticated"}})

      _ ->
        case fun.(user) do
          {:ok, lobby} ->
            json(conn, %{tournament: lobby})

          {:error, :unauthorized} ->
            conn |> put_status(401) |> json(%{error: %{message: "Not authenticated"}})

          {:error, :forbidden} ->
            conn |> put_status(403) |> json(%{error: %{message: "Not allowed"}})

          {:error, :not_found} ->
            conn |> put_status(404) |> json(%{error: %{message: "Not found"}})

          {:error, :banned} ->
            conn |> put_status(403) |> json(%{error: %{message: "You are banned from this tournament"}})

          {:error, :closed} ->
            conn |> put_status(422) |> json(%{error: %{message: "Tournament is closed"}})

          {:error, :wrong_status} ->
            conn |> put_status(422) |> json(%{error: %{message: "Tournament is not in the right state for that"}})

          {:error, :not_enough_players} ->
            conn |> put_status(422) |> json(%{error: %{message: "Need at least two registered players"}})

          {:error, :already_reported} ->
            conn |> put_status(422) |> json(%{error: %{message: "That match already has a winner"}})

          {:error, :not_a_match} ->
            conn |> put_status(422) |> json(%{error: %{message: "That is a draft pod, not a match"}})

          {:error, :not_in_match} ->
            conn |> put_status(422) |> json(%{error: %{message: "Winner must be seated at that table"}})

          {:error, changeset} ->
            conn |> put_status(422) |> json(%{error: %{message: "Request failed", errors: format_errors(changeset)}})
        end
    end
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

  defp format_errors(%Ecto.Changeset{} = changeset) do
    Ecto.Changeset.traverse_errors(changeset, fn {msg, opts} ->
      Enum.reduce(opts, msg, fn {key, value}, acc ->
        String.replace(acc, "%{#{key}}", to_string(value))
      end)
    end)
  end

  defp format_errors(_), do: %{}
end
