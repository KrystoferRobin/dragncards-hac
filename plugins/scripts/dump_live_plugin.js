/**
 * Paste this into Brave DevTools → Console on an open DragnCards table
 * (the tab that finished loading, e.g. https://dragncards.com/room/...).
 *
 * It reads the gzip plugin already cached in IndexedDB (same payload the
 * table downloaded) and saves {pluginName}-live-dump.json.
 *
 * Then:
 *   python plugins/scripts/import_live_plugin.py ~/Downloads/*-live-dump.json
 *   python plugins/scripts/collect_hosted_images.py --allow-s3 <plugin-folder>
 */
(async () => {
  const inflateGzip = async (bytes) => {
    const ds = new DecompressionStream("gzip");
    const buf = await new Response(new Blob([bytes]).stream().pipeThrough(ds)).arrayBuffer();
    return JSON.parse(new TextDecoder().decode(buf));
  };

  const downloadJson = (obj, filename) => {
    const blob = new Blob([JSON.stringify(obj, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  };

  const db = await new Promise((resolve, reject) => {
    const req = indexedDB.open("dragncards", 1);
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error || new Error("indexedDB open failed"));
  });

  if (!db.objectStoreNames.contains("pluginData")) {
    console.error("No pluginData store. Wait until the table loading spinner finishes, then run again.");
    return;
  }

  const keys = await new Promise((resolve, reject) => {
    const q = db.transaction("pluginData").objectStore("pluginData").getAllKeys();
    q.onsuccess = () => resolve(q.result || []);
    q.onerror = () => reject(q.error);
  });

  if (!keys.length) {
    console.error("IndexedDB cache is empty. Leave this table tab open until cards render, then run again.");
    return;
  }

  const safe = (s) => String(s || "plugin").replace(/[^\w.-]+/g, "_").replace(/^_|_$/g, "") || "plugin";

  for (const key of keys) {
    const bytes = await new Promise((resolve, reject) => {
      const q = db.transaction("pluginData").objectStore("pluginData").get(key);
      q.onsuccess = () => resolve(q.result);
      q.onerror = () => reject(q.error);
    });
    if (!bytes) {
      console.warn("empty cache entry", key);
      continue;
    }
    const plugin = await inflateGzip(bytes);
    const name = plugin.game_def?.pluginName || plugin.name || `plugin-${key}`;
    const file = `${safe(name)}-live-dump.json`;
    downloadJson(plugin, file);
    console.log("saved", file, {
      id: plugin.id,
      name,
      version: plugin.version,
      cards: Object.keys(plugin.card_db || {}).length,
      gameDefKeys: Object.keys(plugin.game_def || {}),
      repo_url: plugin.repo_url || "",
    });
  }
})().catch((err) => console.error(err));
