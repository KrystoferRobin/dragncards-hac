defmodule DragnCardsWeb.TournamentChannel do
  use DragnCardsWeb, :channel

  def join("tournament:" <> _id, _payload, socket) do
    {:ok, socket}
  end
end
