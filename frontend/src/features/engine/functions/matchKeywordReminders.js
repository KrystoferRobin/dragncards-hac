function stripMarkup(text) {
  return String(text)
    .replace(/<[^>]+>/g, " ")
    .replace(/&[a-z0-9#]+;/gi, " ")
    .replace(/\s+/g, " ");
}

function termPattern(name) {
  const escaped = name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const parts = escaped.split(/\s+/).filter(Boolean);
  if (parts.length >= 2) {
    const last = parts.pop();
    return `${parts.join("\\s+")}(?:\\s+\\d+)?\\s+${last}`;
  }
  return `${escaped}(?:\\s+\\d+)?`;
}

/** Match glossary terms in printed card text, longest name first. */
export function matchKeywordReminders(text, glossary) {
  if (!text || !glossary || typeof glossary !== "object") return [];
  const haystack = stripMarkup(text);
  const names = Object.keys(glossary).sort((a, b) => b.length - a.length);
  const occupied = [];
  const hits = [];

  const overlaps = (start, end) => occupied.some(([s, e]) => start < e && end > s);

  for (const name of names) {
    const reminder = glossary[name];
    if (!reminder || reminder === "[null]") continue;
    const re = new RegExp(`\\b${termPattern(name)}\\b`, "gi");
    let match;
    while ((match = re.exec(haystack)) !== null) {
      const start = match.index;
      const end = start + match[0].length;
      if (overlaps(start, end)) continue;
      occupied.push([start, end]);
      hits.push({ name: match[0], reminder, index: start });
      break;
    }
  }

  hits.sort((a, b) => a.index - b.index);
  const seen = new Set();
  const out = [];
  for (const hit of hits) {
    if (seen.has(hit.reminder)) continue;
    seen.add(hit.reminder);
    out.push(hit);
  }
  return out;
}
