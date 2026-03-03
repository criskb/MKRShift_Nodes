import { app } from "../../../scripts/app.js";

const UI = {
  MIN_W: 920,
  MIN_H: 620,
  PAD: 14,
  SAFE_TOP: 72,
  SAFE_BOTTOM: 24,
  HEADER_H: 62,
  BOTTOM_H: 172,
  GAP: 12,
  LEFT_RATIO: 0.56,
  CARD_COLS: 2,
  CARD_ROWS: 3,
  CARD_GAP: 10,
};

const THEME = {
  shellStart: "#163146",
  shellEnd: "#275167",
  shellStroke: "#4d7d95",
  panelStart: "#fbf5e9",
  panelEnd: "#f0e4cf",
  panelStroke: "#cebea4",
  panelText: "#1d2b36",
  panelMuted: "#5f6f78",
  accent: "#e86f51",
  accentSoft: "#f4b08a",
  accentDeep: "#bf563c",
  accentAlt: "#2f9786",
  accentAltSoft: "#92d4c6",
  cardStart: "#fffaf1",
  cardEnd: "#f3e8d4",
  cardStroke: "#d8c4a1",
  cardSelectedStroke: "#e86f51",
  cardSelectedGlow: "rgba(232,111,81,0.35)",
  chipBg: "#f1ddbe",
  chipText: "#5f4f37",
  previewBg: "#d6e4ea",
  previewStroke: "#89a4b3",
  previewPlaceholder: "#6f8493",
  controlBg: "#f8efdf",
  controlStroke: "#cdb99a",
  controlValue: "#26343e",
  controlButtonBg: "#25586f",
  controlButtonText: "#f6f9fb",
  statusOk: "#2f9e44",
  statusWarn: "#bb6a0b",
  statusCardStart: "#f9ecd3",
  statusCardEnd: "#f0dec0",
  statusCardStroke: "#c9af84",
};

const FONT = {
  hero: "700 22px 'Avenir Next Condensed', 'Avenir Next', 'Trebuchet MS', 'Segoe UI', sans-serif",
  heading: "700 15px 'Avenir Next', 'Trebuchet MS', 'Segoe UI', sans-serif",
  label: "600 11px 'Avenir Next', 'Trebuchet MS', 'Segoe UI', sans-serif",
  body: "500 12px 'Avenir Next', 'Trebuchet MS', 'Segoe UI', sans-serif",
  bodyBold: "700 12px 'Avenir Next', 'Trebuchet MS', 'Segoe UI', sans-serif",
  tiny: "500 10px 'Avenir Next', 'Trebuchet MS', 'Segoe UI', sans-serif",
};

let packsRequest = null;

function getApi() {
  return globalThis?.api || globalThis?.comfyAPI?.api || null;
}

function apiUrl(path) {
  const p = String(path || "");
  const apiObj = getApi();
  if (apiObj && typeof apiObj.apiURL === "function") {
    return apiObj.apiURL(p);
  }
  return p;
}

function fetchApiCompat(path, init = undefined) {
  const comfyApi = getApi();
  if (comfyApi && typeof comfyApi.fetchApi === "function") {
    return comfyApi.fetchApi(path, init);
  }
  return fetch(path, init);
}

function matchesSocialPackName(name) {
  const token = String(name ?? "").toLowerCase().replace(/[^a-z0-9]+/g, "");
  if (!token) return false;
  if (token === "mkrshiftsocialpackbuilder") return true;
  return token.includes("socialpackbuilder");
}

function isSocialPackNode(node) {
  const candidates = [
    node?.comfyClass,
    node?.type,
    node?.title,
    node?.constructor?.comfyClass,
    node?.constructor?.type,
  ].filter(Boolean);
  return candidates.some(matchesSocialPackName);
}

