import React, { useEffect, useMemo, useState } from "react";
import axios from "axios";
import { useSiteL10n } from "../../../../hooks/useSiteL10n";
import useProfile from "../../../../hooks/useProfile";
import { base64ToBytes, inflatePluginBytes } from "../../../../contexts/PluginContext";
import { gameDefToBuilderInputs } from "../builderPluginLoad";

const initialInputs = {
  backgroundUrl: "https://dragncards-core.s3.us-east-1.amazonaws.com/dragncards_logo_background.jpg",
  minPlayers: 2,
  maxPlayers: 2,
};

export const EditPlugin = ({ inputs, setInputs, onPluginLoaded, onCleared }) => {
  const siteL10n = useSiteL10n();
  const user = useProfile();
  const [plugins, setPlugins] = useState([]);
  const [selectedId, setSelectedId] = useState(inputs.sourcePlugin?.id ? String(inputs.sourcePlugin.id) : "");
  const [loadingList, setLoadingList] = useState(false);
  const [loadingPlugin, setLoadingPlugin] = useState(false);
  const [percentLoaded, setPercentLoaded] = useState(0);
  const [errorMessage, setErrorMessage] = useState("");

  const canEditPlugin = (plugin) =>
    !!user?.id && (user.admin || plugin.author_id === user.id);

  useEffect(() => {
    if (!user?.id) return;
    let cancelled = false;
    setLoadingList(true);
    axios
      .get(`/be/api/plugins/visible/${user.id}`)
      .then((res) => {
        if (cancelled) return;
        const list = (res.data?.data || []).filter(canEditPlugin);
        list.sort((a, b) => (a.name || "").localeCompare(b.name || ""));
        setPlugins(list);
      })
      .catch(() => {
        if (!cancelled) setErrorMessage(siteL10n("Could not load your plugins."));
      })
      .finally(() => {
        if (!cancelled) setLoadingList(false);
      });
    return () => {
      cancelled = true;
    };
  }, [user?.id, user?.admin]);

  const selectedPlugin = useMemo(
    () => plugins.find((plugin) => String(plugin.id) === String(selectedId)),
    [plugins, selectedId]
  );

  const loadSelected = async () => {
    if (!selectedId || !selectedPlugin) return;
    if (!canEditPlugin(selectedPlugin)) {
      setErrorMessage(siteL10n("You can only edit plugins you uploaded (or any plugin, if you are an admin)."));
      return;
    }
    setErrorMessage("");
    setLoadingPlugin(true);
    setPercentLoaded(0);
    try {
      const res = await axios.get(`/be/api/plugins/${selectedId}`, {
        onDownloadProgress: (event) => {
          if (event.total) setPercentLoaded(Math.round((event.loaded / event.total) * 100));
        },
      });
      const loaded = inflatePluginBytes(base64ToBytes(res.data));
      if (!loaded?.game_def) {
        setErrorMessage(siteL10n("Could not read that plugin."));
        return;
      }
      const next = gameDefToBuilderInputs({
        ...loaded,
        id: selectedPlugin?.id ?? loaded.id,
        version: selectedPlugin?.version ?? loaded.version,
        public: selectedPlugin?.public ?? loaded.public,
        name: selectedPlugin?.name || loaded.name,
        author_id: selectedPlugin?.author_id ?? loaded.author_id,
        repo_url: selectedPlugin?.repo_url || loaded.repo_url,
      });
      setInputs(next);
      onPluginLoaded?.();
    } catch (err) {
      setErrorMessage(err?.message || siteL10n("Could not load this plugin."));
    } finally {
      setLoadingPlugin(false);
    }
  };

  const startFresh = () => {
    setSelectedId("");
    setInputs({ ...initialInputs });
    setErrorMessage("");
    onCleared?.();
  };

  const cardCount = Object.keys(inputs.cardDb || {}).length;
  const loadedName = inputs.sourcePlugin?.name;

  return (
    <div className="max-w-3xl p-6 m-4 bg-gray-800 rounded-lg text-white">
      <p className="text-sm text-gray-300 mb-3">
        {siteL10n(
          "Optional. Load one of your plugins (or any plugin, if you are an admin) to edit its layout, groups, phases, tokens, and other settings. Card data stays as-is unless you upload a new TSV on the next tab."
        )}
      </p>
      <p className="text-sm text-gray-400 mb-4">
        {siteL10n(
          "Saving writes back to that plugin and keeps automation, hotkeys, and other JSON the builder does not show."
        )}
      </p>

      {!user?.id && (
        <p className="text-sm text-yellow-300 mb-3">{siteL10n("Log in to load a plugin you uploaded.")}</p>
      )}
      {loadingList && <p className="text-sm text-yellow-300 mb-3">{siteL10n("Loading plugin list…")}</p>}

      <label className="block text-sm text-gray-300 mb-2">
        {siteL10n("Plugin")}
        <select
          value={selectedId}
          onChange={(event) => setSelectedId(event.target.value)}
          className="mt-1 w-full bg-gray-900 text-white border border-gray-600 rounded px-2 py-2"
        >
          <option value="">{siteL10n("— Start a new plugin —")}</option>
          {plugins.map((plugin) => (
            <option key={plugin.id} value={plugin.id}>
              {plugin.name}
              {plugin.public ? "" : " (private)"}
              {user?.admin && plugin.author_id !== user.id ? ` — ${plugin.author_alias || plugin.author || "other"}` : ""}
            </option>
          ))}
        </select>
      </label>

      <div className="flex flex-wrap gap-3 mt-3">
        <button
          type="button"
          disabled={!selectedId || loadingPlugin}
          onClick={loadSelected}
          className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-40 text-white rounded text-sm"
        >
          {loadingPlugin
            ? `${siteL10n("Loading")} ${percentLoaded ? `${percentLoaded}%` : "…"}`
            : siteL10n("Load into builder")}
        </button>
        {inputs.sourcePlugin && (
          <button
            type="button"
            onClick={startFresh}
            className="px-4 py-2 bg-gray-600 hover:bg-gray-500 text-white rounded text-sm"
          >
            {siteL10n("Clear and start new")}
          </button>
        )}
      </div>

      {errorMessage && <p className="text-red-400 text-sm mt-3">{errorMessage}</p>}

      {loadedName && (
        <div className="mt-4 text-sm text-green-300">
          {siteL10n("Loaded")} <span className="font-semibold">{loadedName}</span>
          {cardCount ? ` — ${cardCount.toLocaleString()} ${siteL10n("cards")}` : ""}.
          {" "}
          {siteL10n("The other tabs now show this plugin’s data.")}
        </div>
      )}
    </div>
  );
};
