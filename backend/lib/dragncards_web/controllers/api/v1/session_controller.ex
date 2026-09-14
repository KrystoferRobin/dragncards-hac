defmodule DragnCardsWeb.API.V1.SessionController do
  use DragnCardsWeb, :controller

  alias DragnCards.Users
  alias DragnCardsWeb.APIAuthPlug
  alias Plug.Conn

  @spec create(Conn.t(), map()) :: Conn.t()
  def create(conn, %{"user" => user_params}) do
    user_params = resolve_login_identity(user_params)

    conn
    |> Pow.Plug.authenticate_user(user_params)
    |> case do
      {:ok, conn} ->
        json(conn, %{
          data: %{
            token: conn.private[:api_auth_token],
            renew_token: conn.private[:api_renew_token]
          }
        })

      {:error, conn} ->
        conn
        |> put_status(401)
        |> json(%{error: %{status: 401, message: "Invalid nickname or password"}})
    end
  end

  # Login is by nickname. Pow still authenticates on email, so we resolve alias → email.
  # A value that looks like an email is left alone (existing accounts / tests).
  defp resolve_login_identity(params) do
    alias_name = Map.get(params, "alias") || Map.get(params, "nickname")
    email = Map.get(params, "email")

    cond do
      is_binary(alias_name) and String.trim(alias_name) != "" ->
        put_email_from_alias(params, alias_name)

      is_binary(email) and not String.contains?(email, "@") ->
        put_email_from_alias(params, email)

      true ->
        params
    end
  end

  defp put_email_from_alias(params, alias_name) do
    case Users.get_user_by_alias(alias_name) do
      %{email: email} when is_binary(email) -> Map.put(params, "email", email)
      _ -> params
    end
  end

  @spec renew(Conn.t(), map()) :: Conn.t()
  def renew(conn, _params) do
    config = Pow.Plug.fetch_config(conn)

    IO.puts("session renew 1")
    # config |> IO.inspect(label: "config")

    conn = conn
    |> APIAuthPlug.renew(config)
    |> case do
      {conn, nil} ->
        # "Invalid token" |> IO.inspect()
        IO.puts("session renew fail")
        IO.inspect(conn)
        IO.inspect(config)
        conn
        |> put_status(401)
        |> json(%{error: %{status: 401, message: "Invalid token"}})

      {conn, _user} ->
        IO.puts("session renew success")
        IO.inspect(conn)
        json(conn, %{
          data: %{
            token: conn.private[:api_auth_token],
            renew_token: conn.private[:api_renew_token]
          }
        })
    end
    IO.puts("session renew 2")
    conn
  end

  @spec delete(Conn.t(), map()) :: Conn.t()
  def delete(conn, _params) do
    IO.puts("session delete 1")
    conn
    |> Pow.Plug.delete()
    |> json(%{data: %{}})
  end
end
