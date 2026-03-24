import { app } from "../../../scripts/app.js";
import { createButtonRow, createError, createPanelShell, createSection, ensureMkrUIStyles } from "./uiSystem.js";

const EXT = "mkr.prompt_studio";
const STYLE_ID = "mkr-prompt-studio-style";
const NODE_NAME = "MKRCLIPTextEncodePrompt";
const DEFAULT_SIZE = [540, 760];

function getApi() {
  return window.comfyAPI?.api || window.api || null;
}

function apiUrl(path) {
  const api = getApi();
  if (api && typeof api.apiURL === "function") {
    return api.apiURL(path);
  }
  return path;
}

function getWidget(node, name) {
  return node.widgets?.find((widget) => widget?.name === name) || null;
}

function setWidgetValue(node, widget, value) {
  if (!widget) return;
  const previous = widget.value;
  if (String(previous ?? "") === String(value ?? "")) {
    return;
  }
  widget.value = value;
  if (typeof widget.callback === "function") {
    widget.callback(value, app?.graph, node, widget);
  }
  node.setDirtyCanvas?.(true, true);
  app?.graph?.setDirtyCanvas?.(true, true);
}

function ensurePromptStyles() {
  ensureMkrUIStyles();
  if (document.getElementById(STYLE_ID)) return;
  const style = document.createElement("style");
  style.id = STYLE_ID;
  style.textContent = `
    .mkr-prompt-panel {
      --mkr-ink: #f2f6fb;
      --mkr-muted: #8ca1b3;
      --mkr-line: rgba(186, 209, 226, 0.12);
      --mkr-card: #1f2328;
      --mkr-card-alt: #181c20;
      --mkr-accent: #d8ff5b;
      --mkr-accent-soft: rgba(216, 255, 91, 0.08);
      --mkr-accent-border: rgba(216, 255, 91, 0.24);
      --mkr-bg-0: #202428;
      --mkr-bg-1: #252a2f;
      --mkr-bg-2: #2a3036;
      width: 100%;
      max-width: none;
      max-height: none;
      overflow: hidden;
      padding: 10px;
      border-radius: 16px;
      border: 1px solid rgba(165, 187, 206, 0.14);
      background: var(--mkr-bg-1);
      color: var(--mkr-ink);
      box-shadow: inset 0 1px 0 rgba(255,255,255,0.02), 0 16px 40px rgba(0,0,0,0.28);
    }
    .mkr-prompt-panel .mkr-header {
      margin-bottom: 10px;
      padding: 12px 14px;
      border-radius: 14px;
      border: 1px solid rgba(165, 187, 206, 0.12);
      background: var(--mkr-card);
    }
    .mkr-prompt-panel .mkr-kicker {
      color: #a5b8c7;
      font-size: 10px;
      letter-spacing: 0.14em;
      margin-bottom: 5px;
    }
    .mkr-prompt-panel .mkr-title {
      color: #f7fbff;
      font-size: 24px;
      line-height: 1.05;
      letter-spacing: -0.03em;
      margin: 0;
    }
    .mkr-prompt-panel .mkr-subtitle {
      color: #8ea4b7;
      font-size: 12px;
      margin-top: 6px;
      line-height: 1.4;
    }
    .mkr-prompt-panel .mkr-section {
      margin-top: 0;
      padding: 10px;
      border-radius: 14px;
      border: 1px solid rgba(165, 187, 206, 0.1);
      background: var(--mkr-card-alt);
      box-shadow: none;
    }
    .mkr-prompt-panel .mkr-section-title {
      color: #f1f6fb;
      font-size: 12px;
      letter-spacing: 0.02em;
    }
    .mkr-prompt-panel .mkr-section-note {
      color: #7f95a8;
      font-size: 10px;
    }
    .mkr-prompt-summary {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 8px;
    }
    .mkr-prompt-stat {
      padding: 11px 12px;
      border-radius: 12px;
      background: #15191d;
      border: 1px solid rgba(165, 187, 206, 0.1);
    }
    .mkr-prompt-stat-label {
      font-size: 10px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: #8198ab;
      margin-bottom: 4px;
    }
    .mkr-prompt-stat-value {
      font-size: 18px;
      font-weight: 700;
      color: #f5fbff;
    }
    .mkr-prompt-grid {
      display: grid;
      grid-template-columns: minmax(0, 1.25fr) minmax(235px, 0.9fr);
      gap: 10px;
      min-height: 0;
    }
    .mkr-prompt-compose,
    .mkr-prompt-library {
      display: flex;
      flex-direction: column;
      gap: 8px;
      min-height: 0;
    }
    .mkr-prompt-label {
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: #89a0b3;
      font-weight: 700;
      margin-bottom: 4px;
    }
    .mkr-prompt-textarea,
    .mkr-prompt-notes,
    .mkr-prompt-input,
    .mkr-prompt-search {
      width: 100%;
      box-sizing: border-box;
      border: 1px solid rgba(165, 187, 206, 0.12);
      border-radius: 12px;
      background: #111417;
      color: #edf4fb;
      padding: 10px 12px;
      font-family: "IBM Plex Mono", "SFMono-Regular", Consolas, monospace;
      font-size: 12px;
      outline: none;
      transition: border-color 120ms ease, box-shadow 120ms ease, background 120ms ease;
    }
    .mkr-prompt-textarea:focus,
    .mkr-prompt-notes:focus,
    .mkr-prompt-input:focus,
    .mkr-prompt-search:focus {
      border-color: rgba(216, 255, 91, 0.42);
      box-shadow: 0 0 0 3px rgba(216, 255, 91, 0.08);
      background: #0f1215;
    }
    .mkr-prompt-textarea {
      min-height: 290px;
      resize: vertical;
      line-height: 1.48;
    }
    .mkr-prompt-notes {
      min-height: 92px;
      resize: vertical;
      line-height: 1.4;
    }
    .mkr-prompt-row {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 8px;
    }
    .mkr-prompt-chip-row {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
    }
    .mkr-prompt-chip {
      border: 1px solid rgba(165, 187, 206, 0.12);
      background: #15191d;
      color: #d8e4ee;
      border-radius: 999px;
      padding: 5px 10px;
      font-size: 11px;
      font-weight: 700;
      cursor: pointer;
    }
    .mkr-prompt-chip[data-active="true"] {
      background: #222821;
      border-color: rgba(216, 255, 91, 0.35);
      color: #eff9b6;
    }
    .mkr-prompt-bookmarks {
      min-height: 260px;
      max-height: 420px;
      overflow: auto;
      display: flex;
      flex-direction: column;
      gap: 7px;
      padding-right: 2px;
    }
    .mkr-prompt-bookmark {
      border: 1px solid rgba(165, 187, 206, 0.1);
      border-radius: 13px;
      padding: 10px;
      background: #15191d;
      cursor: pointer;
      transition: transform 120ms ease, border-color 120ms ease, box-shadow 120ms ease;
    }
    .mkr-prompt-bookmark:hover {
      transform: translateY(-1px);
      border-color: rgba(216, 255, 91, 0.24);
      box-shadow: 0 12px 24px rgba(0, 0, 0, 0.22);
    }
    .mkr-prompt-bookmark[data-active="true"] {
      border-color: rgba(216, 255, 91, 0.38);
      background: #20251d;
    }
    .mkr-prompt-bookmark-top {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      margin-bottom: 5px;
    }
    .mkr-prompt-bookmark-name {
      font-size: 13px;
      font-weight: 700;
      color: #f4f8fc;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .mkr-prompt-bookmark-folder {
      font-size: 10px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: #8ca1b3;
    }
    .mkr-prompt-bookmark-snippet {
      font-size: 11px;
      line-height: 1.4;
      color: #9cb1c1;
      display: -webkit-box;
      -webkit-line-clamp: 3;
      -webkit-box-orient: vertical;
      overflow: hidden;
      margin-bottom: 6px;
    }
    .mkr-prompt-bookmark-meta {
      display: flex;
      flex-wrap: wrap;
      gap: 5px;
      align-items: center;
    }
    .mkr-prompt-tag {
      font-size: 10px;
      border-radius: 999px;
      padding: 3px 8px;
      background: #222821;
      color: #dae8b5;
    }
    .mkr-prompt-empty {
      padding: 18px 14px;
      border-radius: 12px;
      border: 1px dashed rgba(165, 187, 206, 0.14);
      color: #91a5b5;
      font-size: 12px;
      text-align: center;
      background: #14181c;
    }
    .mkr-prompt-foot {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      font-size: 11px;
      color: #7f94a6;
    }
    .mkr-prompt-checkbox-wrap {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      font-size: 11px;
      font-weight: 700;
      color: #dbe6ef;
    }
    .mkr-prompt-panel .mkr-btn {
      border-radius: 10px;
      border: 1px solid rgba(165, 187, 206, 0.12);
      background: #171b1f;
      color: #e6eef5;
      font-size: 11px;
      font-weight: 700;
      min-height: 34px;
      box-shadow: none;
    }
    .mkr-prompt-panel .mkr-btn[data-tone="accent"] {
      background: #2b3320;
      border-color: rgba(216, 255, 91, 0.34);
      color: #d8ff5b;
    }
    .mkr-prompt-panel .mkr-btn:hover {
      transform: translateY(-1px);
      border-color: rgba(216, 255, 91, 0.26);
    }
    .mkr-prompt-btn-row .mkr-btn {
      flex: 1 1 0;
      justify-content: center;
    }
    @media (max-width: 760px) {
      .mkr-prompt-grid {
        grid-template-columns: 1fr;
      }
      .mkr-prompt-summary {
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }
      .mkr-prompt-row {
        grid-template-columns: 1fr;
      }
    }
  `;
  document.head.appendChild(style);
}