function isSocialPackNodeDef(nodeData) {
  const candidates = [nodeData?.name, nodeData?.display_name, nodeData?.type].filter(Boolean);
  return candidates.some(matchesSocialPackName);
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function roundRectPath(ctx, x, y, w, h, r) {
  const radius = Math.min(r, w / 2, h / 2);
  ctx.beginPath();
  if (ctx.roundRect) {
    ctx.roundRect(x, y, w, h, radius);
  } else {
    ctx.rect(x, y, w, h);
  }
}

function drawRoundedFill(ctx, x, y, w, h, r, fill) {
  roundRectPath(ctx, x, y, w, h, r);
  ctx.fillStyle = fill;
  ctx.fill();
}

function drawRoundedStroke(ctx, x, y, w, h, r, stroke, lineWidth = 1) {
  roundRectPath(ctx, x, y, w, h, r);
  ctx.lineWidth = lineWidth;
  ctx.strokeStyle = stroke;
  ctx.stroke();
}

function drawRoundedGradient(ctx, rect, radius, colorA, colorB, vertical = true) {
  const g = vertical
    ? ctx.createLinearGradient(rect.x, rect.y, rect.x, rect.y + rect.h)
    : ctx.createLinearGradient(rect.x, rect.y, rect.x + rect.w, rect.y + rect.h);
  g.addColorStop(0, colorA);
  g.addColorStop(1, colorB);
  drawRoundedFill(ctx, rect.x, rect.y, rect.w, rect.h, radius, g);
}

function trimText(ctx, text, maxWidth) {
  const raw = String(text ?? "");
  if (!raw) return "";
  if (ctx.measureText(raw).width <= maxWidth) return raw;
  let value = raw;
  while (value.length > 1 && ctx.measureText(`${value}...`).width > maxWidth) {
    value = value.slice(0, -1);
  }
  return `${value}...`;
}

function drawWrappedText(ctx, text, x, y, maxWidth, lineHeight, maxLines) {
  const words = String(text ?? "").split(/\s+/).filter(Boolean);
  if (!words.length) return 0;

  const lines = [];
  let current = words[0];
  for (let i = 1; i < words.length; i++) {
    const next = `${current} ${words[i]}`;
    if (ctx.measureText(next).width <= maxWidth) {
      current = next;
    } else {
      lines.push(current);
      current = words[i];
      if (lines.length >= maxLines) break;
    }
  }
  if (lines.length < maxLines && current) {
    lines.push(current);
  }
  if (lines.length > maxLines) {
    lines.length = maxLines;
  }

  for (let i = 0; i < lines.length; i++) {
    let line = lines[i];
    if (i === maxLines - 1 && i < words.length) {
      line = trimText(ctx, line, maxWidth);
    }
    ctx.fillText(line, x, y + i * lineHeight);
  }
  return lines.length;
}

function extractPackId(value) {
  const text = String(value ?? "");
  if (text.includes("(") && text.endsWith(")")) {
    return text.split("(").pop().slice(0, -1).trim();
  }
  return text.trim();
}

function getWidget(node, name) {
  return node.widgets?.find((w) => w.name === name);
}

function getWidgetChoices(widget) {
  if (!widget) return [];
  if (Array.isArray(widget.options?.values)) return widget.options.values;
  if (Array.isArray(widget.values)) return widget.values;
  if (Array.isArray(widget.options)) return widget.options;
  return [];
}

function setWidgetValue(node, widget, value) {
  if (!widget) return;
  widget.value = value;
  if (typeof widget.callback === "function") {
    widget.callback(value, app.graph, node, widget);
  }
}

function markDirty(node) {
  node.setDirtyCanvas?.(true, true);
  app.graph?.setDirtyCanvas?.(true, true);
}

function hideWidget(widget) {
  if (!widget) return;
  widget.type = "hidden";
  widget.computeSize = () => [0, -4];
}

function hideBuiltInWidgets(node) {
  if (!Array.isArray(node.widgets)) return;
  for (const widget of node.widgets) {
    hideWidget(widget);
  }
}

function pointInRect(point, rect) {
  if (!point || !rect) return false;
  return (
    point.x >= rect.x &&
    point.x <= rect.x + rect.w &&
    point.y >= rect.y &&
    point.y <= rect.y + rect.h
  );
}

function buildViewUrl(info) {
  if (!info?.filename) return "";
  const subfolder = info.subfolder ? `&subfolder=${encodeURIComponent(info.subfolder)}` : "";
  const type = info.type || "temp";
  return apiUrl(`/view?filename=${encodeURIComponent(info.filename)}${subfolder}&type=${encodeURIComponent(type)}`);
}

async function fetchPacksFromBackend() {
  if (!packsRequest) {
    packsRequest = (async () => {
      try {
        const response = await fetchApiCompat("/mkrshift_social/packs");
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();
        return Array.isArray(data) ? data : [];
      } catch (error) {
        console.warn("[mkrshift.socialpack] Failed to fetch packs:", error);
        packsRequest = null;
        return null;
      }
    })();
  }
  return packsRequest;
}

function fallbackPacksFromWidget(node) {
  const widget = getWidget(node, "pack");
  const values = getWidgetChoices(widget);
  return values.map((entry) => {
    const raw = String(entry);
    const id = extractPackId(raw);
    const name = raw.replace(/\s*\([^)]+\)\s*$/, "").trim() || id;
    return {
      id,
      name,
      tags: [],
      description: "",
      preview: "",
      default_count: 12,
      ratios: [],
      shot_count: 0,
      export: {},
    };
  });
}

function preloadPackImages(state) {
  for (const pack of state.packs) {
    if (!pack.preview) continue;
    if (state.packImages[pack.id]) continue;

    const entry = {
      img: new Image(),
      loaded: false,
      failed: false,
    };
    entry.img.onload = () => {
      entry.loaded = true;
      markDirty(state.node);
    };
    entry.img.onerror = () => {
      entry.failed = true;
      markDirty(state.node);
    };
    entry.img.src = apiUrl(pack.preview);
    state.packImages[pack.id] = entry;
  }
}

function queueRedraw(state) {
  if (state.redrawQueued) return;
  state.redrawQueued = true;
  const raf = globalThis.requestAnimationFrame || ((fn) => setTimeout(fn, 16));
  raf(() => {
    state.redrawQueued = false;
    markDirty(state.node);
  });
}

function syncPackSelection(node, state, packId) {
  if (!packId) return;
  state.selectedPackId = packId;
  state.selectionAnimStart = Date.now();
  node.properties = node.properties || {};
  node.properties.selected_pack_id = packId;

  const packIdWidget = getWidget(node, "pack_id");
  if (packIdWidget && packIdWidget.value !== packId) {
    setWidgetValue(node, packIdWidget, packId);
  }

  const packWidget = getWidget(node, "pack");
  if (packWidget) {
    const options = getWidgetChoices(packWidget);
    const match = options.find((option) => extractPackId(option) === packId);
    if (match && packWidget.value !== match) {
      setWidgetValue(node, packWidget, match);
    }
  }
}

function pickInitialPackId(node, packs) {
  const fromProperty = String(node.properties?.selected_pack_id ?? "").trim();
  if (fromProperty) return fromProperty;

  const packWidget = getWidget(node, "pack");
  const fromWidget = extractPackId(packWidget?.value ?? "");
  if (fromWidget) return fromWidget;

  return packs[0]?.id || "";
}

function loadInputPreviewImage(state, previewInfo) {
  if (!previewInfo?.filename) return;
  const url = buildViewUrl(previewInfo);
  if (!url) return;

  state.inputPreview = previewInfo;
  state.inputPreviewUrl = url;
  state.inputImage = {
    img: new Image(),
    loaded: false,
    failed: false,
  };
  state.inputImage.img.onload = () => {
    state.inputImage.loaded = true;
    markDirty(state.node);
  };
  state.inputImage.img.onerror = () => {
    state.inputImage.failed = true;
    markDirty(state.node);
  };
  state.inputImage.img.src = `${url}&_ts=${Date.now()}`;
}

