defmodule DragnCards.Repo.Migrations.AddLimitedFieldsToDecks do
  use Ecto.Migration

  def change do
    alter table(:decks) do
      add :formats, {:array, :string}, default: []
      add :limited_session_id, :string
    end
  end
end
