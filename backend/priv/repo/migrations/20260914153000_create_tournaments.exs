defmodule DragnCards.Repo.Migrations.CreateTournaments do
  use Ecto.Migration

  def change do
    create table(:tournaments) do
      add :plugin_id, references(:plugins, on_delete: :delete_all), null: false
      add :created_by, references(:users, on_delete: :nilify_all)
      add :name, :string, null: false
      add :slug, :string, null: false
      add :status, :string, null: false, default: "registration"
      add :format, :string, null: false, default: "constructed"
      add :structure, :string, null: false, default: "two_loss_out"
      add :best_of, :integer, null: false, default: 1
      add :match_size, :integer, null: false, default: 2
      add :pod_size, :integer, null: false, default: 8
      add :round, :integer, null: false, default: 0
      add :config, :map, null: false, default: %{}
      add :notes, :text
      add :announce_rounds, :boolean, null: false, default: false
      add :announce_finalists, :boolean, null: false, default: true
      add :announce_winner, :boolean, null: false, default: true
      add :winner_id, :integer

      timestamps()
    end

    create unique_index(:tournaments, [:slug])
    create index(:tournaments, [:plugin_id])
    create index(:tournaments, [:status])

    create unique_index(:tournaments, [:plugin_id],
      name: :tournaments_one_open_per_plugin,
      where: "status IN ('registration', 'limited', 'in_progress')"
    )

    create table(:tournament_players) do
      add :tournament_id, references(:tournaments, on_delete: :delete_all), null: false
      add :user_id, references(:users, on_delete: :delete_all), null: false
      add :status, :string, null: false, default: "registered"
      add :wins, :integer, null: false, default: 0
      add :losses, :integer, null: false, default: 0
      add :draws, :integer, null: false, default: 0
      add :byes, :integer, null: false, default: 0
      add :pool, {:array, :map}, default: []
      add :load_list, {:array, :map}, default: []

      timestamps()
    end

    create unique_index(:tournament_players, [:tournament_id, :user_id])
    create index(:tournament_players, [:user_id])

    create table(:tournament_matches) do
      add :tournament_id, references(:tournaments, on_delete: :delete_all), null: false
      add :kind, :string, null: false, default: "match"
      add :round, :integer, null: false, default: 0
      add :status, :string, null: false, default: "pending"
      add :room_slug, :string
      add :player_ids, {:array, :integer}, null: false, default: []
      add :winner_id, :integer
      add :reported_by, :integer
      add :game_wins, :map, null: false, default: %{}

      timestamps()
    end

    create index(:tournament_matches, [:tournament_id])
    create index(:tournament_matches, [:room_slug])
  end
end
