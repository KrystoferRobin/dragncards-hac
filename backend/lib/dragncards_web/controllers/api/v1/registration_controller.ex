defmodule DragnCardsWeb.API.V1.RegistrationController do
  use DragnCardsWeb, :controller

  import Ecto.Query
  alias Ecto.Changeset
  alias Plug.Conn
  alias DragnCards.Repo
  alias DragnCards.Users.User

  @spec create(Conn.t(), map()) :: Conn.t()
  def create(conn, %{"user" => user_params}) do
    invite_code = Map.get(user_params, "invite_code") || Map.get(user_params, "inviteCode")

    cond do
      not invite_configured?() ->
        conn
        |> put_status(403)
        |> json(%{
          error: %{status: 403, message: "Sign-up is disabled (no invite code configured)."}
        })

      not invite_valid?(invite_code) ->
        conn
        |> put_status(403)
        |> json(%{error: %{status: 403, message: "Invalid Haven invite code."}})

      true ->
        alias_name = user_params["alias"] || ""

        params =
          user_params
          |> Map.drop(["invite_code", "inviteCode"])
          |> Map.put("email", invite_email(alias_name))

        conn
        |> Pow.Plug.create_user(params)
        |> case do
          {:ok, user, conn} ->
            confirm_user(user)

            json(conn, %{
              data: %{
                token: conn.private[:api_auth_token],
                renew_token: conn.private[:api_renew_token]
              }
            })

          {:error, changeset, conn} ->
            conn
            |> put_status(500)
            |> json(%{
              error: %{
                status: 500,
                message: "Couldn't create user",
                errors: traverse_errors(changeset)
              }
            })
        end
    end
  end

  defp invite_configured? do
    String.trim(System.get_env("DRAGN_INVITE_CODE") || "") != ""
  end

  defp invite_valid?(given) do
    expected = String.trim(System.get_env("DRAGN_INVITE_CODE") || "")
    given = given |> to_string() |> String.trim()

    expected != "" and given != "" and
      Plug.Crypto.secure_compare(
        :crypto.hash(:sha256, expected),
        :crypto.hash(:sha256, given)
      )
  end

  defp invite_email(alias) do
    slug =
      alias
      |> to_string()
      |> String.trim()
      |> String.downcase()
      |> String.replace(~r/[^a-z0-9]+/u, "-")
      |> String.trim("-")

    slug = if slug == "", do: "player-#{System.unique_integer([:positive])}", else: slug
    "#{slug}@haven.invite"
  end

  defp confirm_user(%{id: id}) when is_integer(id) do
    now = DateTime.utc_now() |> DateTime.truncate(:second)

    from(u in User, where: u.id == ^id)
    |> Repo.update_all(set: [email_confirmed_at: now])
  end

  defp confirm_user(_), do: :ok

  defp traverse_errors(changeset) do
    Changeset.traverse_errors(changeset, fn {msg, opts} ->
      Enum.reduce(opts, msg, fn {key, value}, acc ->
        String.replace(acc, "%{#{key}}", to_string(value))
      end)
    end)
  end
end
