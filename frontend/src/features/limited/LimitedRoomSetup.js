import React, { useEffect, useState } from "react";
import axios from "axios";
import useProfile from "../../hooks/useProfile";

const MODES = [
  { value: "constructed", label: "Constructed" },
  { value: "sealed", label: "Sealed" },
  { value: "draft", label: "Draft" },
  { value: "sealed_draft", label: "Sealed draft" },
];

const cloneDefaults = (limited, mode) => {
  const defaults = limited?.defaults || {};
  if (mode === "draft") {
    return {
      draftProducts: (defaults.draftBoosters || []).map((row) => ({ ...row })),
      sealedProducts: [],
    };
  }
  if (mode === "sealed") {
    return {
      draftProducts: [],
      sealedProducts: (defaults.sealedProducts || []).map((row) => ({ ...row })),
    };
  }
  if (mode === "sealed_draft") {
    return {
      draftProducts: (defaults.sealedDraftBoosters || defaults.draftBoosters || []).map((row) => ({ ...row })),
      sealedProducts: (defaults.sealedProducts || []).map((row) => ({ ...row })),
    };
  }
  return { draftProducts: [], sealedProducts: [] };
};

export const LimitedRoomSetup = ({ plugin, value, onChange }) => {
  const limited = plugin?.limited;
  const user = useProfile();
  const [publicDecks, setPublicDecks] = useState([]);

  useEffect(() => {
    if (!plugin?.id || !limited) return;
    axios.get(`/be/api/v1/public_decks/${plugin.id}`).then((res) => {
      setPublicDecks((res.data?.public_decks || []).filter((d) => (d.formats || []).includes("sealed")));
    }).catch(() => setPublicDecks([]));
  }, [plugin?.id, limited]);

  const boosterProducts = limited?.products || [];
  const sealedDecks = [
    ...(limited?.sealedDecks || []),
    ...publicDecks.map((d) => ({
      id: `deck:${d.id}`,
      label: `${d.name} (public)`,
      kind: "deck",
      load_list: d.load_list,
    })),
  ];

  if (!limited) return null;

  const mode = value?.mode || "constructed";

  const setMode = (nextMode) => {
    if (nextMode === "constructed") {
      onChange(null);
      return;
    }
    onChange({
      mode: nextMode,
      passDirection: limited.passDirection || "clockwise",
      ...cloneDefaults(limited, nextMode),
    });
  };

  const updateDraft = (index, patch) => {
    const draftProducts = [...(value.draftProducts || [])];
    draftProducts[index] = { ...draftProducts[index], ...patch };
    onChange({ ...value, draftProducts });
  };

  const updateSealed = (index, patch) => {
    const sealedProducts = [...(value.sealedProducts || [])];
    sealedProducts[index] = { ...sealedProducts[index], ...patch };
    onChange({ ...value, sealedProducts });
  };

  return (
    <div className="mb-3 text-sm text-white">
      <label className="block mb-1">Format</label>
      <select
        className="w-full text-black rounded px-2 py-1 mb-2"
        value={mode}
        onChange={(e) => setMode(e.target.value)}
      >
        {MODES.map((opt) => (
          <option key={opt.value} value={opt.value}>{opt.label}</option>
        ))}
      </select>

      {mode !== "constructed" && (mode === "draft" || mode === "sealed_draft") && (
        <div className="mb-2">
          <div className="mb-1">Draft boosters</div>
          {(value?.draftProducts || []).map((row, index) => (
            <div key={index} className="flex gap-1 mb-1">
              <select
                className="flex-1 text-black rounded px-1 py-1"
                value={row.productId || ""}
                onChange={(e) => updateDraft(index, { productId: e.target.value })}
              >
                <option value="">Product…</option>
                {boosterProducts.map((p) => (
                  <option key={p.id} value={p.id}>{p.label}</option>
                ))}
              </select>
              <input
                type="number"
                min="1"
                max="12"
                className="w-16 text-black rounded px-1 py-1"
                value={row.count || 1}
                onChange={(e) => updateDraft(index, { count: parseInt(e.target.value, 10) || 1 })}
              />
              <button
                type="button"
                className="px-2 bg-gray-600 rounded"
                onClick={() => onChange({ ...value, draftProducts: value.draftProducts.filter((_, i) => i !== index) })}
              >
                ×
              </button>
            </div>
          ))}
          <button
            type="button"
            className="text-xs underline"
            onClick={() => onChange({
              ...value,
              draftProducts: [...(value.draftProducts || []), { productId: boosterProducts[0]?.id, count: 1 }],
            })}
          >
            Add booster product
          </button>
        </div>
      )}

      {mode !== "constructed" && (mode === "sealed" || mode === "sealed_draft") && (
        <div className="mb-2">
          <div className="mb-1">Sealed products</div>
          {(value?.sealedProducts || []).map((row, index) => (
            <div key={index} className="flex gap-1 mb-1">
              <select
                className="flex-1 text-black rounded px-1 py-1"
                value={row.kind === "prebuilt" ? `prebuilt:${row.id}` : row.kind === "deck" ? `deck:${row.id}` : `product:${row.productId || row.id || ""}`}
                onChange={(e) => {
                  const raw = e.target.value;
                  if (raw.startsWith("prebuilt:")) {
                    updateSealed(index, { kind: "prebuilt", id: raw.slice(9), productId: undefined, load_list: undefined, count: 1 });
                  } else if (raw.startsWith("deck:")) {
                    const deck = publicDecks.find((d) => String(d.id) === raw.slice(5));
                    updateSealed(index, { kind: "deck", id: deck?.id, load_list: deck?.load_list, productId: undefined, count: 1 });
                  } else {
                    updateSealed(index, { kind: "product", productId: raw.slice(8), id: undefined, load_list: undefined, count: row.count || 1 });
                  }
                }}
              >
                <option value="">Product…</option>
                {sealedDecks.filter((d) => d.kind === "prebuilt").map((d) => (
                  <option key={d.id} value={`prebuilt:${d.id}`}>{d.label}</option>
                ))}
                {publicDecks.map((d) => (
                  <option key={d.id} value={`deck:${d.id}`}>{d.name} (public)</option>
                ))}
                {boosterProducts.map((p) => (
                  <option key={p.id} value={`product:${p.id}`}>{p.label} (generated)</option>
                ))}
              </select>
              {row.kind === "product" && (
                <input
                  type="number"
                  min="1"
                  max="12"
                  className="w-16 text-black rounded px-1 py-1"
                  value={row.count || 1}
                  onChange={(e) => updateSealed(index, { count: parseInt(e.target.value, 10) || 1 })}
                />
              )}
              <button
                type="button"
                className="px-2 bg-gray-600 rounded"
                onClick={() => onChange({ ...value, sealedProducts: value.sealedProducts.filter((_, i) => i !== index) })}
              >
                ×
              </button>
            </div>
          ))}
          <button
            type="button"
            className="text-xs underline"
            onClick={() => onChange({
              ...value,
              sealedProducts: [...(value.sealedProducts || []), sealedDecks[0] ? { kind: "prebuilt", id: sealedDecks[0].id } : { kind: "product", productId: boosterProducts[0]?.id, count: 1 }],
            })}
          >
            Add sealed product
          </button>
        </div>
      )}
      {mode !== "constructed" && !user?.id && (
        <div className="text-xs text-red-300">Log in to create a limited table.</div>
      )}
    </div>
  );
};