function getImageLinked(node, inputName) {
  const input = node.inputs?.find((entry) => entry.name === inputName);
  return !!input?.link;
}

function getReadinessLines(node) {
  const lines = [];

  if (!getImageLinked(node, "image")) {
    lines.push({ level: "warn", text: "IMAGE input is not connected." });
  }

  const brandingValue = String(getWidget(node, "branding")?.value ?? "Off");
  if (brandingValue !== "Off" && !getImageLinked(node, "brand_logo")) {
    lines.push({ level: "warn", text: "Branding enabled, but logo input is missing." });
  }

  if (!lines.length) {
    return [{ level: "ok", text: "Ready to queue and generate." }];
  }

  return lines.slice(0, 3);
}

function getLocalPos(node, event, pos) {
  if (Array.isArray(pos) && pos.length >= 2) {
    return { x: pos[0], y: pos[1] };
  }
  if (event && typeof event.canvasX === "number" && typeof event.canvasY === "number") {
    return {
      x: event.canvasX - node.pos[0],
      y: event.canvasY - node.pos[1],
    };
  }
  return null;
}

function setNodeMinSize(node) {
  if (!Array.isArray(node.size) || node.size.length < 2) {
    node.size = [UI.MIN_W, UI.MIN_H];
    return;
  }
  node.size[0] = Math.max(node.size[0], UI.MIN_W);
  node.size[1] = Math.max(node.size[1], UI.MIN_H);
}

function ensureNodeState(node) {
  if (node.__mkrshiftSocialState) return node.__mkrshiftSocialState;

  const state = {
    node,
    packs: [],
    packImages: {},
    selectedPackId: "",
    page: 0,
    cardsPerPage: UI.CARD_COLS * UI.CARD_ROWS,
    loadingPacks: false,
    inputPreview: null,
    inputPreviewUrl: "",
    inputImage: null,
    selectionAnimStart: 0,
    redrawQueued: false,
    hitboxes: {
      libraryPanel: null,
      cards: [],
      prevPage: null,
      nextPage: null,
      controls: [],
      headerButtons: [],
    },
  };

  node.__mkrshiftSocialState = state;
  return state;
}

function getSelectedPack(state) {
  if (!state.packs.length) return null;
  const match = state.packs.find((pack) => pack.id === state.selectedPackId);
  return match || state.packs[0] || null;
}

function cycleWidgetValue(node, widgetName, step = 1) {
  const widget = getWidget(node, widgetName);
  if (!widget) return;
  const values = getWidgetChoices(widget);
  if (!values.length) return;

  const current = String(widget.value);
  const currentIndex = Math.max(0, values.findIndex((v) => String(v) === current));
  const nextIndex = (currentIndex + step + values.length) % values.length;
  setWidgetValue(node, widget, values[nextIndex]);
}

function adjustCount(node, direction) {
  const widget = getWidget(node, "count");
  if (!widget) return;
  const options = widget.options || {};
  const step = Number(options.step ?? 1);
  const min = Number(options.min ?? 1);
  const max = Number(options.max ?? 999);
  const value = Number(widget.value ?? min);
  const next = clamp(value + direction * step, min, max);
  setWidgetValue(node, widget, next);
}

function applyPackDefaults(node, state) {
  const pack = getSelectedPack(state);
  if (!pack) return;

  const countWidget = getWidget(node, "count");
  if (countWidget) {
    const options = countWidget.options || {};
    const min = Number(options.min ?? 1);
    const max = Number(options.max ?? 999);
    const fallback = Number(countWidget.value ?? min);
    const raw = Number(pack.default_count ?? fallback);
    const next = Number.isFinite(raw) ? clamp(raw, min, max) : fallback;
    setWidgetValue(node, countWidget, next);
  }

  const aspectWidget = getWidget(node, "aspect");
  const ratios = Array.isArray(pack.ratios) ? pack.ratios.map((r) => String(r)) : [];
  if (aspectWidget && ratios.length) {
    const choices = getWidgetChoices(aspectWidget).map((v) => String(v));
    const preferred = ratios.find((ratio) => choices.includes(ratio)) || ratios[0];
    if (preferred) {
      setWidgetValue(node, aspectWidget, preferred);
    }
  }

  markDirty(node);
}

function chooseRandomPack(node, state) {
  if (state.packs.length < 2) return;
  const pool = state.packs.filter((pack) => pack.id !== state.selectedPackId);
  const randomPack = pool[Math.floor(Math.random() * pool.length)] || state.packs[0];
  if (!randomPack) return;
  syncPackSelection(node, state, randomPack.id);
  markDirty(node);
}

function drawImageCover(ctx, image, x, y, w, h) {
  const iw = image.width;
  const ih = image.height;
  if (!iw || !ih) return;

  const scale = Math.max(w / iw, h / ih);
  const sw = w / scale;
  const sh = h / scale;
  const sx = (iw - sw) * 0.5;
  const sy = (ih - sh) * 0.5;
  ctx.drawImage(image, sx, sy, sw, sh, x, y, w, h);
}

function drawImageContain(ctx, image, x, y, w, h) {
  const iw = image.width;
  const ih = image.height;
  if (!iw || !ih) return;

  const scale = Math.min(w / iw, h / ih);
  const dw = iw * scale;
  const dh = ih * scale;
  const dx = x + (w - dw) * 0.5;
  const dy = y + (h - dh) * 0.5;
  ctx.drawImage(image, dx, dy, dw, dh);
}

