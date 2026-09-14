import React from "react";
import { useSiteL10n } from "../../../../hooks/useSiteL10n";

const basicKeys = [
  {
    key: "pluginName",
    label: "Plugin Name",
    type: "text",
    placeholder: "Enter plugin name",
  },
  {
    key: "author",
    label: "Author (lobby credit)",
    type: "text",
    placeholder: "Original author or community. Leave blank to show you.",
  },
  {
    key: "minPlayers",
    label: "Minimum Players",
    type: "number",
    placeholder: "Enter minimum players",
  },
  {
    key: "maxPlayers",
    label: "Maximum Players",
    type: "number",
    placeholder: "Enter maximum players",
  },
  {
    key: "backgroundUrl",
    label: "Background Image URL",
    type: "text",
    placeholder: "Enter background image URL",
  },
  {
    key: "bannerUrl",
    label: "Lobby Banner URL",
    type: "text",
    placeholder: "/cards/{game}/_plugin/banner2.jpg",
  },
  {
    key: "logoUrl",
    label: "Lobby Logo URL",
    type: "text",
    placeholder: "/cards/{game}/_plugin/logo2.jpg",
  },
  {
    key: "tutorialUrl",
    label: "Tutorial URL",
    type: "text",
    placeholder: "https://… (lobby button labeled Tutorial)",
  },
];

export const GameBasics = ({ inputs, setInputs }) => {
  console.log("GameBasics component rendered with inputs:", inputs);
  const siteL10n = useSiteL10n();

  const handleChange = (key, value) => {
    setInputs((prev) => ({
      ...prev,
      [key]: value,
    }));
  };

  return (
    <div className="max-w-3xl p-6 m-4 bg-gray-800 rounded-lg">
      {basicKeys.map(({ key, label, type, placeholder }) => (
        <div key={key} className="flex items-center space-x-4">
          <label className="flex-1 text-sm text-gray-300 p-1">
            {siteL10n(label)}:
            <input
              type={type}
              placeholder={placeholder}
              value={inputs[key] || ""}
              onChange={(e) => handleChange(key, e.target.value)}
              className="w-full bg-gray-800 text-white border border-gray-600 rounded px-2 py-1"
            />
          </label>
        </div>
      ))}
      <div className="mt-4 text-sm text-gray-300 p-1">
        Extra lobby buttons (rulebook, glossary, videos). Up to 8 including Tutorial.
        {Array.from({ length: 8 }).map((_, index) => {
          const row = (inputs.referenceLinks || [])[index] || { label: "", url: "" };
          return (
            <div key={index} className="flex gap-2 mt-1">
              <input
                type="text"
                placeholder={`Label ${index + 1}`}
                value={row.label || ""}
                onChange={(e) => {
                  const next = [...(inputs.referenceLinks || [])];
                  while (next.length < 8) next.push({ label: "", url: "" });
                  next[index] = { ...next[index], label: e.target.value };
                  setInputs((prev) => ({ ...prev, referenceLinks: next.slice(0, 8) }));
                }}
                className="w-1/3 bg-gray-800 text-white border border-gray-600 rounded px-2 py-1"
              />
              <input
                type="text"
                placeholder="https://…"
                value={row.url || ""}
                onChange={(e) => {
                  const next = [...(inputs.referenceLinks || [])];
                  while (next.length < 8) next.push({ label: "", url: "" });
                  next[index] = { ...next[index], url: e.target.value };
                  setInputs((prev) => ({ ...prev, referenceLinks: next.slice(0, 8) }));
                }}
                className="flex-1 bg-gray-800 text-white border border-gray-600 rounded px-2 py-1"
              />
            </div>
          );
        })}
      </div>
      {inputs.backgroundUrl && (
        <div className="mt-4">
          <img
            src={inputs.backgroundUrl}
            alt={siteL10n("Background Preview")}
            className="max-w-full max-h-64 rounded border border-gray-600"
            style={{ objectFit: "cover" }}
          />
        </div>
      )}
    </div>
  );

};
