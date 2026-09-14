defmodule DragnCardsWeb.API.V1.RegistrationControllerTest do
  use DragnCardsWeb.ConnCase

  @invite "test-invite"

  setup do
    System.put_env("DRAGN_INVITE_CODE", @invite)
    :ok
  end

  describe "create/2" do
    @valid_params %{
      "user" => %{
        "invite_code" => @invite,
        "password" => "secret1234",
        "password_confirmation" => "secret1234",
        "alias" => "Test User"
      }
    }
    @invalid_params %{
      "user" => %{
        "invite_code" => @invite,
        "password" => "secret1234",
        "password_confirmation" => "",
        "alias" => ""
      }
    }

    test "with valid params", %{conn: conn} do
      conn = post(conn, Routes.api_v1_registration_path(conn, :create, @valid_params))

      assert json = json_response(conn, 200)
      assert json["data"]["token"]
      assert json["data"]["renew_token"]
    end

    test "with invalid params", %{conn: conn} do
      conn = post(conn, Routes.api_v1_registration_path(conn, :create, @invalid_params))

      assert json = json_response(conn, 500)

      assert json["error"]["message"] == "Couldn't create user"
      assert json["error"]["status"] == 500
      assert json["error"]["errors"]["password_confirmation"] == ["does not match confirmation"]
      assert json["error"]["errors"]["alias"] == ["can't be blank"]
    end

    test "rejects a bad invite code", %{conn: conn} do
      params = put_in(@valid_params, ["user", "invite_code"], "nope")
      conn = post(conn, Routes.api_v1_registration_path(conn, :create, params))

      assert json = json_response(conn, 403)
      assert json["error"]["message"] == "Invalid Haven invite code."
    end
  end
end