function drawShellBackdrop(ctx, rect) {
  drawRoundedGradient(ctx, rect, 14, THEME.shellStart, THEME.shellEnd, false);
  drawRoundedStroke(ctx, rect.x, rect.y, rect.w, rect.h, 14, THEME.shellStroke, 1.2);

  const glowRect = {
    x: rect.x + 12,
    y: rect.y + 10,
    w: rect.w - 24,
    h: 20,
  };
  const g = ctx.createLinearGradient(glowRect.x, glowRect.y, glowRect.x + glowRect.w, glowRect.y);
  g.addColorStop(0, "rgba(244,176,138,0.0)");
  g.addColorStop(0.3, "rgba(244,176,138,0.42)");
  g.addColorStop(1, "rgba(47,151,134,0.0)");
  drawRoundedFill(ctx, glowRect.x, glowRect.y, glowRect.w, glowRect.h, 10, g);
}

function drawPanelBase(ctx, rect, radius = 12) {
  drawRoundedGradient(ctx, rect, radius, THEME.panelStart, THEME.panelEnd, true);
  drawRoundedStroke(ctx, rect.x, rect.y, rect.w, rect.h, radius, THEME.panelStroke, 1);
}

function drawHeader(ctx, node, state, rect, selectedPack) {
  state.hitboxes.headerButtons = [];
  drawPanelBase(ctx, rect, 12);

  const stripeRect = { x: rect.x + 10, y: rect.y + 10, w: rect.w - 20, h: 5 };
  const stripe = ctx.createLinearGradient(stripeRect.x, stripeRect.y, stripeRect.x + stripeRect.w, stripeRect.y);
  stripe.addColorStop(0, THEME.accentAlt);
  stripe.addColorStop(1, THEME.accent);
  drawRoundedFill(ctx, stripeRect.x, stripeRect.y, stripeRect.w, stripeRect.h, 3, stripe);

  ctx.fillStyle = THEME.panelText;
  ctx.font = FONT.hero;
  ctx.fillText("MKRshift Social Studio", rect.x + 14, rect.y + 42);

  ctx.fillStyle = THEME.panelMuted;
  ctx.font = FONT.body;
  const subtitle = selectedPack
    ? `${selectedPack.name} selected \u2022 ${state.packs.length} pack${state.packs.length === 1 ? "" : "s"}`
    : `No pack selected \u2022 ${state.packs.length} available`;
  ctx.fillText(trimText(ctx, subtitle, rect.w * 0.56), rect.x + 15, rect.y + 57);

  const buttons = [
    { id: "random", label: "Surprise" },
    { id: "defaults", label: "Use Defaults" },
    { id: "reload", label: "Reload" },
  ];

  ctx.font = FONT.label;
  const gap = 8;
  let cursorX = rect.x + rect.w - 14;
  for (let i = buttons.length - 1; i >= 0; i--) {
    const button = buttons[i];
    const textW = ctx.measureText(button.label).width;
    const w = Math.max(70, textW + 22);
    const h = 26;
    const b = { x: cursorX - w, y: rect.y + 24, w, h, action: button.id };

    const fill = button.id === "defaults" ? THEME.accentAlt : THEME.controlButtonBg;
    drawRoundedFill(ctx, b.x, b.y, b.w, b.h, 8, fill);
    drawRoundedStroke(ctx, b.x, b.y, b.w, b.h, 8, "rgba(255,255,255,0.24)", 1);

    ctx.fillStyle = THEME.controlButtonText;
    ctx.font = FONT.label;
    const tx = b.x + (b.w - textW) / 2;
    ctx.fillText(button.label, tx, b.y + 17);

    state.hitboxes.headerButtons.push(b);
    cursorX = b.x - gap;
  }
}

