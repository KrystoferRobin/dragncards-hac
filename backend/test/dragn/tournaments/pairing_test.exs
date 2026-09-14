defmodule DragnCards.Tournaments.PairingTest do
  use ExUnit.Case, async: true

  alias DragnCards.Tournaments.Pairing

  defp p(id, losses, status \\ "active") do
    %{user_id: id, losses: losses, status: status, wins: 0}
  end

  test "two-loss-out drops anyone with two losses" do
    players = [p(1, 0), p(2, 1), p(3, 2), p(4, 0, "kicked")]
    ids = Pairing.eligible(players, "two_loss_out") |> Enum.map(& &1.user_id)
    assert Enum.sort(ids) == [1, 2]
  end

  test "single elim drops after one loss" do
    players = [p(1, 0), p(2, 1)]
    ids = Pairing.eligible(players, "single_elim") |> Enum.map(& &1.user_id)
    assert ids == [1]
  end

  test "one eligible player is finished" do
    assert Pairing.finished?([p(1, 0)])
    refute Pairing.finished?([p(1, 0), p(2, 0)])
  end

  test "tables of 2 leave a single leftover as a bye" do
    {tables, byes} = Pairing.tables([1, 2, 3], 2)
    assert length(tables) == 1
    assert length(hd(tables)) == 2
    assert length(byes) == 1
  end

  test "leftover of 2+ becomes an undersized table" do
    {tables, byes} = Pairing.tables([1, 2, 3, 4, 5, 6], 4)
    assert byes == []
    sizes = tables |> Enum.map(&length/1) |> Enum.sort()
    assert sizes == [2, 4]
  end
end
