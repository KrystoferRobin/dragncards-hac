defmodule DragnCards.Tournaments.TournamentMatch do
  use Ecto.Schema
  import Ecto.Changeset

  @statuses ["pending", "playing", "reported", "cancelled"]
  @kinds ["pod", "match"]

  schema "tournament_matches" do
    field :tournament_id, :integer
    field :kind, :string, default: "match"
    field :round, :integer, default: 0
    field :status, :string, default: "pending"
    field :room_slug, :string
    field :player_ids, {:array, :integer}, default: []
    field :winner_id, :integer
    field :reported_by, :integer
    field :game_wins, :map, default: %{}

    timestamps()
  end

  def changeset(match, attrs) do
    match
    |> cast(attrs, [
      :tournament_id,
      :kind,
      :round,
      :status,
      :room_slug,
      :player_ids,
      :winner_id,
      :reported_by,
      :game_wins
    ])
    |> validate_required([:tournament_id, :kind, :round, :status, :player_ids])
    |> validate_inclusion(:status, @statuses)
    |> validate_inclusion(:kind, @kinds)
  end
end