function drawLibrary(ctx, state, rect) {
  state.hitboxes.libraryPanel = rect;
  state.hitboxes.cards = [];
  state.hitboxes.prevPage = null;
  state.hitboxes.nextPage = null;

  drawPanelBase(ctx, rect, 12);

  ctx.fillStyle = THEME.panelText;
  ctx.font = FONT.heading;
  ctx.fillText("Pack Library", rect.x + 12, rect.y + 22);

  ctx.fillStyle = THEME.panelMuted;
  ctx.font = FONT.tiny;
  ctx.fillText(`${state.packs.length} curated flows`, rect.x + 12, rect.y + 36);

  const cardsTop = rect.y + 42;
  const cardsArea = {
    x: rect.x + 8,
    y: cardsTop,
    w: rect.w - 16,
    h: rect.h - 50,
  };

  const cols = UI.CARD_COLS;
  const rows = UI.CARD_ROWS;
  const gap = UI.CARD_GAP;
  const cardsPerPage = cols * rows;
  state.cardsPerPage = cardsPerPage;

  const totalPages = Math.max(1, Math.ceil(state.packs.length / cardsPerPage));
  state.page = clamp(state.page, 0, totalPages - 1);
  const pageStart = state.page * cardsPerPage;
  const pageItems = state.packs.slice(pageStart, pageStart + cardsPerPage);

  if (totalPages > 1) {
    const pagerText = `${state.page + 1}/${totalPages}`;
    ctx.font = FONT.tiny;
    const pagerWidth = ctx.measureText(pagerText).width;
    const btnW = 20;
    const btnH = 16;
    const right = rect.x + rect.w - 10;

    const prevRect = { x: right - btnW * 2 - 36, y: rect.y + 10, w: btnW, h: btnH };
    const nextRect = { x: right - btnW - 8, y: rect.y + 10, w: btnW, h: btnH };
    state.hitboxes.prevPage = prevRect;
    state.hitboxes.nextPage = nextRect;

    drawRoundedFill(ctx, prevRect.x, prevRect.y, prevRect.w, prevRect.h, 4, THEME.controlButtonBg);
    drawRoundedFill(ctx, nextRect.x, nextRect.y, nextRect.w, nextRect.h, 4, THEME.controlButtonBg);
    ctx.fillStyle = THEME.controlButtonText;
    ctx.fillText("<", prevRect.x + 7, prevRect.y + 12);
    ctx.fillText(">", nextRect.x + 7, nextRect.y + 12);

    ctx.fillStyle = THEME.panelMuted;
    ctx.fillText(pagerText, right - btnW - 12 - pagerWidth, rect.y + 22);
  }

  if (!pageItems.length) {
    drawRoundedFill(ctx, cardsArea.x + 4, cardsArea.y + 8, cardsArea.w - 8, cardsArea.h - 16, 10, "rgba(255,255,255,0.35)");
    ctx.fillStyle = THEME.panelMuted;
    ctx.font = FONT.body;
    ctx.fillText("No pack files found in /packs", cardsArea.x + 16, cardsArea.y + cardsArea.h / 2);
    return;
  }

  const cardW = (cardsArea.w - gap * (cols + 1)) / cols;
  const cardH = (cardsArea.h - gap * (rows + 1)) / rows;

  for (let i = 0; i < pageItems.length; i++) {
    const pack = pageItems[i];
    const col = i % cols;
    const row = Math.floor(i / cols);
    const cardRect = {
      x: cardsArea.x + gap + col * (cardW + gap),
      y: cardsArea.y + gap + row * (cardH + gap),
      w: cardW,
      h: cardH,
      packId: pack.id,
    };
    state.hitboxes.cards.push(cardRect);

    const selected = state.selectedPackId === pack.id;
    const animT = selected ? clamp((Date.now() - state.selectionAnimStart) / 260, 0, 1) : 1;
    const glowAlpha = selected ? 0.35 * (1 - animT) + 0.15 : 0;
    if (selected && animT < 1) {
      queueRedraw(state);
    }

    if (selected) {
      ctx.save();
      ctx.shadowColor = `rgba(232,111,81,${glowAlpha.toFixed(3)})`;
      ctx.shadowBlur = 10 + 14 * (1 - animT);
      drawRoundedFill(ctx, cardRect.x, cardRect.y, cardRect.w, cardRect.h, 10, THEME.cardStart);
      ctx.restore();
    }

    drawRoundedGradient(ctx, cardRect, 10, THEME.cardStart, THEME.cardEnd, true);
    drawRoundedStroke(
      ctx,
      cardRect.x,
      cardRect.y,
      cardRect.w,
      cardRect.h,
      10,
      selected ? THEME.cardSelectedStroke : THEME.cardStroke,
      selected ? 2.2 : 1
    );

    const imageRect = {
      x: cardRect.x + 7,
      y: cardRect.y + 7,
      w: cardRect.w - 14,
      h: cardRect.h * 0.5,
    };
    drawRoundedFill(ctx, imageRect.x, imageRect.y, imageRect.w, imageRect.h, 7, THEME.previewBg);
    drawRoundedStroke(ctx, imageRect.x, imageRect.y, imageRect.w, imageRect.h, 7, THEME.previewStroke, 1);

    const imageEntry = state.packImages[pack.id];
    if (imageEntry?.loaded) {
      ctx.save();
      roundRectPath(ctx, imageRect.x, imageRect.y, imageRect.w, imageRect.h, 7);
      ctx.clip();
      drawImageCover(ctx, imageEntry.img, imageRect.x, imageRect.y, imageRect.w, imageRect.h);
      ctx.restore();
    } else {
      ctx.fillStyle = THEME.previewPlaceholder;
      ctx.font = FONT.tiny;
      ctx.fillText("preview", imageRect.x + 8, imageRect.y + imageRect.h / 2 + 4);
    }

    const titleY = imageRect.y + imageRect.h + 17;
    ctx.fillStyle = THEME.panelText;
    ctx.font = FONT.bodyBold;
    ctx.fillText(trimText(ctx, pack.name || pack.id, cardRect.w - 14), cardRect.x + 7, titleY);

    const meta = `${pack.default_count ?? 12} frames \u2022 ${(pack.ratios || []).join(" / ") || "Auto"}`;
    ctx.fillStyle = THEME.panelMuted;
    ctx.font = FONT.tiny;
    ctx.fillText(trimText(ctx, meta, cardRect.w - 14), cardRect.x + 7, titleY + 14);

    const tags = Array.isArray(pack.tags) ? pack.tags.slice(0, 2) : [];
    let tx = cardRect.x + 7;
    const ty = titleY + 24;
    ctx.font = FONT.tiny;
    for (const tag of tags) {
      const label = trimText(ctx, tag, 60);
      const tw = ctx.measureText(label).width + 10;
      if (tx + tw > cardRect.x + cardRect.w - 7) break;
      drawRoundedFill(ctx, tx, ty - 9, tw, 14, 7, THEME.chipBg);
      ctx.fillStyle = THEME.chipText;
      ctx.fillText(label, tx + 5, ty + 1);
      tx += tw + 4;
    }
  }
}

