defmodule DragnCards.Tournaments.Tournament do
  use Ecto.Schema
  import Ecto.Changeset

  @statuses ["registration", "limited", "in_progress", "completed", "cancelled"]
  @formats ["constructed", "sealed", "draft", "sealed_draft"]
  @structures ["swiss", "single_elim", "double_elim", "round_robin", "two_loss_out"]

  schema "tournaments" do
    field :plugin_id, :integer
    field :created_by, :integer
    field :name, :string
    field :slug, :string
    field :status, :string, default: "registration"
    field :format, :string, default: "constructed"
    field :structure, :string, default: "two_loss_out"
    field :best_of, :integer, default: 1
    field :match_size, :integer, default: 2
    field :pod_size, :integer, default: 8
    field :round, :integer, default: 0
    field :config, :map, default: %{}
    field :notes, :string
    field :announce_rounds, :boolean, default: false
    field :announce_finalists, :boolean, default: true
    field :announce_winner, :boolean, default: true
    field :winner_id, :integer

    timestamps()
  end

  def changeset(tournament, attrs) do
    tournament
    |> cast(attrs, [
      :plugin_id,
      :created_by,
      :name,
      :slug,
      :status,
      :format,
      :structure,
      :best_of,
      :match_size,
      :pod_size,
      :round,
      :config,
      :notes,
      :announce_rounds,
      :announce_finalists,
      :announce_winner,
      :winner_id
    ])
    |> validate_required([:plugin_id, :created_by, :name, :slug, :status, :format, :structure, :best_of, :match_size])
    |> validate_inclusion(:status, @statuses)
    |> validate_inclusion(:format, @formats)
    |> validate_inclusion(:structure, @structures)
    |> validate_inclusion(:best_of, [1, 3])
    |> validate_number(:match_size, greater_than_or_equal_to: 2, less_than_or_equal_to: 8)
    |> validate_number(:pod_size, greater_than_or_equal_to: 2, less_than_or_equal_to: 8)
    |> unique_constraint(:slug)
    |> unique_constraint(:plugin_id, name: :tournaments_one_open_per_plugin)
  end
end
