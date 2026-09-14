import { useEffect, useState } from "react";
import axios from "axios";
import { base64ToBytes, inflatePluginBytes } from "../../contexts/PluginContext";
import { readPluginCache, writePluginCache } from "../../contexts/pluginCache";

export const useLoadPluginPayload = (pluginId) => {
  const [plugin, setPlugin] = useState(null);
  const [percentLoaded, setPercentLoaded] = useState(0);
  const [error, setError] = useState(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    if (!pluginId) {
      setIsLoading(false);
      setError("Missing plugin.");
      return;
    }
    let cancelled = false;
    setIsLoading(true);
    setError(null);
    setPlugin(null);

    (async () => {
      try {
        const cached = await readPluginCache(pluginId);
        if (cancelled) return;
        if (cached) {
          const cachedPlugin = inflatePluginBytes(cached);
          if (cachedPlugin?.game_def) {
            setPlugin(cachedPlugin);
            setIsLoading(false);
            return;
          }
        }
        const res = await axios.get(`/be/api/plugins/${pluginId}`, {
          onDownloadProgress: (event) => {
            if (event.total) setPercentLoaded(Math.round((event.loaded / event.total) * 100));
          },
        });
        if (cancelled) return;
        const bytes = base64ToBytes(res.data);
        const loaded = bytes ? inflatePluginBytes(bytes) : null;
        if (!loaded?.game_def) {
          setError("Could not load this plugin.");
          setIsLoading(false);
          return;
        }
        setPlugin(loaded);
        if (bytes) writePluginCache(pluginId, bytes);
        setIsLoading(false);
      } catch (err) {
        if (!cancelled) {
          setError(err?.message || "Could not load this plugin.");
          setIsLoading(false);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [pluginId]);

  return { plugin, isLoading, percentLoaded, error };
};