function drawPreviewStage(ctx, node, state, rect, selectedPack) {
  drawPanelBase(ctx, rect, 12);

  ctx.fillStyle = THEME.panelText;
  ctx.font = FONT.heading;
  const heading = selectedPack ? `Creative Stage \u2022 ${selectedPack.name}` : "Creative Stage";
  ctx.fillText(trimText(ctx, heading, rect.w - 24), rect.x + 12, rect.y + 22);

  const previewRect = {
    x: rect.x + 12,
    y: rect.y + 30,
    w: rect.w - 24,
    h: Math.floor(rect.h * 0.56),
  };

  const g = ctx.createLinearGradient(previewRect.x, previewRect.y, previewRect.x + previewRect.w, previewRect.y + previewRect.h);
  g.addColorStop(0, "#e0edf3");
  g.addColorStop(1, "#cedde4");
  drawRoundedFill(ctx, previewRect.x, previewRect.y, previewRect.w, previewRect.h, 10, g);
  drawRoundedStroke(ctx, previewRect.x, previewRect.y, previewRect.w, previewRect.h, 10, THEME.previewStroke, 1.2);

  if (state.inputImage?.loaded) {
    ctx.save();
    roundRectPath(ctx, previewRect.x, previewRect.y, previewRect.w, previewRect.h, 10);
    ctx.clip();
    drawImageContain(ctx, state.inputImage.img, previewRect.x, previewRect.y, previewRect.w, previewRect.h);
    ctx.restore();
  } else {
    ctx.fillStyle = THEME.previewPlaceholder;
    ctx.font = FONT.body;
    const placeholder = getImageLinked(node, "image")
      ? "Input linked. Queue once to capture a live preview."
      : "Connect IMAGE input to stage your source.";
    drawWrappedText(ctx, placeholder, previewRect.x + 14, previewRect.y + previewRect.h / 2 - 10, previewRect.w - 24, 16, 2);
  }

  const infoY = previewRect.y + previewRect.h + 16;
  const infoH = rect.y + rect.h - infoY - 10;
  const infoRect = { x: rect.x + 12, y: infoY, w: rect.w - 24, h: Math.max(44, infoH) };

  drawRoundedFill(ctx, infoRect.x, infoRect.y, infoRect.w, infoRect.h, 10, "rgba(255,255,255,0.45)");
  drawRoundedStroke(ctx, infoRect.x, infoRect.y, infoRect.w, infoRect.h, 10, "rgba(120,90,56,0.24)", 1);

  if (!selectedPack) {
    ctx.fillStyle = THEME.panelMuted;
    ctx.font = FONT.body;
    ctx.fillText("Select a pack to inspect details.", infoRect.x + 12, infoRect.y + 24);
    return;
  }

  const ratioText = Array.isArray(selectedPack.ratios) && selectedPack.ratios.length
    ? selectedPack.ratios.join(" / ")
    : "Auto";
  const exportType = String(selectedPack.export?.type || "mixed");
  const shotCount = Number(selectedPack.shot_count || 0);

  const metrics = [
    { label: "Shots", value: shotCount > 0 ? String(shotCount) : "-" },
    { label: "Ratios", value: ratioText },
    { label: "Export", value: exportType },
  ];

  const metricGap = 8;
  const metricW = (infoRect.w - metricGap * 4) / 3;
  let mx = infoRect.x + metricGap;
  const my = infoRect.y + 8;
  for (const metric of metrics) {
    drawRoundedFill(ctx, mx, my, metricW, 24, 7, "rgba(255,255,255,0.64)");
    ctx.fillStyle = THEME.panelMuted;
    ctx.font = FONT.tiny;
    ctx.fillText(metric.label, mx + 7, my + 10);
    ctx.fillStyle = THEME.panelText;
    ctx.font = FONT.label;
    ctx.fillText(trimText(ctx, metric.value, metricW - 14), mx + 7, my + 21);
    mx += metricW + metricGap;
  }

  ctx.fillStyle = THEME.panelMuted;
  ctx.font = FONT.tiny;
  drawWrappedText(
    ctx,
    selectedPack.description || "No pack description available.",
    infoRect.x + 10,
    infoRect.y + 42,
    infoRect.w - 20,
    13,
    2
  );
}

function drawControlsRow(ctx, node, state, rect, specs) {
  const present = specs.filter((spec) => !!getWidget(node, spec.key));
  if (!present.length) return;

  const gap = 8;
  const cellW = (rect.w - gap * (present.length - 1)) / present.length;
  let x = rect.x;

  for (const spec of present) {
    const control = { x, y: rect.y, w: cellW, h: rect.h };

    drawRoundedFill(ctx, control.x, control.y, control.w, control.h, 9, THEME.controlBg);
    drawRoundedStroke(ctx, control.x, control.y, control.w, control.h, 9, THEME.controlStroke, 1);

    ctx.fillStyle = THEME.panelMuted;
    ctx.font = FONT.tiny;
    ctx.fillText(spec.label, control.x + 8, control.y + 12);

    const widget = getWidget(node, spec.key);
    const value = String(widget?.value ?? "");

    if (spec.type === "count") {
      const btnW = 18;
      const btnH = 18;
      const minusRect = { x: control.x + 8, y: control.y + control.h - 24, w: btnW, h: btnH };
      const plusRect = { x: control.x + control.w - btnW - 8, y: control.y + control.h - 24, w: btnW, h: btnH };

      drawRoundedFill(ctx, minusRect.x, minusRect.y, minusRect.w, minusRect.h, 4, THEME.controlButtonBg);
      drawRoundedFill(ctx, plusRect.x, plusRect.y, plusRect.w, plusRect.h, 4, THEME.controlButtonBg);
      ctx.fillStyle = THEME.controlButtonText;
      ctx.font = FONT.bodyBold;
      ctx.fillText("-", minusRect.x + 7, minusRect.y + 13);
      ctx.fillText("+", plusRect.x + 6, plusRect.y + 13);

      ctx.fillStyle = THEME.controlValue;
      ctx.font = FONT.bodyBold;
      const v = trimText(ctx, value, control.w - 70);
      const tw = ctx.measureText(v).width;
      ctx.fillText(v, control.x + (control.w - tw) / 2, control.y + control.h - 11);

      state.hitboxes.controls.push({ kind: "count", minusRect, plusRect });
    } else {
      ctx.fillStyle = THEME.controlValue;
      ctx.font = FONT.bodyBold;
      ctx.fillText(trimText(ctx, value, control.w - 16), control.x + 8, control.y + control.h - 11);
      state.hitboxes.controls.push({ kind: "cycle", key: spec.key, rect: control });
    }

    x += cellW + gap;
  }
}

