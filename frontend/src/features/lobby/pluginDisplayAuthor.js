/** Credit line for lobby listings: game_def.author, else the uploading user. */
export const pluginDisplayAuthor = (plugin) => {
  const named = typeof plugin?.author === "string" ? plugin.author.trim() : "";
  return named || plugin?.author_alias || "";
};
