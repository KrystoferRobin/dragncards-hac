defmodule DragnCards.Tournaments.TournamentPlayer do
  use Ecto.Schema
  import Ecto.Changeset

  @statuses ["registered", "active", "dropped", "kicked", "banned"]

  schema "tournament_players" do
    field :tournament_id, :integer
    field :user_id, :integer
    field :status, :string, default: "registered"
    field :wins, :integer, default: 0
    field :losses, :integer, default: 0
    field :draws, :integer, default: 0
    field :byes, :integer, default: 0
    field :pool, {:array, :map}, default: []
    field :load_list, {:array, :map}, default: []

    timestamps()
  end

  def changeset(player, attrs) do
    player
    |> cast(attrs, [
      :tournament_id,
      :user_id,
      :status,
      :wins,
      :losses,
      :draws,
      :byes,
      :pool,
      :load_list
    ])
    |> validate_required([:tournament_id, :user_id, :status])
    |> validate_inclusion(:status, @statuses)
    |> unique_constraint([:tournament_id, :user_id])
  end
end
