defmodule DragnCards.Tournaments.Pairing do
  @moduledoc """
  Pure pairing helpers. A table reports one winner; everyone else records a loss.
  """

  def eligible(players, structure) when is_list(players) do
    players
    |> Enum.filter(&(&1.status == "active"))
    |> Enum.filter(fn p ->
      case structure do
        "single_elim" -> p.losses < 1
        "two_loss_out" -> p.losses < 2
        "double_elim" -> p.losses < 2
        _ -> true
      end
    end)
  end

  def finished?(eligible) when length(eligible) <= 1, do: true
  def finished?(_), do: false

  @doc """
  Split shuffled ids into tables of `match_size`. A leftover of 1 gets a bye.
  A leftover of 2+ becomes one undersized table so a 3-player Commander field
  still sits when the plugin's usual table is 4.
  """
  def tables(player_ids, match_size) when is_list(player_ids) and match_size >= 2 do
    ids = Enum.shuffle(player_ids)
    {full, rest} = take_full(ids, match_size, [])

    cond do
      length(rest) >= 2 -> {Enum.reverse(full) ++ [rest], []}
      true -> {Enum.reverse(full), rest}
    end
  end

  def out_losses("single_elim"), do: 1
  def out_losses(_), do: 2

  defp take_full(ids, n, acc) when length(ids) < n, do: {acc, ids}
  defp take_full(ids, n, acc) do
    {chunk, rest} = Enum.split(ids, n)
    take_full(rest, n, [chunk | acc])
  end
end
