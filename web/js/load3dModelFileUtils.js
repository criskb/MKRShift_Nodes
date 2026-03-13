export function normalizeModelFile(value) {
  return typeof value === "string" ? value.trim() : "";
}

function firstString(value) {
  if (Array.isArray(value)) {
    for (const entry of value) {
      const candidate = normalizeModelFile(entry);
      if (candidate) {
        return candidate;
      }
    }
    return "";
  }
  return normalizeModelFile(value);
}

export function extractModelFileCandidate(payload) {
  for (const candidate of [
    payload?.model_file,
    payload?.output?.model_file,
    payload?.result?.[0],
    payload?.output?.result?.[0],
  ]) {
    const normalized = firstString(candidate);
    if (normalized) {
      return normalized;
    }
  }
  return "";
}

export function parseModelFileReference(value, fallbackType = "input") {
  const raw = normalizeModelFile(value);
  if (!raw) {
    return null;
  }

  if (/^https?:\/\//i.test(raw)) {
    return {
      raw,
      cleanPath: raw,
      subfolder: "",
      filename: raw,
      type: null,
      widgetValue: raw,
      isRemote: true,
    };
  }

  const suffixMatch = raw.match(/\s*\[(output|input|temp)\]\s*$/i);
  const type = (suffixMatch?.[1] || fallbackType || "input").toLowerCase();
  const cleanPath = suffixMatch ? raw.slice(0, suffixMatch.index).trim() : raw;
  const separatorIndex = cleanPath.lastIndexOf("/");
  const subfolder = separatorIndex === -1 ? "" : cleanPath.slice(0, separatorIndex);
  const filename = separatorIndex === -1 ? cleanPath : cleanPath.slice(separatorIndex + 1);

  return {
    raw,
    cleanPath,
    subfolder,
    filename,
    type,
    widgetValue: cleanPath,
    isRemote: false,
  };
}
