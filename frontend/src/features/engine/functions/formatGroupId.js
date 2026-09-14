// Resolves layout groupIds:
//   playerN / playerN+X  — relative to the Look (observing) seat (existing)
//   playerS              — the seat you are sitting in
//   playerL              — the Look target; if you are looking at yourself
//                          (or not looking), this is the previous seat (N-1),
//                          wrapping to the last player for seat 1
export function offsetPlayerId(playerId, offset, numPlayers) {
  const n = numPlayers || 1;
  const index = parseInt(String(playerId || "").replace("player", ""), 10) - 1;
  if (Number.isNaN(index)) return playerId;
  return `player${(((index + offset) % n) + n) % n + 1}`;
}

export function lookedPlayerId(seatedPlayerN, observingPlayerN, numPlayers) {
  if (observingPlayerN && seatedPlayerN && observingPlayerN !== seatedPlayerN) {
    return observingPlayerN;
  }
  if (seatedPlayerN) return offsetPlayerId(seatedPlayerN, -1, numPlayers);
  if (observingPlayerN) return offsetPlayerId(observingPlayerN, -1, numPlayers);
  return "player1";
}

export function formatGroupId(groupId, observingPlayerN, numPlayers, seatedPlayerN) {
  if (!groupId || typeof groupId !== "string") return groupId;
  const seated = seatedPlayerN || observingPlayerN;
  const looked = lookedPlayerId(seated, observingPlayerN, numPlayers);
  const observeIndex = parseInt(String(observingPlayerN || seated || "player1").replace("player", ""), 10) - 1;
  const n = numPlayers || 1;

  const replaceOffset = (source, token) => source
    .replace(new RegExp(`\\{${token}([+-]\\d+)\\}`, "g"), (_, offset) => {
      const offsetInt = parseInt(offset, 10);
      return `player${(((observeIndex + offsetInt) % n) + n) % n + 1}`;
    })
    .replace(new RegExp(`${token}([+-]\\d+)`, "g"), (_, offset) => {
      const offsetInt = parseInt(offset, 10);
      return `player${(((observeIndex + offsetInt) % n) + n) % n + 1}`;
    });

  groupId = groupId.replace(/\{playerL\}/g, looked);
  groupId = groupId.replace(/playerL/g, looked);
  groupId = groupId.replace(/\{playerS\}/g, seated || "player1");
  groupId = groupId.replace(/playerS/g, seated || "player1");
  groupId = replaceOffset(groupId, "playerN");
  if (observingPlayerN) {
    groupId = groupId.replace(/\{playerN\}/g, observingPlayerN);
    groupId = groupId.replace(/playerN/g, observingPlayerN);
  }
  return groupId;
}
