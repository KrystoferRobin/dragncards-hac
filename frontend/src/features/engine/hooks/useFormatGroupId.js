import { useSelector } from "react-redux";
import { formatGroupId } from "../functions/formatGroupId";

export const useFormatGroupId = () => {
    const observingPlayerN = useSelector(state => state?.playerUi?.observingPlayerN);
    const seatedPlayerN = useSelector(state => state?.playerUi?.playerN);
    const numPlayers = useSelector(state => state?.gameUi?.game?.numPlayers);
    return (groupId) => formatGroupId(groupId, observingPlayerN, numPlayers, seatedPlayerN);
}