function drawStatusPanel(ctx, node, rect, selectedPack) {
  drawRoundedGradient(ctx, rect, 10, THEME.statusCardStart, THEME.statusCardEnd, true);
  drawRoundedStroke(ctx, rect.x, rect.y, rect.w, rect.h, 10, THEME.statusCardStroke, 1);

  ctx.fillStyle = THEME.panelText;
  ctx.font = FONT.heading;
  ctx.fillText("Readiness", rect.x + 10, rect.y + 20);

  const lines = getReadinessLines(node);
  let y = rect.y + 38;
  for (const line of lines.slice(0, 3)) {
    ctx.fillStyle = line.level === "ok" ? THEME.statusOk : THEME.statusWarn;
    ctx.font = FONT.tiny;
    drawWrappedText(ctx, line.text, rect.x + 10, y, rect.w - 20, 13, 2);
    y += 24;
  }

  ctx.fillStyle = THEME.panelMuted;
  ctx.font = FONT.tiny;
  ctx.fillText(`IMAGE: ${getImageLinked(node, "image") ? "connected" : "missing"}`, rect.x + 10, rect.y + rect.h - 32);
  ctx.fillText(`LOGO: ${getImageLinked(node, "brand_logo") ? "connected" : "missing"}`, rect.x + 10, rect.y + rect.h - 18);

  if (selectedPack) {
    ctx.fillStyle = THEME.panelText;
    ctx.font = FONT.tiny;
    ctx.fillText(trimText(ctx, `Pack: ${selectedPack.id}`, rect.w - 20), rect.x + 10, rect.y + rect.h - 4);
  }
}

function drawBottomDeck(ctx, node, state, rect, selectedPack) {
  state.hitboxes.controls = [];

  drawPanelBase(ctx, rect, 12);

  ctx.fillStyle = THEME.panelText;
  ctx.font = FONT.heading;
  ctx.fillText("Control Deck", rect.x + 12, rect.y + 22);

  const statusW = Math.min(230, Math.max(200, rect.w * 0.24));
  const statusRect = {
    x: rect.x + rect.w - statusW - 10,
    y: rect.y + 30,
    w: statusW,
    h: rect.h - 40,
  };

  const controlsArea = {
    x: rect.x + 10,
    y: rect.y + 30,
    w: rect.w - statusW - 24,
    h: rect.h - 40,
  };

  const rowGap = 8;
  const rowH = (controlsArea.h - rowGap) / 2;
  const row1 = { x: controlsArea.x, y: controlsArea.y, w: controlsArea.w, h: rowH };
  const row2 = { x: controlsArea.x, y: controlsArea.y + rowH + rowGap, w: controlsArea.w, h: rowH };

  const specRow1 = [
    { label: "Mode", key: "output_mode", type: "cycle" },
    { label: "Count", key: "count", type: "count" },
    { label: "Aspect", key: "aspect", type: "cycle" },
    { label: "Brand", key: "branding", type: "cycle" },
    { label: "Tone", key: "caption_tone", type: "cycle" },
  ];

  const specRow2 = [
    { label: "Platform", key: "platform", type: "cycle" },
    { label: "Objective", key: "objective", type: "cycle" },
    { label: "Hook", key: "hook_style", type: "cycle" },
    { label: "CTA", key: "cta_mode", type: "cycle" },
    { label: "Hashtags", key: "hashtag_mode", type: "cycle" },
  ];

  drawControlsRow(ctx, node, state, row1, specRow1);
  drawControlsRow(ctx, node, state, row2, specRow2);
  drawStatusPanel(ctx, node, statusRect, selectedPack);
}

function drawLoadingOverlay(ctx, rect) {
  drawRoundedFill(ctx, rect.x, rect.y, rect.w, rect.h, 12, "rgba(18,31,43,0.62)");
  ctx.fillStyle = "#f3ead8";
  ctx.font = FONT.heading;
  ctx.fillText("Loading packs...", rect.x + 14, rect.y + 26);
}

function drawSocialPackUI(node, ctx, state) {
  if (node.flags?.collapsed) return;

  setNodeMinSize(node);

  const packFromWidget = extractPackId(getWidget(node, "pack")?.value ?? "");
  if (packFromWidget && packFromWidget !== state.selectedPackId) {
    state.selectedPackId = packFromWidget;
  }

  const width = node.size[0];
  const height = node.size[1];
  const pad = UI.PAD;
  const safeX = pad;
  const safeY = pad + UI.SAFE_TOP;
  const safeW = Math.max(520, width - pad * 2);
  const safeH = Math.max(360, height - (pad * 2 + UI.SAFE_TOP + UI.SAFE_BOTTOM));

  const shellRect = { x: safeX, y: safeY, w: safeW, h: safeH };
  drawShellBackdrop(ctx, shellRect);

  const headerRect = { x: safeX + 8, y: safeY + 8, w: safeW - 16, h: UI.HEADER_H };
  const contentY = headerRect.y + headerRect.h + UI.GAP;
  const contentH = Math.max(180, safeH - UI.HEADER_H - UI.BOTTOM_H - UI.GAP * 3 - 16);

  const leftW = Math.max(260, Math.round((safeW - UI.GAP - 16) * UI.LEFT_RATIO));
  const rightW = Math.max(220, safeW - 16 - UI.GAP - leftW);
  const leftRect = { x: safeX + 8, y: contentY, w: leftW, h: contentH };
  const rightRect = { x: leftRect.x + leftW + UI.GAP, y: contentY, w: rightW, h: contentH };
  const bottomRect = {
    x: safeX + 8,
    y: contentY + contentH + UI.GAP,
    w: safeW - 16,
    h: UI.BOTTOM_H,
  };

  const selectedPack = getSelectedPack(state);

  drawHeader(ctx, node, state, headerRect, selectedPack);
  drawLibrary(ctx, state, leftRect);
  drawPreviewStage(ctx, node, state, rightRect, selectedPack);
  drawBottomDeck(ctx, node, state, bottomRect, selectedPack);

  if (state.loadingPacks) {
    drawLoadingOverlay(ctx, shellRect);
  }
}