function hideWidget(widget) {
  if (!widget || widget.__mkrPromptHidden) return;
  widget.__mkrPromptHidden = true;
  widget.type = "hidden";
  widget.hidden = true;
  widget.visible = false;
  widget.last_y = 0;
  widget.computeSize = () => [0, 0];
  if (widget.options && typeof widget.options === "object") {
    widget.options.serialize = true;
    widget.options.hidden = true;
  }
}

function clampText(text, limit = 160) {
  return String(text || "").trim().slice(0, limit);
}

function formatUpdatedAt(value) {
  const timestamp = Number(value || 0);
  if (!Number.isFinite(timestamp) || timestamp <= 0) return "now";
  try {
    return new Date(timestamp * 1000).toLocaleString([], {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return "updated";
  }
}

function buildPromptPanel(node) {
  ensurePromptStyles();
  const promptWidget = getWidget(node, "prompt_text");
  if (promptWidget) {
    hideWidget(promptWidget);
  }

  const { panel } = createPanelShell({
    kicker: "MKR Shift Prompt",
    title: "Prompt Writer",
    subtitle: "Write, shape, bookmark, and recall prompts in one place without the usual node clutter.",
  });
  panel.classList.add("mkr-prompt-panel");

  if (!promptWidget) {
    panel.appendChild(createError("prompt_text widget not found."));
    return panel;
  }

  node.properties = node.properties || {};
  const state = node.properties.mkrPromptState || {};
  node.properties.mkrPromptState = state;

  let bookmarks = [];
  let folders = [];
  let selectedId = String(state.selectedId || "");
  let activeFolder = String(state.activeFolder || "");
  let activeSearch = String(state.activeSearch || "");
  let statusText = "Ready";

  const summarySection = createSection({ title: "Prompt Stats", note: "Live", delayMs: 20 });
  const summary = document.createElement("div");
  summary.className = "mkr-prompt-summary";
  const statCards = {};
  for (const key of ["Chars", "Words", "Lines", "Tokens"]) {
    const card = document.createElement("div");
    card.className = "mkr-prompt-stat";
    const label = document.createElement("div");
    label.className = "mkr-prompt-stat-label";
    label.textContent = key;
    const value = document.createElement("div");
    value.className = "mkr-prompt-stat-value";
    value.textContent = "0";
    card.append(label, value);
    statCards[key.toLowerCase()] = value;
    summary.appendChild(card);
  }
  summarySection.body.appendChild(summary);
  panel.appendChild(summarySection.section);

  const workspaceSection = createSection({ title: "Prompt Workspace", note: "Compose + library", delayMs: 45 });
  const grid = document.createElement("div");
  grid.className = "mkr-prompt-grid";
  const compose = document.createElement("div");
  compose.className = "mkr-prompt-compose";
  const library = document.createElement("div");
  library.className = "mkr-prompt-library";

  const promptLabel = document.createElement("div");
  promptLabel.className = "mkr-prompt-label";
  promptLabel.textContent = "Prompt";
  const promptArea = document.createElement("textarea");
  promptArea.className = "mkr-prompt-textarea";
  promptArea.value = String(promptWidget.value || "");
  promptArea.placeholder = "Write the prompt here. Build reusable looks, character language, shot framing, materials, style blocks, and saved production prompts.";
  promptArea.addEventListener("input", () => {
    setWidgetValue(node, promptWidget, promptArea.value);
    updateStats();
  });

  const rowA = document.createElement("div");
  rowA.className = "mkr-prompt-row";
  const nameWrap = document.createElement("div");
  const nameLabel = document.createElement("div");
  nameLabel.className = "mkr-prompt-label";
  nameLabel.textContent = "Bookmark Name";
  const nameInput = document.createElement("input");
  nameInput.className = "mkr-prompt-input";
  nameInput.value = String(state.bookmarkName || "");
  nameInput.placeholder = "Hero prompt / ad copy / texture base";
  nameWrap.append(nameLabel, nameInput);
  const folderWrap = document.createElement("div");
  const folderLabel = document.createElement("div");
  folderLabel.className = "mkr-prompt-label";
  folderLabel.textContent = "Folder";
  const folderInput = document.createElement("input");
  folderInput.className = "mkr-prompt-input";
  folderInput.value = String(state.bookmarkFolder || "Default");
  folderInput.placeholder = "Characters / Looks / Ads / Surfaces";
  folderWrap.append(folderLabel, folderInput);
  rowA.append(nameWrap, folderWrap);

  const rowB = document.createElement("div");
  rowB.className = "mkr-prompt-row";
  const tagsWrap = document.createElement("div");
  const tagsLabel = document.createElement("div");
  tagsLabel.className = "mkr-prompt-label";
  tagsLabel.textContent = "Tags";
  const tagsInput = document.createElement("input");
  tagsInput.className = "mkr-prompt-input";
  tagsInput.value = String(state.bookmarkTags || "");
  tagsInput.placeholder = "portrait, cinematic, product";
  tagsWrap.append(tagsLabel, tagsInput);
  const notesWrap = document.createElement("div");
  const notesLabel = document.createElement("div");
  notesLabel.className = "mkr-prompt-label";
  notesLabel.textContent = "Notes";
  const favoriteWrap = document.createElement("label");
  favoriteWrap.className = "mkr-prompt-checkbox-wrap";
  const favoriteInput = document.createElement("input");
  favoriteInput.type = "checkbox";
  favoriteInput.checked = !!state.favorite;
  favoriteWrap.append(favoriteInput, document.createTextNode("Favorite"));
  notesWrap.append(notesLabel, favoriteWrap);
  rowB.append(tagsWrap, notesWrap);

  const notesAreaLabel = document.createElement("div");
  notesAreaLabel.className = "mkr-prompt-label";
  notesAreaLabel.textContent = "Bookmark Notes";
  const notesArea = document.createElement("textarea");
  notesArea.className = "mkr-prompt-notes";
  notesArea.value = String(state.bookmarkNotes || "");
  notesArea.placeholder = "Optional notes for how this prompt should be used.";

  const actionRow = createButtonRow([
    {
      label: "Save Bookmark",
      tone: "accent",
      onClick: () => saveBookmark(false),
    },
    {
      label: "Save Copy",
      onClick: () => saveBookmark(true),
    },
    {
      label: "Clear Draft",
      onClick: clearDraft,
    },
  ]);
  actionRow.classList.add("mkr-prompt-btn-row");

  compose.append(promptLabel, promptArea, rowA, rowB, notesAreaLabel, notesArea, actionRow);

  const searchLabel = document.createElement("div");
  searchLabel.className = "mkr-prompt-label";
  searchLabel.textContent = "Search Library";
  const searchInput = document.createElement("input");
  searchInput.className = "mkr-prompt-search";
  searchInput.value = activeSearch;
  searchInput.placeholder = "Search by name, folder, tags, or prompt text";
  searchInput.addEventListener("input", () => {
    activeSearch = searchInput.value;
    state.activeSearch = activeSearch;
    renderBookmarks();
  });

  const folderFilterLabel = document.createElement("div");
  folderFilterLabel.className = "mkr-prompt-label";
  folderFilterLabel.textContent = "Folders";
  const folderChips = document.createElement("div");
  folderChips.className = "mkr-prompt-chip-row";

  const bookmarkList = document.createElement("div");
  bookmarkList.className = "mkr-prompt-bookmarks";

  const libraryActions = createButtonRow([
    { label: "Load Selected", tone: "accent", onClick: loadSelectedBookmark },
    { label: "Delete Selected", onClick: deleteSelectedBookmark },
  ]);
  libraryActions.classList.add("mkr-prompt-btn-row");

  const foot = document.createElement("div");
  foot.className = "mkr-prompt-foot";
  const statusNode = document.createElement("span");
  statusNode.textContent = statusText;
  const selectionNode = document.createElement("span");
  selectionNode.textContent = "No bookmark selected";
  foot.append(statusNode, selectionNode);

  library.append(searchLabel, searchInput, folderFilterLabel, folderChips, bookmarkList, libraryActions, foot);
  grid.append(compose, library);
  workspaceSection.body.appendChild(grid);
  panel.appendChild(workspaceSection.section);

  async function fetchBookmarks() {
    statusText = "Loading library...";
    statusNode.textContent = statusText;
    try {
      const response = await fetch(apiUrl("/mkrshift/prompt_bookmarks/list"));
      const payload = await response.json();
      bookmarks = Array.isArray(payload?.bookmarks) ? payload.bookmarks : [];
      folders = Array.isArray(payload?.folders) ? payload.folders : [];
      renderFolderChips();
      renderBookmarks();
      statusText = `${bookmarks.length} bookmark${bookmarks.length === 1 ? "" : "s"} ready`;
    } catch (error) {
      bookmarks = [];
      folders = [];
      renderFolderChips();
      renderBookmarks();
      statusText = `Bookmark library unavailable: ${error?.message || error}`;
    }
    statusNode.textContent = statusText;
  }

  function updateStats() {
    const text = String(promptArea.value || "");
    const words = text.trim() ? text.trim().split(/\s+/).length : 0;
    const lines = text ? text.split("\n").length : 0;
    const tokens = text ? Math.max(1, Math.round(text.length / 3.8)) : 0;
    statCards.chars.textContent = String(text.length);
    statCards.words.textContent = String(words);
    statCards.lines.textContent = String(lines);
    statCards.tokens.textContent = String(tokens);
  }

  function selectedBookmark() {
    return bookmarks.find((item) => item.id === selectedId) || null;
  }

  function shouldUpdateSelectedBookmark(name, folder, prompt, notes, tags, favorite) {
    const bookmark = selectedBookmark();
    if (!bookmark) return false;
    if (String(bookmark.name || "") !== String(name || "")) return false;
    if (String(bookmark.folder || "Default") !== String(folder || "Default")) return false;
    return true;
  }

  function applyBookmarkToDraft(bookmark) {
    if (!bookmark) return;
    state.selectedId = selectedId = String(bookmark.id || "");
    state.bookmarkName = nameInput.value = String(bookmark.name || "");
    state.bookmarkFolder = folderInput.value = String(bookmark.folder || "Default");
    state.bookmarkTags = tagsInput.value = Array.isArray(bookmark.tags) ? bookmark.tags.join(", ") : "";
    state.bookmarkNotes = notesArea.value = String(bookmark.notes || "");
    state.favorite = favoriteInput.checked = !!bookmark.favorite;
    selectionNode.textContent = `Selected: ${bookmark.folder || "Default"} / ${bookmark.name || "Bookmark"}`;
  }

  function clearDraft() {
    selectedId = "";
    state.selectedId = "";
    nameInput.value = "";
    tagsInput.value = "";
    notesArea.value = "";
    favoriteInput.checked = false;
    selectionNode.textContent = "No bookmark selected";
    renderBookmarks();
  }

  function renderFolderChips() {
    folderChips.innerHTML = "";
    const folderValues = ["", ...folders];
    for (const folder of folderValues) {
      const chip = document.createElement("button");
      chip.className = "mkr-prompt-chip";
      chip.type = "button";
      chip.dataset.active = String(activeFolder === folder);
      chip.textContent = folder || "All";
      chip.addEventListener("click", () => {
        activeFolder = folder;
        state.activeFolder = activeFolder;
        renderFolderChips();
        renderBookmarks();
      });
      folderChips.appendChild(chip);
    }
  }

  function renderBookmarks() {
    bookmarkList.innerHTML = "";
    const search = String(activeSearch || "").trim().toLowerCase();
    const filtered = bookmarks.filter((item) => {
      if (activeFolder && item.folder !== activeFolder) return false;
      if (!search) return true;
      const haystack = [
        item.name,
        item.folder,
        ...(Array.isArray(item.tags) ? item.tags : []),
        item.prompt,
        item.notes,
      ]
        .join(" ")
        .toLowerCase();
      return haystack.includes(search);
    });

    if (!filtered.length) {
      const empty = document.createElement("div");
      empty.className = "mkr-prompt-empty";
      empty.textContent = bookmarks.length
        ? "No bookmarks match the current search or folder filter."
        : "No bookmarks yet. Save the current prompt to start building a reusable prompt library.";
      bookmarkList.appendChild(empty);
      return;
    }

    for (const bookmark of filtered) {
      const item = document.createElement("div");
      item.className = "mkr-prompt-bookmark";
      item.dataset.active = String(bookmark.id === selectedId);
      item.addEventListener("click", () => {
        applyBookmarkToDraft(bookmark);
        renderBookmarks();
      });
      item.addEventListener("dblclick", () => {
        applyBookmarkToDraft(bookmark);
        loadSelectedBookmark();
      });

      const top = document.createElement("div");
      top.className = "mkr-prompt-bookmark-top";
      const nameNode = document.createElement("div");
      nameNode.className = "mkr-prompt-bookmark-name";
      nameNode.textContent = bookmark.name || "Untitled";
      const folderNode = document.createElement("div");
      folderNode.className = "mkr-prompt-bookmark-folder";
      folderNode.textContent = `${bookmark.favorite ? "★ " : ""}${bookmark.folder || "Default"}`;
      top.append(nameNode, folderNode);

      const snippet = document.createElement("div");
      snippet.className = "mkr-prompt-bookmark-snippet";
      snippet.textContent = String(bookmark.prompt || "");

      const meta = document.createElement("div");
      meta.className = "mkr-prompt-bookmark-meta";
      const updated = document.createElement("span");
      updated.className = "mkr-prompt-tag";
      updated.textContent = formatUpdatedAt(bookmark.updated_at);
      meta.appendChild(updated);
      for (const tag of Array.isArray(bookmark.tags) ? bookmark.tags.slice(0, 4) : []) {
        const tagNode = document.createElement("span");
        tagNode.className = "mkr-prompt-tag";
        tagNode.textContent = tag;
        meta.appendChild(tagNode);
      }

      item.append(top, snippet, meta);
      bookmarkList.appendChild(item);
    }
  }

  async function saveBookmark(asCopy) {
    const prompt = String(promptArea.value || "").trim();
    const name = clampText(nameInput.value || prompt.split("\n")[0] || "", 160);
    const folder = clampText(folderInput.value || "Default", 160) || "Default";
    if (!prompt || !name) {
      statusText = "Name and prompt are required to save a bookmark.";
      statusNode.textContent = statusText;
      return;
    }
    const updateExisting = !asCopy && shouldUpdateSelectedBookmark(
      name,
      folder,
      prompt,
      notesArea.value,
      tagsInput.value,
      favoriteInput.checked
    );
    const payload = {
      id: updateExisting ? selectedId : "",
      folder,
      name,
      prompt,
      notes: notesArea.value,
      tags: tagsInput.value,
      favorite: favoriteInput.checked,
    };
    statusText = "Saving bookmark...";
    statusNode.textContent = statusText;
    try {
      const response = await fetch(apiUrl("/mkrshift/prompt_bookmarks/save"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const result = await response.json();
      if (!response.ok || !result?.ok) {
        throw new Error(result?.error || `HTTP ${response.status}`);
      }
      applyBookmarkToDraft(result.bookmark);
      await fetchBookmarks();
      statusText = result.updated ? "Bookmark updated." : "Bookmark saved as new.";
      statusNode.textContent = statusText;
    } catch (error) {
      statusText = `Save failed: ${error?.message || error}`;
      statusNode.textContent = statusText;
    }
  }

  function loadSelectedBookmark() {
    const bookmark = selectedBookmark();
    if (!bookmark) {
      statusText = "Select a bookmark first.";
      statusNode.textContent = statusText;
      return;
    }
    promptArea.value = String(bookmark.prompt || "");
    setWidgetValue(node, promptWidget, promptArea.value);
    applyBookmarkToDraft(bookmark);
    updateStats();
    statusText = `Loaded prompt: ${bookmark.name}`;
    statusNode.textContent = statusText;
  }

  async function deleteSelectedBookmark() {
    const bookmark = selectedBookmark();
    if (!bookmark) {
      statusText = "Select a bookmark first.";
      statusNode.textContent = statusText;
      return;
    }
    statusText = "Deleting bookmark...";
    statusNode.textContent = statusText;
    try {
      const response = await fetch(apiUrl("/mkrshift/prompt_bookmarks/delete"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: bookmark.id }),
      });
      const result = await response.json();
      if (!response.ok || !result?.ok) {
        throw new Error(result?.error || `HTTP ${response.status}`);
      }
      clearDraft();
      await fetchBookmarks();
      statusText = "Bookmark deleted.";
      statusNode.textContent = statusText;
    } catch (error) {
      statusText = `Delete failed: ${error?.message || error}`;
      statusNode.textContent = statusText;
    }
  }

  [nameInput, folderInput, tagsInput, notesArea, favoriteInput].forEach((input) => {
    const eventName = input.tagName === "TEXTAREA" ? "input" : "change";
    input.addEventListener(eventName, () => {
      state.bookmarkName = nameInput.value;
      state.bookmarkFolder = folderInput.value;
      state.bookmarkTags = tagsInput.value;
      state.bookmarkNotes = notesArea.value;
      state.favorite = favoriteInput.checked;
    });
  });

  updateStats();
  fetchBookmarks();
  return panel;
}

function applyPromptNodeExtension(node) {
  if (!node || node.__mkrPromptStudioInstalled) return;
  node.__mkrPromptStudioInstalled = true;

  const promptWidget = getWidget(node, "prompt_text");
  if (promptWidget) {
    hideWidget(promptWidget);
  }

  const panel = buildPromptPanel(node);
  const domWidget = node.addDOMWidget?.("mkr_prompt_studio_panel", "DOM", panel, {
    serialize: false,
    hideOnZoom: false,
  });

  if (domWidget) {
    domWidget.computeSize = () => [Math.max(DEFAULT_SIZE[0], node.size?.[0] || DEFAULT_SIZE[0]), DEFAULT_SIZE[1]];
  }

  const originalOnResize = node.onResize;
  node.onResize = function onResize(size) {
    const result = originalOnResize?.apply(this, arguments);
    const prompt = getWidget(this, "prompt_text");
    if (prompt) {
      hideWidget(prompt);
    }
    if (panel) {
      panel.style.width = "100%";
    }
    return result;
  };

  if (!Array.isArray(node.size) || node.size.length < 2) {
    node.size = DEFAULT_SIZE.slice();
  } else {
    node.size = [Math.max(node.size[0], DEFAULT_SIZE[0]), Math.max(node.size[1], DEFAULT_SIZE[1])];
  }
}

app.registerExtension({
  name: EXT,
  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (!nodeData || nodeData.name !== NODE_NAME) {
      return;
    }

    const originalOnNodeCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function onNodeCreated() {
      const result = originalOnNodeCreated?.apply(this, arguments);
      applyPromptNodeExtension(this);
      return result;
    };
  },
});
