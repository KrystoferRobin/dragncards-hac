defmodule DragnCardsGame.LimitedTest do
  use ExUnit.Case, async: true

  alias DragnCardsGame.Limited

  defp face(set, rarity) do
    %{"A" => %{"set" => set, "rarity" => rarity, "name" => rarity}}
  end

  defp kingdom_db do
    commons = for i <- 1..12, into: %{}, do: {"c#{i}", face("02Kingdom", "Common-3")}
    uncommons = for i <- 1..6, into: %{}, do: {"u#{i}", face("02Kingdom", "Uncommon-2")}
    rares = for i <- 1..4, into: %{}, do: {"r#{i}", face("02Kingdom", "Rare-1")}
    phoenix = %{"p1" => face("03Phoenix", "Common")}
    Map.merge(commons, uncommons) |> Map.merge(rares) |> Map.merge(phoenix)
  end

  defp wyvern_def do
    %{
      "setProperty" => "set",
      "rarityProperty" => "rarity",
      "rarityNormalize" => %{"Common" => "C", "Uncommon" => "U", "Rare" => "R"},
      "defaultSpread" => %{
        "slots" => [
          %{"count" => 8, "rarities" => ["C"]},
          %{"count" => 3, "rarities" => ["U", "C"]},
          %{"count" => 1, "rarities" => ["R", "U", "C"]}
        ]
      },
      "products" => %{
        "kingdom-booster" => %{"kind" => "booster", "set" => "02Kingdom", "label" => "Kingdom"},
        "kingdom-starter" => %{
          "kind" => "starter",
          "label" => "Starter",
          "slots" => [
            %{"count" => 3, "rarities" => ["C"], "set" => "02Kingdom"},
            %{"from" => "fixed", "cards" => [%{"databaseId" => "c1", "quantity" => 2}]}
          ]
        }
      }
    }
  end

  test "normalize_rarity strips Lackey sheet suffixes and named values" do
    defn = wyvern_def()
    assert Limited.normalize_rarity(defn, "Common-3") == "C"
    assert Limited.normalize_rarity(defn, "Uncommon-2") == "U"
    assert Limited.normalize_rarity(defn, "Rare-1") == "R"
    assert Limited.normalize_rarity(defn, "Common") == "C"
  end

  test "Kingdom booster fills 8C 3U 1R without replacement" do
    :rand.seed(:exsss, {1, 2, 3})
    pack = Limited.generate_pack(kingdom_db(), wyvern_def(), %{"kind" => "booster", "set" => "02Kingdom"})
    assert length(pack) == 12
    assert length(Enum.uniq(pack)) == 12
    assert Enum.all?(pack, fn id -> String.starts_with?(id, ["c", "u", "r"]) end)
    refute Enum.any?(pack, &(&1 == "p1"))
  end

  test "empty rare bin falls through to uncommon then common" do
    db = for i <- 1..10, into: %{}, do: {"c#{i}", face("S", "Common")}
    defn = %{
      "setProperty" => "set",
      "rarityProperty" => "rarity",
      "defaultSpread" => %{"slots" => [%{"count" => 2, "rarities" => ["R", "U", "C"]}]}
    }

    pack = Limited.generate_pack(db, defn, %{"kind" => "booster", "set" => "S"})
    assert length(pack) == 2
    assert Enum.all?(pack, &String.starts_with?(&1, "c"))
  end

  test "starter mixes random slots and a fixed card list" do
    :rand.seed(:exsss, {4, 5, 6})
    pack = Limited.generate_pack(kingdom_db(), wyvern_def(), wyvern_def()["products"]["kingdom-starter"])
    assert Enum.count(pack, &(&1 == "c1")) >= 2
    assert length(pack) == 5
  end

  test "a solo drafter keeps the pack and can finish it alone" do
    gameui = %{
      "createdBy" => 1,
      "playerInfo" => %{"player1" => %{"id" => 1}},
      "game" => %{
        "numPlayers" => 2,
        "limited" => %{
          "status" => "drafting",
          "waitingOn" => ["player1"],
          "passSign" => 1,
          "passDirection" => "clockwise",
          "packIndex" => 0,
          "pickIndex" => 0,
          "public" => %{"whoHasPicked" => []},
          "private" => %{
            "player1" => %{"currentPack" => ["a", "b"], "unopened" => [], "pool" => []}
          }
        }
      }
    }

    {:ok, after_first} = Limited.pick(gameui, 1, "a")
    assert after_first["game"]["limited"]["status"] == "drafting"
    assert after_first["game"]["limited"]["private"]["player1"]["currentPack"] == ["b"]
    assert after_first["game"]["limited"]["waitingOn"] == ["player1"]

    {:ok, done} = Limited.pick(after_first, 1, "b")
    assert done["game"]["limited"]["status"] == "building"
    pool_ids = Enum.map(done["game"]["limited"]["private"]["player1"]["pool"], & &1["databaseId"])
    assert pool_ids == ["a", "b"]
  end

  test "clockwise pass sends player1 remaining pack to player2" do
    private = %{
      "player1" => %{"currentPack" => ["a", "b"]},
      "player2" => %{"currentPack" => ["c", "d"]},
      "player3" => %{"currentPack" => ["e"]}
    }

    rotated = Limited.rotate_packs(private, ["player1", "player2", "player3"], 1)
    assert rotated["player1"]["currentPack"] == ["e"]
    assert rotated["player2"]["currentPack"] == ["a", "b"]
    assert rotated["player3"]["currentPack"] == ["c", "d"]
  end

  test "alternate / reverse pass sends player1 pack to last seat" do
    private = %{
      "player1" => %{"currentPack" => ["a"]},
      "player2" => %{"currentPack" => ["b"]}
    }

    rotated = Limited.rotate_packs(private, ["player1", "player2"], -1)
    assert rotated["player1"]["currentPack"] == ["b"]
    assert rotated["player2"]["currentPack"] == ["a"]
  end

  test "picks wait for every seat then rotate" do
    gameui = %{
      "createdBy" => 1,
      "playerInfo" => %{
        "player1" => %{"id" => 1},
        "player2" => %{"id" => 2}
      },
      "game" => %{
        "numPlayers" => 2,
        "limited" => %{
          "status" => "drafting",
          "waitingOn" => ["player1", "player2"],
          "passSign" => 1,
          "passDirection" => "clockwise",
          "packIndex" => 0,
          "pickIndex" => 0,
          "public" => %{"whoHasPicked" => []},
          "private" => %{
            "player1" => %{"currentPack" => ["a", "b"], "unopened" => [], "pool" => []},
            "player2" => %{"currentPack" => ["c", "d"], "unopened" => [], "pool" => []}
          }
        }
      }
    }

    {:ok, after_p1} = Limited.pick(gameui, 1, "a")
    assert after_p1["game"]["limited"]["waitingOn"] == ["player2"]
    assert hd(get_in(after_p1, ["game", "limited", "private", "player1", "pool"]))["databaseId"] == "a"

    {:ok, after_p2} = Limited.pick(after_p1, 2, "c")
    limited = after_p2["game"]["limited"]
    assert limited["waitingOn"] == ["player1", "player2"]
    assert limited["private"]["player1"]["currentPack"] == ["d"]
    assert limited["private"]["player2"]["currentPack"] == ["b"]
  end

  test "last cards in a pack with no unopened packs move status to building" do
    gameui = %{
      "createdBy" => 1,
      "playerInfo" => %{"player1" => %{"id" => 1}, "player2" => %{"id" => 2}},
      "game" => %{
        "numPlayers" => 2,
        "limited" => %{
          "status" => "drafting",
          "waitingOn" => ["player1", "player2"],
          "passSign" => 1,
          "passDirection" => "clockwise",
          "packIndex" => 0,
          "pickIndex" => 0,
          "public" => %{"whoHasPicked" => []},
          "private" => %{
            "player1" => %{"currentPack" => ["a"], "unopened" => [], "pool" => []},
            "player2" => %{"currentPack" => ["b"], "unopened" => [], "pool" => []}
          }
        }
      }
    }

    {:ok, after_p1} = Limited.pick(gameui, 1, "a")
    {:ok, done} = Limited.pick(after_p1, 2, "b")
    assert done["game"]["limited"]["status"] == "building"
  end

  test "validate_commit requires the full pool and no extras" do
    pool = [%{"databaseId" => "a", "quantity" => 2, "source" => "draft"}]
    ok_list = [
      %{"databaseId" => "a", "quantity" => 1, "loadGroupId" => "playerNDeck"},
      %{"databaseId" => "a", "quantity" => 1, "loadGroupId" => "playerNCardPool"}
    ]
    assert Limited.validate_commit(pool, ok_list) == :ok
    assert {:error, _} = Limited.validate_commit(pool, [%{"databaseId" => "a", "quantity" => 3, "loadGroupId" => "playerNDeck"}])
    assert {:error, _} = Limited.validate_commit(pool, [%{"databaseId" => "a", "quantity" => 1, "loadGroupId" => "playerNDeck"}])
  end

  test "a seated player cannot pick another seat's card by spoofing" do
    gameui = %{
      "playerInfo" => %{"player1" => %{"id" => 1}, "player2" => %{"id" => 2}},
      "game" => %{
        "numPlayers" => 2,
        "limited" => %{
          "status" => "drafting",
          "waitingOn" => ["player1", "player2"],
          "private" => %{
            "player1" => %{"currentPack" => ["mine"], "pool" => []},
            "player2" => %{"currentPack" => ["theirs"], "pool" => []}
          },
          "public" => %{"whoHasPicked" => []}
        }
      }
    }

    assert {:error, _} = Limited.pick(gameui, 1, "theirs")
    assert {:ok, _} = Limited.pick(gameui, 1, "mine")
  end
end