function runHeaderAction(node, state, action) {
  if (action === "random") {
    chooseRandomPack(node, state);
    return;
  }
  if (action === "defaults") {
    applyPackDefaults(node, state);
    return;
  }
  if (action === "reload") {
    packsRequest = null;
    loadPacksForNode(node, state).catch((error) => {
      console.error("[mkrshift.socialpack] reload failed:", error);
    });
  }
}

function handleMouseDown(node, state, point, event) {
  if (!point) return false;

  for (const button of state.hitboxes.headerButtons) {
    if (pointInRect(point, button)) {
      runHeaderAction(node, state, button.action);
      markDirty(node);
      return true;
    }
  }

  if (state.hitboxes.prevPage && pointInRect(point, state.hitboxes.prevPage)) {
    state.page = Math.max(0, state.page - 1);
    markDirty(node);
    return true;
  }

  if (state.hitboxes.nextPage && pointInRect(point, state.hitboxes.nextPage)) {
    const totalPages = Math.max(1, Math.ceil(state.packs.length / state.cardsPerPage));
    state.page = Math.min(totalPages - 1, state.page + 1);
    markDirty(node);
    return true;
  }

  for (const card of state.hitboxes.cards) {
    if (pointInRect(point, card)) {
      syncPackSelection(node, state, card.packId);
      markDirty(node);
      return true;
    }
  }

  for (const option of state.hitboxes.controls) {
    if (option.kind === "cycle" && pointInRect(point, option.rect)) {
      cycleWidgetValue(node, option.key, 1);
      markDirty(node);
      return true;
    }

    if (option.kind === "count") {
      if (pointInRect(point, option.minusRect)) {
        adjustCount(node, -1);
        markDirty(node);
        return true;
      }
      if (pointInRect(point, option.plusRect)) {
        adjustCount(node, 1);
        markDirty(node);
        return true;
      }
    }
  }

  if (state.hitboxes.libraryPanel && pointInRect(point, state.hitboxes.libraryPanel)) {
    event?.stopPropagation?.();
    return false;
  }

  return false;
}

function handleMouseWheel(node, state, point, event) {
  if (!point || !state.hitboxes.libraryPanel || !pointInRect(point, state.hitboxes.libraryPanel)) {
    return false;
  }

  const totalPages = Math.max(1, Math.ceil(state.packs.length / state.cardsPerPage));
  if (totalPages <= 1) return false;

  const delta = Number(event?.deltaY ?? 0);
  if (delta === 0) return false;

  const nextPage = clamp(state.page + (delta > 0 ? 1 : -1), 0, totalPages - 1);
  if (nextPage !== state.page) {
    state.page = nextPage;
    markDirty(node);
  }

  event?.preventDefault?.();
  event?.stopPropagation?.();
  return true;
}

async function loadPacksForNode(node, state) {
  if (state.loadingPacks) return;
  state.loadingPacks = true;
  markDirty(node);

  const remotePacks = await fetchPacksFromBackend();
  state.packs = Array.isArray(remotePacks) && remotePacks.length ? remotePacks : fallbackPacksFromWidget(node);

  preloadPackImages(state);

  const selected = pickInitialPackId(node, state.packs);
  if (selected) {
    syncPackSelection(node, state, selected);
  }

  state.loadingPacks = false;
  markDirty(node);
}

async function initializeSocialPackNode(node) {
  const state = ensureNodeState(node);
  hideBuiltInWidgets(node);
  setNodeMinSize(node);
  attachHandlers(node, state);
  await loadPacksForNode(node, state);
}

function attachHandlers(node, state) {
  if (node.__mkrshiftSocialAttached) return;
  node.__mkrshiftSocialAttached = true;

  const originalDrawForeground = node.onDrawForeground;
  node.onDrawForeground = function onDrawForeground(ctx) {
    originalDrawForeground?.apply(this, arguments);
    drawSocialPackUI(this, ctx, state);
  };

  const originalMouseDown = node.onMouseDown;
  node.onMouseDown = function onMouseDown(event, pos) {
    const point = getLocalPos(this, event, pos);
    if (handleMouseDown(this, state, point, event)) {
      return true;
    }
    return originalMouseDown?.apply(this, arguments);
  };

  const originalMouseWheel = node.onMouseWheel;
  node.onMouseWheel = function onMouseWheel(event, pos) {
    const point = getLocalPos(this, event, pos);
    if (handleMouseWheel(this, state, point, event)) {
      return true;
    }
    return originalMouseWheel?.apply(this, arguments);
  };

  const originalExecuted = node.onExecuted;
  node.onExecuted = function onExecuted(message) {
    originalExecuted?.apply(this, arguments);
    const previewInfo = message?.input_preview?.[0] ?? message?.ui?.input_preview?.[0] ?? null;
    if (previewInfo) {
      loadInputPreviewImage(state, previewInfo);
      markDirty(this);
    }
  };

  const originalConfigure = node.onConfigure;
  node.onConfigure = function onConfigure(info) {
    originalConfigure?.apply(this, arguments);
    hideBuiltInWidgets(this);
    const selectedFromProperty = String(this.properties?.selected_pack_id ?? "").trim();
    if (selectedFromProperty) {
      syncPackSelection(this, state, selectedFromProperty);
    }
    markDirty(this);
  };

  const originalConnectionsChange = node.onConnectionsChange;
  node.onConnectionsChange = function onConnectionsChange() {
    const out = originalConnectionsChange?.apply(this, arguments);
    markDirty(this);
    return out;
  };
}

app.registerExtension({
  name: "mkrshift.socialpack",
  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (!isSocialPackNodeDef(nodeData)) return;

    const originalOnNodeCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function onNodeCreated() {
      originalOnNodeCreated?.apply(this, arguments);
      initializeSocialPackNode(this).catch((error) => {
        console.error("[mkrshift.socialpack] init failed in onNodeCreated:", error);
      });
    };
  },
  async nodeCreated(node) {
    if (!isSocialPackNode(node)) return;
    await initializeSocialPackNode(node);
  },
});
