defmodule DragnCardsGame.Limited do
  @moduledoc """
  Sealed / draft / sealed-draft session on a room.

  Pack generation is server-side. Picks are bound to the socket's seated user
  in GameUIServer, not to a client-supplied $PLAYER_N.
  """

  alias DragnCardsGame.{Evaluate, GameUI, PluginCache}

  @modes ["sealed", "draft", "sealed_draft"]
  @card_pool_suffix "CardPool"

  def card_pool_group(player_n), do: "#{player_n}#{@card_pool_suffix}"

  def init_game(game, options) do
    cfg = options["limited"]

    if is_map(cfg) and cfg["mode"] in @modes do
      Map.put(game, "limited", waiting_state(cfg))
    else
      game
    end
  end

  def waiting_state(cfg) when is_map(cfg) do
    %{
      "sessionId" => Ecto.UUID.generate(),
      "tournamentId" => cfg["tournamentId"],
      "mode" => cfg["mode"],
      "status" => "waiting",
      "config" => stringify_cfg(cfg),
      "passSign" => 1,
      "packIndex" => 0,
      "pickIndex" => 0,
      "waitingOn" => [],
      "committed" => [],
      "public" => %{"whoHasPicked" => []},
      "private" => %{}
    }
  end

  def start(gameui, user_id) do
    game = gameui["game"]
    limited = game["limited"]

    cond do
      not is_map(limited) ->
        {:error, "This room is not a limited session."}

      limited["status"] != "waiting" ->
        {:error, "Limited play has already started."}

      gameui["createdBy"] != user_id ->
        {:error, "Only the host can start limited play."}

      true ->
        seats = seated_players(gameui, game["numPlayers"] || 0)

        # Pod is whoever is seated. Empty seats are skipped so a host can
        # solo-test pick/build; a later 8-player table still waits on people
        # actually sitting, not on the layout's max.
        if length(seats) < 1 do
          {:error, "Sit down before starting."}
        else
          do_start(gameui, seats)
        end
    end
  end

  def pick(gameui, user_id, database_id) do
    game = gameui["game"]
    limited = game["limited"]
    player_n = GameUI.get_player_n_by_user_id(gameui, user_id)

    cond do
      not is_map(limited) or limited["status"] != "drafting" ->
        {:error, "No draft pick is open."}

      player_n == nil ->
        {:error, "Sit down to pick."}

      player_n not in (limited["waitingOn"] || []) ->
        {:error, "It is not your pick, or you already picked."}

      true ->
        pack = get_in(limited, ["private", player_n, "currentPack"]) || []

        if database_id not in pack do
          {:error, "That card is not in your current pack."}
        else
          seats = limited["seats"] || seated_players(gameui, game["numPlayers"])
          {:ok, put_in(gameui["game"], apply_pick(game, player_n, database_id, seats))}
        end
    end
  end

  def commit_deck(gameui, user_id, load_list) when is_list(load_list) do
    game = gameui["game"]
    limited = game["limited"]
    player_n = GameUI.get_player_n_by_user_id(gameui, user_id)

    cond do
      not is_map(limited) or limited["status"] != "building" ->
        {:error, "Deck building is not open."}

      player_n == nil ->
        {:error, "Sit down to commit a deck."}

      player_n in (limited["committed"] || []) ->
        {:error, "You already committed a deck."}

      true ->
        pool = get_in(limited, ["private", player_n, "pool"]) || []

        case validate_commit(pool, load_list) do
          {:error, reason} ->
            {:error, reason}

          :ok ->
            seats = limited["seats"] || seated_players(gameui, game["numPlayers"])
            game = inject_card_pool_groups(game, seats)
            game = put_in(game["playerInfo"], gameui["playerInfo"])
            game = put_in(game["variables"]["$PLAYER_N"], player_n)

            items =
              Enum.map(load_list, fn item ->
                %{
                  "databaseId" => item["databaseId"] || item[:databaseId],
                  "quantity" => item["quantity"] || item[:quantity] || 1,
                  "loadGroupId" => item["loadGroupId"] || item[:loadGroupId]
                }
              end)

            game = Evaluate.evaluate(game, ["LOAD_CARDS", ["LIST"] ++ items], ["limited_commit"])

            committed = (limited["committed"] || []) ++ [player_n]
            limited = put_in(limited["committed"], Enum.uniq(committed))
            limited = put_in(limited, ["private", player_n, "committedLoadList"], items)

            limited =
              if Enum.sort(limited["committed"]) == Enum.sort(seats) do
                put_in(limited["status"], "playing")
              else
                limited
              end

            game = put_in(game["limited"], limited)
            {:ok, put_in(gameui["game"], game)}
        end
    end
  end

  def commit_deck(_gameui, _user_id, _), do: {:error, "load_list must be a list."}

  def generate_pack(card_db, limited_def, product) when is_map(product) do
    kind = product["kind"] || "booster"

    case kind do
      "starter" ->
        generate_starter(card_db, limited_def, product)

      _ ->
        set = product["set"]
        spread = product["spread"] || set_spread(limited_def, set)
        fill_spread(card_db, limited_def, spread, set)
    end
  end

  def generate_pack(_, _, _), do: []

  def normalize_rarity(limited_def, value) do
    raw = value |> to_string() |> String.trim()
    mapped = get_in(limited_def || %{}, ["rarityNormalize", raw])

    cond do
      is_binary(mapped) and mapped != "" ->
        mapped

      true ->
        class =
          case Regex.run(~r/^(.+?)(?:-\d+)?$/, raw) do
            [_, name] -> String.trim(name)
            _ -> raw
          end

        case String.downcase(class) do
          "common" -> "C"
          "uncommon" -> "U"
          "rare" -> "R"
          "mythic" -> "M"
          "mythic rare" -> "M"
          other ->
            mapped2 = get_in(limited_def || %{}, ["rarityNormalize", class])
            if is_binary(mapped2) and mapped2 != "", do: mapped2, else: other
        end
    end
  end

  def rotate_packs(private, seats, pass_sign) when is_list(seats) and seats != [] do
    n = length(seats)
    packs = Enum.map(seats, fn s -> get_in(private, [s, "currentPack"]) || [] end)

    shifted =
      Enum.map(0..(n - 1), fn i ->
        src = if pass_sign >= 0, do: rem(i - 1 + n, n), else: rem(i + 1, n)
        Enum.at(packs, src)
      end)

    Enum.zip(seats, shifted)
    |> Enum.reduce(private, fn {seat, pack}, acc ->
      put_in(acc, [seat, "currentPack"], pack)
    end)
  end

  def rotate_packs(private, _, _), do: private

  def add_to_pool(pool, database_id, quantity, source) when quantity > 0 do
    qty = trunc(quantity)
    idx = Enum.find_index(pool, fn item -> item["databaseId"] == database_id end)

    if idx do
      List.update_at(pool, idx, fn item ->
        Map.update(item, "quantity", qty, &(&1 + qty))
      end)
    else
      pool ++ [%{"databaseId" => database_id, "quantity" => qty, "source" => source}]
    end
  end

  def add_to_pool(pool, _, _, _), do: pool

  def validate_commit(pool, load_list) do
    pool_counts =
      Enum.reduce(pool, %{}, fn item, acc ->
        id = item["databaseId"]
        Map.update(acc, id, item["quantity"] || 0, &(&1 + (item["quantity"] || 0)))
      end)

    used =
      Enum.reduce(load_list, %{}, fn item, acc ->
        id = item["databaseId"] || item[:databaseId]
        qty = item["quantity"] || item[:quantity] || 0
        Map.update(acc, id, qty, &(&1 + qty))
      end)

    extra =
      Enum.find(used, fn {id, qty} ->
        qty > (pool_counts[id] || 0)
      end)

    missing =
      Enum.find(pool_counts, fn {id, qty} ->
        (used[id] || 0) != qty
      end)

    cond do
      extra ->
        {:error, "That deck uses more copies than your limited pool."}

      missing ->
        {:error, "Every pooled card must stay in a pile (use Card Pool for leftovers)."}

      true ->
        :ok
    end
  end

  def seated_players(gameui, num_players) do
    n = num_players || 0

    1..max(n, 0)
    |> Enum.map(&"player#{&1}")
    |> Enum.filter(fn seat ->
      id = get_in(gameui, ["playerInfo", seat, "id"])
      is_integer(id)
    end)
  end

  defp do_start(gameui, seats) do
    game = gameui["game"]
    limited = game["limited"]
    mode = limited["mode"]
    cfg = limited["config"] || %{}
    plugin_id = game["pluginId"]
    game_def = PluginCache.get_game_def_cached(plugin_id)
    card_db = PluginCache.get_card_db_cached(plugin_id)
    limited_def = game_def["limited"] || %{}

    private =
      Enum.reduce(seats, %{}, fn seat, acc ->
        Map.put(acc, seat, %{
          "unopened" => [],
          "currentPack" => [],
          "pool" => [],
          "committedLoadList" => nil
        })
      end)

    {private, status} =
      case mode do
        "sealed" ->
          {award_sealed(private, seats, cfg, card_db, game_def, limited_def), "building"}

        "draft" ->
          private = deal_draft_packs(private, seats, cfg, card_db, limited_def)
          {open_first_packs(private, seats), "drafting"}

        "sealed_draft" ->
          private = award_sealed(private, seats, cfg, card_db, game_def, limited_def)
          private = deal_draft_packs(private, seats, cfg, card_db, limited_def)
          {open_first_packs(private, seats), "drafting"}
      end

    pass_dir = cfg["passDirection"] || limited_def["passDirection"] || "clockwise"

    limited =
      limited
      |> Map.put("private", private)
      |> Map.put("status", status)
      |> Map.put("passSign", 1)
      |> Map.put("passDirection", pass_dir)
      |> Map.put("packIndex", 0)
      |> Map.put("pickIndex", 0)
      |> Map.put("seats", seats)
      |> Map.put("waitingOn", if(status == "drafting", do: seats, else: []))
      |> Map.put("committed", [])
      |> put_in(["public", "whoHasPicked"], [])

    game = inject_card_pool_groups(game, seats)
    game = put_in(game["limited"], limited)
    {:ok, put_in(gameui["game"], game)}
  end

  defp apply_pick(game, player_n, database_id, seats) do
    limited = game["limited"]
    pack = get_in(limited, ["private", player_n, "currentPack"]) || []
    {_, rest} = List.pop_at(pack, Enum.find_index(pack, &(&1 == database_id)))
    pool = get_in(limited, ["private", player_n, "pool"]) || []

    limited = put_in(limited, ["private", player_n, "currentPack"], rest)
    limited = put_in(limited, ["private", player_n, "pool"], add_to_pool(pool, database_id, 1, "draft"))

    who = (get_in(limited, ["public", "whoHasPicked"]) || []) ++ [player_n]
    waiting = Enum.reject(limited["waitingOn"] || [], &(&1 == player_n))
    limited = put_in(limited["waitingOn"], waiting)
    limited = put_in(limited, ["public", "whoHasPicked"], Enum.uniq(who))

    limited =
      if waiting == [] do
        after_all_picked(limited, seats)
      else
        limited
      end

    put_in(game["limited"], limited)
  end

  defp after_all_picked(limited, seats) do
    pass_sign = limited["passSign"] || 1
    private = rotate_packs(limited["private"], seats, pass_sign)
    limited = put_in(limited["private"], private)
    limited = Map.update(limited, "pickIndex", 1, &(&1 + 1))

    if Enum.all?(seats, fn s -> (get_in(private, [s, "currentPack"]) || []) == [] end) do
      deal_or_finish(limited, seats)
    else
      limited
      |> Map.put("waitingOn", seats)
      |> put_in(["public", "whoHasPicked"], [])
    end
  end

  defp deal_or_finish(limited, seats) do
    private = limited["private"]

    still_unopened? =
      Enum.any?(seats, fn s -> length(get_in(private, [s, "unopened"]) || []) > 0 end)

    if still_unopened? do
      private = open_next_packs(private, seats)
      pass_dir = limited["passDirection"] || "clockwise"
      pack_index = (limited["packIndex"] || 0) + 1
      pass_sign = limited["passSign"] || 1

      pass_sign =
        if pass_dir == "alternate", do: pass_sign * -1, else: pass_sign

      limited
      |> Map.put("private", private)
      |> Map.put("packIndex", pack_index)
      |> Map.put("passSign", pass_sign)
      |> Map.put("pickIndex", 0)
      |> Map.put("waitingOn", seats)
      |> put_in(["public", "whoHasPicked"], [])
    else
      limited
      |> Map.put("status", "building")
      |> Map.put("waitingOn", [])
      |> put_in(["public", "whoHasPicked"], [])
    end
  end

  defp open_first_packs(private, seats), do: open_next_packs(private, seats)

  defp open_next_packs(private, seats) do
    Enum.reduce(seats, private, fn seat, acc ->
      unopened = get_in(acc, [seat, "unopened"]) || []

      case unopened do
        [pack | rest] ->
          acc
          |> put_in([seat, "currentPack"], pack)
          |> put_in([seat, "unopened"], rest)

        [] ->
          put_in(acc, [seat, "currentPack"], [])
      end
    end)
  end

  defp deal_draft_packs(private, seats, cfg, card_db, limited_def) do
    recipes = cfg["draftProducts"] || cfg["draftBoosters"] || []

    Enum.reduce(seats, private, fn seat, acc ->
      packs =
        Enum.flat_map(recipes, fn recipe ->
          product_id = recipe["productId"] || recipe["id"]
          count = recipe["count"] || 1
          product = get_in(limited_def, ["products", product_id]) || %{}

          Enum.map(1..max(count, 0), fn _ ->
            generate_pack(card_db, limited_def, product)
          end)
        end)

      put_in(acc, [seat, "unopened"], packs)
    end)
  end

  defp award_sealed(private, seats, cfg, card_db, game_def, limited_def) do
    products = cfg["sealedProducts"] || []

    Enum.reduce(seats, private, fn seat, acc ->
      pool =
        Enum.reduce(products, get_in(acc, [seat, "pool"]) || [], fn product, pool_acc ->
          award_one(pool_acc, product, card_db, game_def, limited_def)
        end)

      put_in(acc, [seat, "pool"], pool)
    end)
  end

  defp award_one(pool, %{"kind" => "prebuilt", "id" => deck_id}, _card_db, game_def, _limited_def) do
    cards = get_in(game_def, ["preBuiltDecks", deck_id, "cards"]) || []

    Enum.reduce(cards, pool, fn card, acc ->
      add_to_pool(acc, card["databaseId"], card["quantity"] || 1, "sealed")
    end)
  end

  defp award_one(pool, %{"kind" => "deck", "load_list" => list}, _card_db, _game_def, _limited_def)
       when is_list(list) do
    Enum.reduce(list, pool, fn card, acc ->
      add_to_pool(acc, card["databaseId"], card["quantity"] || 1, "sealed")
    end)
  end

  defp award_one(pool, product, card_db, _game_def, limited_def) do
    product_id = product["productId"] || product["id"]
    count = product["count"] || 1
    recipe = get_in(limited_def, ["products", product_id]) || product

    Enum.reduce(1..max(count, 0), pool, fn _, acc ->
      generate_pack(card_db, limited_def, recipe)
      |> Enum.reduce(acc, fn id, inner -> add_to_pool(inner, id, 1, "sealed") end)
    end)
  end

  defp generate_starter(card_db, limited_def, product) do
    Enum.flat_map(product["slots"] || [], fn slot ->
      if slot["from"] == "fixed" do
        Enum.flat_map(slot["cards"] || [], fn card ->
          List.duplicate(card["databaseId"], card["quantity"] || 1)
        end)
      else
        set = slot["set"] || product["set"]
        fill_spread(card_db, limited_def, %{"slots" => [Map.delete(slot, "from")]}, set)
      end
    end)
  end

  defp set_spread(limited_def, set) do
    get_in(limited_def, ["setSpreads", set]) || limited_def["defaultSpread"] || %{"slots" => []}
  end

  defp fill_spread(card_db, limited_def, spread, set) do
    bins = rarity_bins(card_db, limited_def, set)

    {ids, _} =
      Enum.reduce(spread["slots"] || [], {[], bins}, fn slot, {acc, remaining} ->
        count = slot["count"] || 0
        rarities = slot["rarities"] || []

        Enum.reduce(1..max(count, 0), {acc, remaining}, fn _, {acc2, rem} ->
          case take_from_bins(rem, rarities) do
            {id, rem2} -> {acc2 ++ [id], rem2}
            :empty -> {acc2, rem}
          end
        end)
      end)

    ids
  end

  defp rarity_bins(card_db, limited_def, set) do
    set_prop = limited_def["setProperty"] || "set"
    rarity_prop = limited_def["rarityProperty"] || "rarity"

    card_db
    |> Enum.reduce(%{}, fn {id, card}, acc ->
      face = card["A"] || %{}
      card_set = face[set_prop]

        if is_nil(set) or card_set == set do
        code = normalize_rarity(limited_def, face[rarity_prop])
        Map.update(acc, code, [id], &[id | &1])
      else
        acc
      end
    end)
    |> Enum.map(fn {k, ids} -> {k, Enum.shuffle(ids)} end)
    |> Map.new()
  end

  defp take_from_bins(bins, rarities) do
    Enum.find_value(rarities, fn code ->
      case bins[code] do
        [id | rest] -> {id, Map.put(bins, code, rest)}
        _ -> nil
      end
    end)
    |> case do
      nil -> :empty
      pair -> pair
    end
  end

  defp inject_card_pool_groups(game, seats) do
    Enum.reduce(seats, game, fn seat, acc ->
      gid = card_pool_group(seat)

      if get_in(acc, ["groupById", gid]) do
        acc
      else
        group = %{
          "id" => gid,
          "stackIds" => [],
          "groupType" => "deck",
          "label" => "Card Pool",
          "tableLabel" => "Card Pool",
          "shuffleOnLoad" => false,
          "canHaveAttachments" => false,
          "canHaveTokens" => false,
          "controller" => seat,
          "onCardEnter" => %{
            "currentSide" => "B",
            "inPlay" => false,
            "rotation" => 0,
            "controller" => seat
          }
        }

        put_in(acc, ["groupById", gid], group)
      end
    end)
  end

  defp stringify_cfg(cfg) do
    %{
      "mode" => cfg["mode"],
      "passDirection" => cfg["passDirection"],
      "numPlayers" => cfg["numPlayers"],
      "draftProducts" => cfg["draftProducts"] || cfg["draftBoosters"] || [],
      "sealedProducts" => cfg["sealedProducts"] || [],
      "tournamentId" => cfg["tournamentId"]
    }
  end
end
