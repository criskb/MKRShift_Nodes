import { app } from "../../../scripts/app.js";
import { createPanelShell } from "./uiSystem.js";
import {
  attachPanel,
  createGradeButton,
  createGradeMetric,
  createGradeReadout,
  createGradeSection,
  createGradeSlider,
  createGradeToggle,
  ensureCanvasResolution,
  ensureColorGradeStyles,
  formatNumber,
  formatSigned,
  getBoolean,
  getNumber,
  getValue,
  installBundledSettingsAdapter,
  normalizePanelNode,
  setWidgetValue,
} from "./colorStudioShared.js";

const EXTENSION_NAME = "MKRShift.GCodeStudios";
const SETTINGS_WIDGET_NAME = "settings_json";
const STYLE_ID = "mkr-gcode-studios-v1";

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function ensureLocalStyles() {
  ensureColorGradeStyles();
  if (document.getElementById(STYLE_ID)) return;
  const style = document.createElement("style");
  style.id = STYLE_ID;
  style.textContent = `
    .mkr-gcode-input,
    .mkr-gcode-select,
    .mkr-gcode-textarea {
      width: 100%;
      border-radius: 7px;
      border: 1px solid rgba(255,255,255,0.08);
      background: rgba(0,0,0,0.22);
      color: #eef2f6;
      padding: 7px 8px;
      font-size: 11px;
      box-sizing: border-box;
      font-family: inherit;
    }

    .mkr-gcode-select {
      margin-top: 4px;
    }

    .mkr-gcode-textarea {
      min-height: 78px;
      resize: vertical;
      margin-top: 4px;
      line-height: 1.35;
      white-space: pre;
    }

    .mkr-gcode-note {
      margin-top: 6px;
      font-size: 10px;
      line-height: 1.35;
      color: rgba(235,240,246,0.56);
    }
  `;
  document.head.appendChild(style);
}

function createTextControl({ label, value, multiline = false, placeholder = "", onChange }) {
  const root = document.createElement("div");
  root.className = "mkr-grade-control";
  const head = document.createElement("div");
  head.className = "mkr-grade-control-label";
  head.innerHTML = `<span>${label}</span><span class="mkr-grade-control-value">${String(value || "").trim() ? "set" : "empty"}</span>`;

  const input = multiline ? document.createElement("textarea") : document.createElement("input");
  input.className = multiline ? "mkr-gcode-textarea" : "mkr-gcode-input";
  if (!multiline) input.type = "text";
  input.value = String(value ?? "");
  input.placeholder = placeholder;
  input.addEventListener("change", () => {
    head.lastChild.textContent = String(input.value || "").trim() ? "set" : "empty";
    onChange?.(input.value);
  });

  root.appendChild(head);
  root.appendChild(input);
  return {
    element: root,
    setValue(next) {
      input.value = String(next ?? "");
      head.lastChild.textContent = String(input.value || "").trim() ? "set" : "empty";
    },
  };
}

function createSelectControl({ label, value, options, onChange }) {
  const root = document.createElement("div");
  root.className = "mkr-grade-control";
  const head = document.createElement("div");
  head.className = "mkr-grade-control-label";
  head.innerHTML = `<span>${label}</span><span class="mkr-grade-control-value">${String(value)}</span>`;

  const select = document.createElement("select");
  select.className = "mkr-gcode-select";
  for (const option of options) {
    const node = document.createElement("option");
    node.value = String(option.value);
    node.textContent = option.label;
    select.appendChild(node);
  }
  select.value = String(value);
  select.addEventListener("change", () => {
    head.lastChild.textContent = String(select.value);
    onChange?.(select.value);
  });

  root.appendChild(head);
  root.appendChild(select);
  return {
    element: root,
    setValue(next) {
      select.value = String(next);
      head.lastChild.textContent = String(next);
    },
  };
}

function addHelp(section, text) {
  if (!text) return;
  const note = document.createElement("div");
  note.className = "mkr-gcode-note";
  note.textContent = text;
  section.body.appendChild(note);
}

function applyValues(node, values) {
  for (const [key, value] of Object.entries(values || {})) {
    setWidgetValue(node, key, value);
  }
}

function installRefreshHooks(node, key, refresh) {
  if (!node || node[key]) return;
  node[key] = true;

  const originalConfigure = node.onConfigure;
  node.onConfigure = function onConfigureRefreshPanel() {
    const result = originalConfigure?.apply(this, arguments);
    refresh();
    return result;
  };

  const originalResize = node.onResize;
  node.onResize = function onResizeRefreshPanel() {
    const result = originalResize?.apply(this, arguments);
    refresh();
    return result;
  };

  const originalExecuted = node.onExecuted;
  node.onExecuted = function onExecutedRefreshPanel() {
    const result = originalExecuted?.apply(this, arguments);
    refresh();
    return result;
  };
}

function drawFrame(ctx, width, height, accent = "rgba(255,255,255,0.14)") {
  ctx.clearRect(0, 0, width, height);
  const frame = { x: 18, y: 18, w: width - 36, h: height - 36 };
  const bg = ctx.createLinearGradient(frame.x, frame.y, frame.x, frame.y + frame.h);
  bg.addColorStop(0, "rgba(15,18,23,0.98)");
  bg.addColorStop(1, "rgba(24,28,34,0.98)");
  ctx.fillStyle = bg;
  ctx.fillRect(frame.x, frame.y, frame.w, frame.h);

  ctx.strokeStyle = "rgba(255,255,255,0.08)";
  ctx.lineWidth = 1;
  for (let i = 0; i <= 5; i += 1) {
    const x = frame.x + ((frame.w * i) / 5);
    const y = frame.y + ((frame.h * i) / 5);
    ctx.beginPath();
    ctx.moveTo(x, frame.y);
    ctx.lineTo(x, frame.y + frame.h);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(frame.x, y);
    ctx.lineTo(frame.x + frame.w, y);
    ctx.stroke();
  }
  ctx.strokeStyle = accent;
  ctx.strokeRect(frame.x, frame.y, frame.w, frame.h);
  return frame;
}

function drawPrinterProfileGraph(ctx, width, height, node) {
  const frame = drawFrame(ctx, width, height, "rgba(110, 214, 255, 0.18)");
  const bedW = getNumber(node, "bed_width_mm", 220);
  const bedD = getNumber(node, "bed_depth_mm", 220);
  const nozzle = getNumber(node, "nozzle_diameter_mm", 0.4);
  const line = getNumber(node, "line_width_mm", 0.45);
  const offsetX = getNumber(node, "offset_x_mm", 0.0);
  const offsetY = getNumber(node, "offset_y_mm", 0.0);
  const origin = String(getValue(node, "origin", "center"));

  const maxDim = Math.max(bedW, bedD, 1);
  const plateW = frame.w * (bedW / maxDim) * 0.86;
  const plateH = frame.h * (bedD / maxDim) * 0.86;
  const x = frame.x + (frame.w - plateW) * 0.5;
  const y = frame.y + (frame.h - plateH) * 0.5;
  ctx.fillStyle = "rgba(46,56,64,0.92)";
  ctx.fillRect(x, y, plateW, plateH);
  ctx.strokeStyle = "rgba(185,205,220,0.18)";
  ctx.strokeRect(x, y, plateW, plateH);

  const ox = origin === "center" ? x + plateW * 0.5 : x;
  const oy = origin === "center" ? y + plateH * 0.5 : y + plateH;
  ctx.strokeStyle = "rgba(110,214,255,0.65)";
  ctx.beginPath();
  ctx.moveTo(ox - 18, oy);
  ctx.lineTo(ox + 18, oy);
  ctx.moveTo(ox, oy - 18);
  ctx.lineTo(ox, oy + 18);
  ctx.stroke();

  const nx = ox + (offsetX / maxDim) * plateW;
  const ny = oy - (offsetY / maxDim) * plateH;
  ctx.fillStyle = "rgba(255,206,94,0.95)";
  ctx.beginPath();
  ctx.arc(nx, ny, clamp(4 + line * 5, 4, 9), 0, Math.PI * 2);
  ctx.fill();
  ctx.strokeStyle = "rgba(255,255,255,0.28)";
  ctx.beginPath();
  ctx.arc(nx, ny, clamp(6 + nozzle * 6, 6, 12), 0, Math.PI * 2);
  ctx.stroke();
}

function drawMeshLoadGraph(ctx, width, height, node) {
  const frame = drawFrame(ctx, width, height, "rgba(127, 245, 214, 0.16)");
  const rx = (getNumber(node, "rotate_x_deg", 0) * Math.PI) / 180;
  const ry = (getNumber(node, "rotate_y_deg", 0) * Math.PI) / 180;
  const rz = (getNumber(node, "rotate_z_deg", 0) * Math.PI) / 180;
  const scale = getNumber(node, "scale", 1.0);
  const fit = getNumber(node, "target_longest_mm", 0.0);
  const cx = frame.x + frame.w * 0.5;
  const cy = frame.y + frame.h * 0.52;
  const size = Math.min(frame.w, frame.h) * 0.22 * clamp(scale, 0.5, 1.8);
  const points = [
    [-1, -1, -1], [1, -1, -1], [1, 1, -1], [-1, 1, -1],
    [-1, -1, 1], [1, -1, 1], [1, 1, 1], [-1, 1, 1],
  ].map(([x, y, z]) => {
    let nx = x;
    let ny = y * Math.cos(rx) - z * Math.sin(rx);
    let nz = y * Math.sin(rx) + z * Math.cos(rx);
    const tx = nx * Math.cos(ry) + nz * Math.sin(ry);
    const tz = -nx * Math.sin(ry) + nz * Math.cos(ry);
    nx = tx;
    nz = tz;
    const qx = nx * Math.cos(rz) - ny * Math.sin(rz);
    const qy = nx * Math.sin(rz) + ny * Math.cos(rz);
    return [cx + qx * size, cy + (qy * size * 0.7) - (nz * size * 0.35)];
  });
  const edges = [[0,1],[1,2],[2,3],[3,0],[4,5],[5,6],[6,7],[7,4],[0,4],[1,5],[2,6],[3,7]];
  ctx.strokeStyle = "rgba(127,245,214,0.76)";
  ctx.lineWidth = 1.6;
  for (const [a, b] of edges) {
    ctx.beginPath();
    ctx.moveTo(points[a][0], points[a][1]);
    ctx.lineTo(points[b][0], points[b][1]);
    ctx.stroke();
  }
  if (fit > 0.01) {
    ctx.fillStyle = "rgba(255,214,117,0.86)";
    ctx.fillText(`fit ${formatNumber(fit, 0)} mm`, frame.x + 12, frame.y + 18);
  }
}

function drawHeightmapGraph(ctx, width, height, node) {
  const frame = drawFrame(ctx, width, height, "rgba(255,171,96,0.18)");
  const relief = getNumber(node, "relief_height_mm", 1.6);
  const gamma = getNumber(node, "height_gamma", 1.0);
  const blur = getNumber(node, "blur_radius_px", 0.0);
  const invert = getBoolean(node, "invert_heightmap", false);
  const bars = 24;
  for (let i = 0; i < bars; i += 1) {
    const u = i / (bars - 1);
    let v = invert ? 1 - u : u;
    v = Math.pow(v, gamma);
    const h = frame.h * (0.16 + v * 0.72);
    const x = frame.x + (frame.w * i) / bars;
    const w = frame.w / bars - 2;
    const grad = ctx.createLinearGradient(x, frame.y + frame.h - h, x, frame.y + frame.h);
    grad.addColorStop(0, "rgba(255,190,120,0.92)");
    grad.addColorStop(1, "rgba(255,106,74,0.24)");
    ctx.fillStyle = grad;
    ctx.fillRect(x, frame.y + frame.h - h, w, h);
  }
  ctx.fillStyle = "rgba(255,255,255,0.78)";
  ctx.fillText(`relief ${formatNumber(relief, 2)} mm`, frame.x + 12, frame.y + 18);
  if (blur > 0.001) ctx.fillText(`blur ${formatNumber(blur, 1)} px`, frame.x + 12, frame.y + 34);
}

function drawVaseGraph(ctx, width, height, node) {
  const frame = drawFrame(ctx, width, height, "rgba(186,141,255,0.18)");
  const baseR = getNumber(node, "base_radius_mm", 28);
  const topR = getNumber(node, "top_radius_mm", 24);
  const amp = getNumber(node, "wave_amplitude_mm", 0.0);
  const freq = getNumber(node, "wave_frequency", 0.0);
  const ovality = getNumber(node, "ovality", 0.0);
  const twist = getNumber(node, "twist_deg", 0.0);
  const phase = (getNumber(node, "phase_deg", 0.0) * Math.PI) / 180;
  const cx = frame.x + frame.w * 0.5;
  const yBottom = frame.y + frame.h * 0.88;
  const yTop = frame.y + frame.h * 0.12;

  ctx.beginPath();
  for (let i = 0; i <= 80; i += 1) {
    const u = i / 80;
    const y = yBottom - (u * (yBottom - yTop));
    let r = (1 - u) * baseR + u * topR;
    if (amp > 0.001 && freq > 0.001) {
      r += amp * Math.sin(u * freq * Math.PI * 2 + phase + twist * 0.02);
    }
    const rx = r * (1 + ovality * 0.45);
    const x = cx - rx * 2.1;
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  }
  for (let i = 80; i >= 0; i -= 1) {
    const u = i / 80;
    const y = yBottom - (u * (yBottom - yTop));
    let r = (1 - u) * baseR + u * topR;
    if (amp > 0.001 && freq > 0.001) {
      r += amp * Math.sin(u * freq * Math.PI * 2 + phase + twist * 0.02);
    }
    const rx = r * (1 + ovality * 0.45);
    ctx.lineTo(cx + rx * 2.1, y);
  }
  ctx.closePath();
  const fill = ctx.createLinearGradient(0, yTop, 0, yBottom);
  fill.addColorStop(0, "rgba(206,164,255,0.68)");
  fill.addColorStop(1, "rgba(122,91,235,0.24)");
  ctx.fillStyle = fill;
  ctx.fill();
  ctx.strokeStyle = "rgba(255,255,255,0.28)";
  ctx.stroke();
}

function drawPreviewGraph(ctx, width, height, node) {
  const frame = drawFrame(ctx, width, height, "rgba(122,198,255,0.16)");
  const mode = String(getValue(node, "view_mode", "auto"));
  const hasPath = String(getValue(node, "gcode_path", "") || "").trim().length > 0;
  const hasText = String(getValue(node, "gcode_text", "") || "").trim().length > 0;

  const leftW = frame.w * (mode === "split" ? 0.48 : 0.72);
  const panelX = frame.x + (frame.w - leftW) * 0.5;
  ctx.fillStyle = "rgba(64,82,102,0.55)";
  ctx.fillRect(panelX, frame.y + 18, leftW, frame.h - 36);
  ctx.strokeStyle = "rgba(255,255,255,0.14)";
  ctx.strokeRect(panelX, frame.y + 18, leftW, frame.h - 36);
  if (mode === "split") {
    ctx.strokeStyle = "rgba(255,255,255,0.12)";
    ctx.beginPath();
    ctx.moveTo(frame.x + frame.w * 0.5, frame.y + 18);
    ctx.lineTo(frame.x + frame.w * 0.5, frame.y + frame.h - 18);
    ctx.stroke();
  }
  ctx.fillStyle = "rgba(255,255,255,0.78)";
  ctx.fillText(hasPath ? "path linked" : hasText ? "text loaded" : "plan / mesh inputs", frame.x + 12, frame.y + 18);
}

function drawAnalyzerGraph(ctx, width, height, node) {
  const frame = drawFrame(ctx, width, height, "rgba(255,122,122,0.16)");
  const bars = [
    { label: "flow", value: getNumber(node, "max_volumetric_flow_mm3_s", 12), max: 40, color: "rgba(255,142,112,0.86)" },
    { label: "travel", value: getNumber(node, "warn_travel_ratio_percent", 35), max: 100, color: "rgba(255,205,99,0.86)" },
    { label: "bed", value: getNumber(node, "warn_bed_usage_percent", 75), max: 100, color: "rgba(114,211,255,0.86)" },
    { label: "cost", value: getNumber(node, "warn_total_cost", 12), max: 40, color: "rgba(180,148,255,0.86)" },
  ];
  const barW = frame.w / bars.length * 0.52;
  bars.forEach((bar, index) => {
    const x = frame.x + 22 + index * (frame.w / bars.length);
    const h = frame.h * clamp(bar.value / bar.max, 0.08, 1.0) * 0.78;
    ctx.fillStyle = "rgba(255,255,255,0.06)";
    ctx.fillRect(x, frame.y + 28, barW, frame.h - 48);
    ctx.fillStyle = bar.color;
    ctx.fillRect(x, frame.y + frame.h - 20 - h, barW, h);
    ctx.fillStyle = "rgba(255,255,255,0.78)";
    ctx.fillText(bar.label, x, frame.y + frame.h - 6);
  });
}

const CONFIGS = {
  MKRGCodePrinterProfile: {
    panelName: "mkr_gcode_printer_profile_studio",
    size: [820, 1080],
    accent: "#6ed6ff",
    title: "Printer Profile Studio",
    subtitle: "Shape the machine envelope, extrusion defaults, offsets, and boot/shutdown scripts from one guided printer panel.",
    defaults: {
      printer_name: "Generic FDM",
      bed_width_mm: 220.0,
      bed_depth_mm: 220.0,
      bed_height_mm: 250.0,
      origin: "center",
      offset_x_mm: 0.0,
      offset_y_mm: 0.0,
      nozzle_diameter_mm: 0.4,
      line_width_mm: 0.45,
      layer_height_mm: 0.2,
      filament_diameter_mm: 1.75,
      extrusion_multiplier: 1.0,
      nozzle_temp_c: 210,
      bed_temp_c: 60,
      print_speed_mm_s: 30.0,
      travel_speed_mm_s: 100.0,
      retraction_mm: 0.8,
      retraction_speed_mm_s: 35.0,
      travel_z_mm: 0.6,
      home_before_print: true,
      prime_line: true,
      start_gcode: "M104 S210\nM140 S60\nG28\nG92 E0",
      end_gcode: "M104 S0\nM140 S0\nG28 X0\nM84",
    },
    numericSpecs: {
      bed_width_mm: { min: 50, max: 1000 },
      bed_depth_mm: { min: 50, max: 1000 },
      bed_height_mm: { min: 50, max: 1500 },
      offset_x_mm: { min: -1000, max: 1000 },
      offset_y_mm: { min: -1000, max: 1000 },
      nozzle_diameter_mm: { min: 0.1, max: 2 },
      line_width_mm: { min: 0.1, max: 2.4 },
      layer_height_mm: { min: 0.05, max: 1.0 },
      filament_diameter_mm: { min: 1.0, max: 3.0 },
      extrusion_multiplier: { min: 0.1, max: 3.0 },
      nozzle_temp_c: { min: 0, max: 400, integer: true },
      bed_temp_c: { min: 0, max: 150, integer: true },
      print_speed_mm_s: { min: 1, max: 400 },
      travel_speed_mm_s: { min: 1, max: 500 },
      retraction_mm: { min: 0, max: 20 },
      retraction_speed_mm_s: { min: 1, max: 200 },
      travel_z_mm: { min: 0.1, max: 10 },
    },
    booleanKeys: ["home_before_print", "prime_line"],
    legacyNames: [
      "printer_name","bed_width_mm","bed_depth_mm","bed_height_mm","origin","nozzle_diameter_mm","line_width_mm","layer_height_mm",
      "offset_x_mm","offset_y_mm","filament_diameter_mm","extrusion_multiplier","nozzle_temp_c","bed_temp_c","print_speed_mm_s","travel_speed_mm_s","retraction_mm",
      "retraction_speed_mm_s","travel_z_mm","home_before_print","prime_line","start_gcode","end_gcode",
    ],
    metrics: [
      { label: "Bed", get: (node) => `${formatNumber(getNumber(node, "bed_width_mm", 220), 0)} x ${formatNumber(getNumber(node, "bed_depth_mm", 220), 0)}` },
      { label: "Nozzle", get: (node) => `${formatNumber(getNumber(node, "nozzle_diameter_mm", 0.4), 2)} mm` },
      { label: "Layer", get: (node) => `${formatNumber(getNumber(node, "layer_height_mm", 0.2), 2)} mm` },
    ],
    presets: [
      { label: "Compact", values: { printer_name: "Compact FDM", bed_width_mm: 180, bed_depth_mm: 180, bed_height_mm: 180, nozzle_diameter_mm: 0.4, print_speed_mm_s: 28, travel_speed_mm_s: 90 } },
      { label: "Bedslinger", tone: "accent", values: { printer_name: "Bedslinger", bed_width_mm: 220, bed_depth_mm: 220, bed_height_mm: 250, nozzle_diameter_mm: 0.4, line_width_mm: 0.45, print_speed_mm_s: 35, travel_speed_mm_s: 120 } },
      { label: "CoreXY", values: { printer_name: "CoreXY", bed_width_mm: 300, bed_depth_mm: 300, bed_height_mm: 300, nozzle_diameter_mm: 0.4, line_width_mm: 0.48, print_speed_mm_s: 80, travel_speed_mm_s: 220, retraction_mm: 0.6 } },
    ],
    graph: {
      title: "Bed Envelope",
      note: "machine frame",
      height: 220,
      draw: drawPrinterProfileGraph,
      readouts: [
        { label: "Origin", get: (node) => String(getValue(node, "origin", "center")) },
        { label: "Offset X", get: (node) => formatSigned(getNumber(node, "offset_x_mm", 0), 1) },
        { label: "Offset Y", get: (node) => formatSigned(getNumber(node, "offset_y_mm", 0), 1) },
      ],
      help: "The preview shows the printable footprint, selected origin, and the current XY offset anchor.",
    },
    sections: [
      { title: "Machine", note: "envelope", controls: [
        { type: "text", key: "printer_name", label: "Printer Name" },
        { type: "select", key: "origin", label: "Origin", options: [{ label: "center", value: "center" }, { label: "lower_left", value: "lower_left" }] },
        { type: "slider", key: "bed_width_mm", label: "Bed Width", min: 50, max: 1000, step: 1, decimals: 0 },
        { type: "slider", key: "bed_depth_mm", label: "Bed Depth", min: 50, max: 1000, step: 1, decimals: 0 },
        { type: "slider", key: "bed_height_mm", label: "Bed Height", min: 50, max: 1500, step: 1, decimals: 0 },
        { type: "slider", key: "offset_x_mm", label: "Offset X", min: -1000, max: 1000, step: 0.1, decimals: 1 },
        { type: "slider", key: "offset_y_mm", label: "Offset Y", min: -1000, max: 1000, step: 0.1, decimals: 1 },
      ]},
      { title: "Extrusion Core", note: "toolhead", controls: [
        { type: "slider", key: "nozzle_diameter_mm", label: "Nozzle", min: 0.1, max: 2.0, step: 0.01, decimals: 2 },
        { type: "slider", key: "line_width_mm", label: "Line Width", min: 0.1, max: 2.4, step: 0.01, decimals: 2 },
        { type: "slider", key: "layer_height_mm", label: "Layer Height", min: 0.05, max: 1.0, step: 0.01, decimals: 2 },
        { type: "slider", key: "filament_diameter_mm", label: "Filament", min: 1.0, max: 3.0, step: 0.01, decimals: 2 },
        { type: "slider", key: "extrusion_multiplier", label: "Extrusion", min: 0.1, max: 3.0, step: 0.01, decimals: 2 },
      ]},
      { title: "Motion + Thermal", note: "defaults", controls: [
        { type: "slider", key: "nozzle_temp_c", label: "Nozzle Temp", min: 0, max: 400, step: 1, decimals: 0 },
        { type: "slider", key: "bed_temp_c", label: "Bed Temp", min: 0, max: 150, step: 1, decimals: 0 },
        { type: "slider", key: "print_speed_mm_s", label: "Print Speed", min: 1, max: 400, step: 0.5, decimals: 1 },
        { type: "slider", key: "travel_speed_mm_s", label: "Travel Speed", min: 1, max: 500, step: 0.5, decimals: 1 },
        { type: "slider", key: "retraction_mm", label: "Retraction", min: 0, max: 20, step: 0.1, decimals: 1 },
        { type: "slider", key: "retraction_speed_mm_s", label: "Retract Speed", min: 1, max: 200, step: 0.5, decimals: 1 },
        { type: "slider", key: "travel_z_mm", label: "Travel Z", min: 0.1, max: 10, step: 0.05, decimals: 2 },
        { type: "toggle", key: "home_before_print", label: "Home Before Print", description: "Insert a homing phase before the toolpath starts." },
        { type: "toggle", key: "prime_line", label: "Prime Line", description: "Emit a prime line during the start procedure." },
      ]},
      { title: "Machine Scripts", note: "boot + shutdown", controls: [
        { type: "textarea", key: "start_gcode", label: "Start G-code" },
        { type: "textarea", key: "end_gcode", label: "End G-code" },
      ]},
    ],
  },
  MKRGCodeLoadMeshModel: {
    panelName: "mkr_gcode_load_mesh_studio",
    size: [800, 900],
    accent: "#7ff5d6",
    title: "Mesh Load Studio",
    subtitle: "Import and stage a printable model with transform, auto-fit sizing, and preview framing in one node.",
    defaults: {
      model_path: "",
      center_xy: true,
      bed_align: true,
      scale: 1.0,
      target_longest_mm: 0.0,
      rotate_x_deg: 0.0,
      rotate_y_deg: 0.0,
      rotate_z_deg: 0.0,
      translate_x_mm: 0.0,
      translate_y_mm: 0.0,
      translate_z_mm: 0.0,
      preview_view: "isometric",
      preview_size: 768,
    },
    numericSpecs: {
      scale: { min: 0.001, max: 1000.0 },
      target_longest_mm: { min: 0.0, max: 4000.0 },
      rotate_x_deg: { min: -360, max: 360 },
      rotate_y_deg: { min: -360, max: 360 },
      rotate_z_deg: { min: -360, max: 360 },
      translate_x_mm: { min: -1000, max: 1000 },
      translate_y_mm: { min: -1000, max: 1000 },
      translate_z_mm: { min: -1000, max: 1000 },
      preview_size: { min: 128, max: 2048, integer: true },
    },
    booleanKeys: ["center_xy", "bed_align"],
    legacyNames: ["model_path","center_xy","bed_align","scale","target_longest_mm","rotate_x_deg","rotate_y_deg","rotate_z_deg","translate_x_mm","translate_y_mm","translate_z_mm","preview_view","preview_size"],
    metrics: [
      { label: "Scale", get: (node) => formatNumber(getNumber(node, "scale", 1.0), 2) },
      { label: "Auto Fit", get: (node) => getNumber(node, "target_longest_mm", 0) > 0 ? `${formatNumber(getNumber(node, "target_longest_mm", 0), 0)} mm` : "off" },
      { label: "View", get: (node) => String(getValue(node, "preview_view", "isometric")) },
    ],
    presets: [
      { label: "Stage", tone: "accent", values: { center_xy: true, bed_align: true, scale: 1.0, rotate_x_deg: 0, rotate_y_deg: 0, rotate_z_deg: 0, target_longest_mm: 0 } },
      { label: "Top Prep", values: { center_xy: true, bed_align: true, rotate_x_deg: 90, rotate_y_deg: 0, rotate_z_deg: 0, preview_view: "top" } },
      { label: "Fit 180", values: { center_xy: true, bed_align: true, target_longest_mm: 180, preview_view: "isometric" } },
    ],
    graph: {
      title: "Transform Preview",
      note: "staging box",
      height: 220,
      draw: drawMeshLoadGraph,
      readouts: [
        { label: "RX", get: (node) => formatSigned(getNumber(node, "rotate_x_deg", 0), 1) },
        { label: "RY", get: (node) => formatSigned(getNumber(node, "rotate_y_deg", 0), 1) },
        { label: "RZ", get: (node) => formatSigned(getNumber(node, "rotate_z_deg", 0), 1) },
      ],
      help: "The box preview tracks rotation, scale, and auto-fit state so the mesh stage feels deliberate before slicing.",
    },
    sections: [
      { title: "Source", note: "mesh file", controls: [
        { type: "text", key: "model_path", label: "Model Path" },
        { type: "toggle", key: "center_xy", label: "Center XY", description: "Center the mesh over the XY origin before further transforms." },
        { type: "toggle", key: "bed_align", label: "Bed Align", description: "Drop the mesh so its minimum Z sits on the bed plane." },
      ]},
      { title: "Transform", note: "size + rotate", controls: [
        { type: "slider", key: "scale", label: "Scale", min: 0.001, max: 1000, step: 0.01, decimals: 2 },
        { type: "slider", key: "target_longest_mm", label: "Auto Fit", min: 0, max: 4000, step: 1, decimals: 0 },
        { type: "slider", key: "rotate_x_deg", label: "Rotate X", min: -360, max: 360, step: 1, decimals: 0 },
        { type: "slider", key: "rotate_y_deg", label: "Rotate Y", min: -360, max: 360, step: 1, decimals: 0 },
        { type: "slider", key: "rotate_z_deg", label: "Rotate Z", min: -360, max: 360, step: 1, decimals: 0 },
      ]},
      { title: "Placement", note: "offset", controls: [
        { type: "slider", key: "translate_x_mm", label: "Move X", min: -1000, max: 1000, step: 0.1, decimals: 1 },
        { type: "slider", key: "translate_y_mm", label: "Move Y", min: -1000, max: 1000, step: 0.1, decimals: 1 },
        { type: "slider", key: "translate_z_mm", label: "Move Z", min: -1000, max: 1000, step: 0.1, decimals: 1 },
        { type: "select", key: "preview_view", label: "Preview View", options: [{ label: "isometric", value: "isometric" }, { label: "top", value: "top" }] },
        { type: "slider", key: "preview_size", label: "Preview Size", min: 128, max: 2048, step: 16, decimals: 0 },
      ]},
    ],
  },
  MKRGCodeHeightmapPlate: {
    panelName: "mkr_gcode_heightmap_studio",
    size: [810, 920],
    accent: "#ffab60",
    title: "Heightmap Plate Studio",
    subtitle: "Turn an image into a relief plate with scan strategy, smoothing, gamma shaping, and profile-aware motion defaults.",
    defaults: {
      width_mm: 80.0,
      height_mm: 80.0,
      base_layers: 3,
      relief_height_mm: 1.6,
      layer_height_mm: 0.2,
      line_width_mm: 0.45,
      fill_mode: "alternate_xy",
      invert_heightmap: false,
      mirror_x: false,
      mirror_y: false,
      blur_radius_px: 0.0,
      height_gamma: 1.0,
      print_speed_mm_s: 28.0,
      travel_speed_mm_s: 120.0,
      use_profile_defaults: false,
    },
    numericSpecs: {
      width_mm: { min: 10, max: 400 },
      height_mm: { min: 10, max: 400 },
      base_layers: { min: 1, max: 40, integer: true },
      relief_height_mm: { min: 0.1, max: 20 },
      layer_height_mm: { min: 0.05, max: 1.0 },
      line_width_mm: { min: 0.1, max: 2.0 },
      blur_radius_px: { min: 0.0, max: 32.0 },
      height_gamma: { min: 0.1, max: 4.0 },
      print_speed_mm_s: { min: 1, max: 300 },
      travel_speed_mm_s: { min: 1, max: 500 },
    },
    booleanKeys: ["invert_heightmap","mirror_x","mirror_y","use_profile_defaults"],
    legacyNames: ["width_mm","height_mm","base_layers","relief_height_mm","layer_height_mm","line_width_mm","fill_mode","invert_heightmap","mirror_x","mirror_y","blur_radius_px","height_gamma","print_speed_mm_s","travel_speed_mm_s","use_profile_defaults"],
    metrics: [
      { label: "Size", get: (node) => `${formatNumber(getNumber(node, "width_mm", 80), 0)} x ${formatNumber(getNumber(node, "height_mm", 80), 0)}` },
      { label: "Relief", get: (node) => `${formatNumber(getNumber(node, "relief_height_mm", 1.6), 2)} mm` },
      { label: "Fill", get: (node) => String(getValue(node, "fill_mode", "alternate_xy")) },
    ],
    presets: [
      { label: "Relief", tone: "accent", values: { width_mm: 80, height_mm: 80, base_layers: 3, relief_height_mm: 1.6, fill_mode: "alternate_xy", blur_radius_px: 0.0, height_gamma: 1.0 } },
      { label: "Litho", values: { width_mm: 100, height_mm: 140, base_layers: 4, relief_height_mm: 2.4, fill_mode: "x_only", blur_radius_px: 1.2, height_gamma: 1.5, invert_heightmap: true } },
      { label: "Fast Plate", values: { width_mm: 70, height_mm: 70, base_layers: 2, relief_height_mm: 1.0, line_width_mm: 0.55, layer_height_mm: 0.24, fill_mode: "y_only", blur_radius_px: 0.8 } },
    ],
    graph: {
      title: "Height Response",
      note: "image to relief",
      height: 220,
      draw: drawHeightmapGraph,
      readouts: [
        { label: "Gamma", get: (node) => formatNumber(getNumber(node, "height_gamma", 1.0), 2) },
        { label: "Blur", get: (node) => formatNumber(getNumber(node, "blur_radius_px", 0.0), 1) },
        { label: "Base", get: (node) => String(Math.round(getNumber(node, "base_layers", 3))) },
      ],
      help: "The bars illustrate the tonal response after invert, gamma shaping, and smoothing, so the relief shape is easier to predict.",
    },
    sections: [
      { title: "Plate Size", note: "footprint", controls: [
        { type: "slider", key: "width_mm", label: "Width", min: 10, max: 400, step: 1, decimals: 0 },
        { type: "slider", key: "height_mm", label: "Height", min: 10, max: 400, step: 1, decimals: 0 },
        { type: "slider", key: "base_layers", label: "Base Layers", min: 1, max: 40, step: 1, decimals: 0 },
        { type: "slider", key: "relief_height_mm", label: "Relief Height", min: 0.1, max: 20, step: 0.05, decimals: 2 },
      ]},
      { title: "Image Response", note: "shape", controls: [
        { type: "select", key: "fill_mode", label: "Fill Mode", options: [{ label: "alternate_xy", value: "alternate_xy" }, { label: "x_only", value: "x_only" }, { label: "y_only", value: "y_only" }] },
        { type: "slider", key: "blur_radius_px", label: "Smoothing", min: 0, max: 32, step: 0.1, decimals: 1 },
        { type: "slider", key: "height_gamma", label: "Height Gamma", min: 0.1, max: 4, step: 0.01, decimals: 2 },
        { type: "toggle", key: "invert_heightmap", label: "Invert Heightmap", description: "Swap dark and bright height interpretation before relief generation." },
        { type: "toggle", key: "mirror_x", label: "Mirror X", description: "Flip the sampled heightmap horizontally." },
        { type: "toggle", key: "mirror_y", label: "Mirror Y", description: "Flip the sampled heightmap vertically." },
      ]},
      { title: "Motion Defaults", note: "print", controls: [
        { type: "slider", key: "layer_height_mm", label: "Layer Height", min: 0.05, max: 1.0, step: 0.01, decimals: 2 },
        { type: "slider", key: "line_width_mm", label: "Line Width", min: 0.1, max: 2.0, step: 0.01, decimals: 2 },
        { type: "slider", key: "print_speed_mm_s", label: "Print Speed", min: 1, max: 300, step: 0.5, decimals: 1 },
        { type: "slider", key: "travel_speed_mm_s", label: "Travel Speed", min: 1, max: 500, step: 0.5, decimals: 1 },
        { type: "toggle", key: "use_profile_defaults", label: "Use Profile Defaults", description: "Prefer line height, width, and speeds from the connected printer profile." },
      ]},
    ],
  },
  MKRGCodeSpiralVase: {
    panelName: "mkr_gcode_spiral_vase_studio",
    size: [800, 930],
    accent: "#ba8dff",
    title: "Spiral Vase Studio",
    subtitle: "Generate helical vases with taper, wave modulation, twist, and oval shaping from one sculptable print form node.",
    defaults: {
      height_mm: 120.0,
      base_radius_mm: 28.0,
      top_radius_mm: 24.0,
      bottom_layers: 3,
      layer_height_mm: 0.2,
      line_width_mm: 0.45,
      segments_per_turn: 72,
      wave_amplitude_mm: 0.0,
      wave_frequency: 0.0,
      twist_deg: 0.0,
      phase_deg: 0.0,
      ovality: 0.0,
      print_speed_mm_s: 24.0,
      travel_speed_mm_s: 120.0,
      use_profile_defaults: false,
    },
    numericSpecs: {
      height_mm: { min: 10, max: 500 },
      base_radius_mm: { min: 2, max: 250 },
      top_radius_mm: { min: 2, max: 250 },
      bottom_layers: { min: 0, max: 30, integer: true },
      layer_height_mm: { min: 0.05, max: 1.0 },
      line_width_mm: { min: 0.1, max: 2.0 },
      segments_per_turn: { min: 12, max: 720, integer: true },
      wave_amplitude_mm: { min: 0.0, max: 30.0 },
      wave_frequency: { min: 0.0, max: 50.0 },
      twist_deg: { min: -720, max: 720 },
      phase_deg: { min: -360, max: 360 },
      ovality: { min: -0.75, max: 0.75 },
      print_speed_mm_s: { min: 1, max: 300 },
      travel_speed_mm_s: { min: 1, max: 500 },
    },
    booleanKeys: ["use_profile_defaults"],
    legacyNames: ["height_mm","base_radius_mm","top_radius_mm","bottom_layers","layer_height_mm","line_width_mm","segments_per_turn","wave_amplitude_mm","wave_frequency","twist_deg","phase_deg","ovality","print_speed_mm_s","travel_speed_mm_s","use_profile_defaults"],
    metrics: [
      { label: "Height", get: (node) => `${formatNumber(getNumber(node, "height_mm", 120), 0)} mm` },
      { label: "Radius", get: (node) => `${formatNumber(getNumber(node, "base_radius_mm", 28), 1)}→${formatNumber(getNumber(node, "top_radius_mm", 24), 1)}` },
      { label: "Twist", get: (node) => formatSigned(getNumber(node, "twist_deg", 0), 0) },
    ],
    presets: [
      { label: "Classic", tone: "accent", values: { height_mm: 140, base_radius_mm: 32, top_radius_mm: 26, wave_amplitude_mm: 0, twist_deg: 0, ovality: 0 } },
      { label: "Scallop", values: { height_mm: 150, base_radius_mm: 30, top_radius_mm: 20, wave_amplitude_mm: 3.2, wave_frequency: 7.5, twist_deg: 40, phase_deg: 18 } },
      { label: "Twist Oval", values: { height_mm: 160, base_radius_mm: 26, top_radius_mm: 24, wave_amplitude_mm: 1.8, wave_frequency: 4.2, twist_deg: 180, ovality: 0.24 } },
    ],
    graph: {
      title: "Vase Silhouette",
      note: "form study",
      height: 228,
      draw: drawVaseGraph,
      readouts: [
        { label: "Wave", get: (node) => formatNumber(getNumber(node, "wave_amplitude_mm", 0), 1) },
        { label: "Freq", get: (node) => formatNumber(getNumber(node, "wave_frequency", 0), 1) },
        { label: "Oval", get: (node) => formatSigned(getNumber(node, "ovality", 0), 2) },
      ],
      help: "The silhouette preview reflects taper, wave modulation, ovality, and twist so you can sculpt the vessel before generating the plan.",
    },
    sections: [
      { title: "Form Core", note: "shape", controls: [
        { type: "slider", key: "height_mm", label: "Height", min: 10, max: 500, step: 1, decimals: 0 },
        { type: "slider", key: "base_radius_mm", label: "Base Radius", min: 2, max: 250, step: 0.5, decimals: 1 },
        { type: "slider", key: "top_radius_mm", label: "Top Radius", min: 2, max: 250, step: 0.5, decimals: 1 },
        { type: "slider", key: "bottom_layers", label: "Bottom Layers", min: 0, max: 30, step: 1, decimals: 0 },
      ]},
      { title: "Surface Modulation", note: "pattern", controls: [
        { type: "slider", key: "wave_amplitude_mm", label: "Wave Amp", min: 0, max: 30, step: 0.1, decimals: 1 },
        { type: "slider", key: "wave_frequency", label: "Wave Freq", min: 0, max: 50, step: 0.1, decimals: 1 },
        { type: "slider", key: "twist_deg", label: "Twist", min: -720, max: 720, step: 1, decimals: 0 },
        { type: "slider", key: "phase_deg", label: "Phase", min: -360, max: 360, step: 1, decimals: 0 },
        { type: "slider", key: "ovality", label: "Ovality", min: -0.75, max: 0.75, step: 0.01, decimals: 2 },
      ]},
      { title: "Print Resolution", note: "toolpath", controls: [
        { type: "slider", key: "layer_height_mm", label: "Layer Height", min: 0.05, max: 1.0, step: 0.01, decimals: 2 },
        { type: "slider", key: "line_width_mm", label: "Line Width", min: 0.1, max: 2.0, step: 0.01, decimals: 2 },
        { type: "slider", key: "segments_per_turn", label: "Seg / Turn", min: 12, max: 720, step: 1, decimals: 0 },
        { type: "slider", key: "print_speed_mm_s", label: "Print Speed", min: 1, max: 300, step: 0.5, decimals: 1 },
        { type: "slider", key: "travel_speed_mm_s", label: "Travel Speed", min: 1, max: 500, step: 0.5, decimals: 1 },
        { type: "toggle", key: "use_profile_defaults", label: "Use Profile Defaults", description: "Prefer connected printer profile defaults for line and speed settings." },
      ]},
    ],
  },
  MKRGCodePreview: {
    panelName: "mkr_gcode_preview_studio",
    size: [820, 960],
    accent: "#7ac6ff",
    title: "Preview Studio",
    subtitle: "Drive the toolpath preview mode and load fallback G-code text or a disk path without leaving the node.",
    defaults: {
      view_mode: "auto",
      preview_size: 768,
    },
    numericSpecs: {
      preview_size: { min: 128, max: 2048, integer: true },
    },
    booleanKeys: [],
    legacyNames: ["view_mode","preview_size"],
    hiddenWidgets: ["gcode_text","gcode_path"],
    metrics: [
      { label: "Mode", get: (node) => String(getValue(node, "view_mode", "auto")) },
      { label: "Size", get: (node) => `${Math.round(getNumber(node, "preview_size", 768))} px` },
      { label: "Source", get: (node) => String(getValue(node, "gcode_path", "") || "").trim() ? "path" : (String(getValue(node, "gcode_text", "") || "").trim() ? "text" : "inputs") },
    ],
    presets: [
      { label: "Auto", tone: "accent", values: { view_mode: "auto" } },
      { label: "Plan", values: { view_mode: "plan_top" } },
      { label: "Split", values: { view_mode: "split" } },
    ],
    graph: {
      title: "Viewport Routing",
      note: "mode chooser",
      height: 214,
      draw: drawPreviewGraph,
      readouts: [
        { label: "Path", get: (node) => String(getValue(node, "gcode_path", "") || "").trim() ? "Set" : "Empty" },
        { label: "Text", get: (node) => String(getValue(node, "gcode_text", "") || "").trim() ? "Set" : "Empty" },
        { label: "View", get: (node) => String(getValue(node, "view_mode", "auto")) },
      ],
      help: "Use the panel to steer preview mode and provide fallback text/path sources when no parsed plan is wired in.",
    },
    sections: [
      { title: "Viewport", note: "preview routing", controls: [
        { type: "select", key: "view_mode", label: "View Mode", options: [
          { label: "auto", value: "auto" },
          { label: "plan_top", value: "plan_top" },
          { label: "mesh_isometric", value: "mesh_isometric" },
          { label: "mesh_top", value: "mesh_top" },
          { label: "split", value: "split" },
        ]},
        { type: "slider", key: "preview_size", label: "Preview Size", min: 128, max: 2048, step: 16, decimals: 0 },
      ]},
      { title: "Fallback Sources", note: "optional", controls: [
        { type: "text_widget", key: "gcode_path", label: "G-code Path" },
        { type: "textarea_widget", key: "gcode_text", label: "G-code Text" },
      ]},
    ],
  },
  MKRGCodePlanAnalyzer: {
    panelName: "mkr_gcode_analyzer_studio",
    size: [820, 980],
    accent: "#ff8a8a",
    title: "Plan Analyzer Studio",
    subtitle: "Set print-risk, bed-usage, cooling, and cost thresholds from one diagnostics-oriented tool panel.",
    defaults: {
      max_volumetric_flow_mm3_s: 12.0,
      min_feature_mm: 0.3,
      min_layer_time_s: 8.0,
      warn_travel_ratio_percent: 35.0,
      warn_bed_usage_percent: 75.0,
      filament_price_per_kg: 20.0,
      material_density_g_cm3: 1.24,
      printer_wattage_w: 120.0,
      electricity_price_per_kwh: 0.20,
      warn_total_cost: 12.0,
    },
    numericSpecs: {
      max_volumetric_flow_mm3_s: { min: 0.5, max: 80.0 },
      min_feature_mm: { min: 0.05, max: 10.0 },
      min_layer_time_s: { min: 0.0, max: 300.0 },
      warn_travel_ratio_percent: { min: 0.0, max: 100.0 },
      warn_bed_usage_percent: { min: 0.0, max: 100.0 },
      filament_price_per_kg: { min: 0.0, max: 500.0 },
      material_density_g_cm3: { min: 0.1, max: 10.0 },
      printer_wattage_w: { min: 0.0, max: 5000.0 },
      electricity_price_per_kwh: { min: 0.0, max: 5.0 },
      warn_total_cost: { min: 0.0, max: 10000.0 },
    },
    booleanKeys: [],
    legacyNames: [
      "max_volumetric_flow_mm3_s","min_feature_mm","min_layer_time_s","warn_travel_ratio_percent",
      "warn_bed_usage_percent","filament_price_per_kg","material_density_g_cm3","printer_wattage_w","electricity_price_per_kwh","warn_total_cost",
    ],
    metrics: [
      { label: "Flow", get: (node) => `${formatNumber(getNumber(node, "max_volumetric_flow_mm3_s", 12), 1)} mm3/s` },
      { label: "Bed Warn", get: (node) => `${formatNumber(getNumber(node, "warn_bed_usage_percent", 75), 0)}%` },
      { label: "Cost Warn", get: (node) => `${formatNumber(getNumber(node, "warn_total_cost", 12), 2)}` },
    ],
    presets: [
      { label: "Safe", tone: "accent", values: { max_volumetric_flow_mm3_s: 10, min_feature_mm: 0.4, min_layer_time_s: 10, warn_travel_ratio_percent: 30, warn_bed_usage_percent: 70 } },
      { label: "Balanced", values: { max_volumetric_flow_mm3_s: 12, min_feature_mm: 0.3, min_layer_time_s: 8, warn_travel_ratio_percent: 35, warn_bed_usage_percent: 75 } },
      { label: "Aggressive", values: { max_volumetric_flow_mm3_s: 20, min_feature_mm: 0.2, min_layer_time_s: 4, warn_travel_ratio_percent: 48, warn_bed_usage_percent: 88 } },
    ],
    graph: {
      title: "Threshold Dashboard",
      note: "risk map",
      height: 220,
      draw: drawAnalyzerGraph,
      readouts: [
        { label: "Feature", get: (node) => `${formatNumber(getNumber(node, "min_feature_mm", 0.3), 2)} mm` },
        { label: "Layer Time", get: (node) => `${formatNumber(getNumber(node, "min_layer_time_s", 8), 1)} s` },
        { label: "Travel", get: (node) => `${formatNumber(getNumber(node, "warn_travel_ratio_percent", 35), 0)}%` },
      ],
      help: "The bars show the current thresholds, so you can quickly tune the analyzer for a conservative or aggressive print-risk stance.",
    },
    sections: [
      { title: "Geometry Risk", note: "printability", controls: [
        { type: "slider", key: "max_volumetric_flow_mm3_s", label: "Max Flow", min: 0.5, max: 80, step: 0.1, decimals: 1 },
        { type: "slider", key: "min_feature_mm", label: "Min Feature", min: 0.05, max: 10, step: 0.01, decimals: 2 },
        { type: "slider", key: "min_layer_time_s", label: "Min Layer Time", min: 0, max: 300, step: 0.5, decimals: 1 },
        { type: "slider", key: "warn_travel_ratio_percent", label: "Travel Warn", min: 0, max: 100, step: 1, decimals: 0 },
        { type: "slider", key: "warn_bed_usage_percent", label: "Bed Usage Warn", min: 0, max: 100, step: 1, decimals: 0 },
      ]},
      { title: "Cost Model", note: "estimate", controls: [
        { type: "slider", key: "filament_price_per_kg", label: "Filament/kg", min: 0, max: 500, step: 0.1, decimals: 2 },
        { type: "slider", key: "material_density_g_cm3", label: "Density", min: 0.1, max: 10, step: 0.01, decimals: 2 },
        { type: "slider", key: "printer_wattage_w", label: "Wattage", min: 0, max: 5000, step: 1, decimals: 0 },
        { type: "slider", key: "electricity_price_per_kwh", label: "Power/kWh", min: 0, max: 5, step: 0.01, decimals: 2 },
        { type: "slider", key: "warn_total_cost", label: "Cost Warn", min: 0, max: 10000, step: 0.1, decimals: 2 },
      ]},
    ],
  },
};

const TARGET_NAMES = new Set(Object.keys(CONFIGS));

function readControlValue(node, spec) {
  if (spec.type === "toggle") return getBoolean(node, spec.key, !!spec.default);
  if (spec.type === "select" || spec.type === "text" || spec.type === "textarea" || spec.type === "text_widget" || spec.type === "textarea_widget") {
    return getValue(node, spec.key, spec.default ?? "");
  }
  return getNumber(node, spec.key, Number(spec.default || 0));
}

function createControl(node, spec, refresh) {
  if (spec.type === "toggle") {
    const control = createGradeToggle({
      label: spec.label,
      checked: getBoolean(node, spec.key, !!spec.default),
      description: spec.description || "",
      onChange: (value) => {
        setWidgetValue(node, spec.key, value);
        refresh();
      },
    });
    return { key: spec.key, ...control };
  }
  if (spec.type === "select") {
    const control = createSelectControl({
      label: spec.label,
      value: String(getValue(node, spec.key, spec.default ?? "")),
      options: spec.options || [],
      onChange: (value) => {
        setWidgetValue(node, spec.key, value);
        refresh();
      },
    });
    return { key: spec.key, ...control };
  }
  if (spec.type === "text" || spec.type === "textarea" || spec.type === "text_widget" || spec.type === "textarea_widget") {
    const control = createTextControl({
      label: spec.label,
      value: String(getValue(node, spec.key, spec.default ?? "")),
      multiline: spec.type === "textarea" || spec.type === "textarea_widget",
      placeholder: spec.placeholder || "",
      onChange: (value) => {
        setWidgetValue(node, spec.key, value);
        refresh();
      },
    });
    return { key: spec.key, ...control };
  }
  const control = createGradeSlider({
    label: spec.label,
    min: spec.min,
    max: spec.max,
    step: spec.step,
    value: getNumber(node, spec.key, spec.default ?? spec.min),
    decimals: spec.decimals ?? 2,
    onChange: (value) => {
      setWidgetValue(node, spec.key, value);
      refresh();
    },
  });
  return { key: spec.key, ...control };
}

function buildPanel(node, config) {
  ensureLocalStyles();
  const { panel } = createPanelShell({
    kicker: "MKR SHIFT G-CODE",
    title: config.title,
    subtitle: config.subtitle,
    showHeader: false,
  });
  panel.classList.add("mkr-grade-panel");
  panel.style.setProperty("--mkr-grade-accent", config.accent);
  panel.style.paddingBottom = "18px";

  const topbar = document.createElement("div");
  topbar.className = "mkr-grade-topbar";
  const metricsWrap = document.createElement("div");
  metricsWrap.className = "mkr-grade-metrics";
  const metricViews = (config.metrics || []).map((metric) => {
    const view = createGradeMetric(metric.label, metric.get(node));
    metricsWrap.appendChild(view.element);
    return { ...metric, view };
  });
  const actions = document.createElement("div");
  actions.className = "mkr-grade-actions";
  for (const preset of config.presets || []) {
    actions.appendChild(createGradeButton(preset.label, () => {
      applyValues(node, preset.values);
      refresh();
    }, preset.tone || ""));
  }
  topbar.appendChild(metricsWrap);
  topbar.appendChild(actions);
  panel.appendChild(topbar);

  const graphSection = createGradeSection(config.graph.title, config.graph.note || "");
  const canvas = document.createElement("canvas");
  canvas.className = "mkr-grade-canvas";
  canvas.style.height = `${config.graph.height || 220}px`;
  graphSection.body.appendChild(canvas);
  const readoutWrap = document.createElement("div");
  readoutWrap.className = "mkr-grade-inline";
  const readoutViews = (config.graph.readouts || []).map((readout) => {
    const view = createGradeReadout(readout.label, readout.get(node));
    readoutWrap.appendChild(view.element);
    return { ...readout, view };
  });
  if (readoutViews.length) graphSection.body.appendChild(readoutWrap);
  addHelp(graphSection, config.graph.help);
  panel.appendChild(graphSection.section);

  const controlViews = [];
  for (const sectionSpec of config.sections || []) {
    const section = createGradeSection(sectionSpec.title, sectionSpec.note || "");
    const grid = document.createElement("div");
    grid.className = "mkr-grade-controls";
    for (const controlSpec of sectionSpec.controls || []) {
      const spec = { ...controlSpec };
      if (spec.default === undefined) spec.default = config.defaults[spec.key];
      const control = createControl(node, spec, refresh);
      grid.appendChild(control.element);
      controlViews.push({ spec, control });
    }
    section.body.appendChild(grid);
    addHelp(section, sectionSpec.help);
    panel.appendChild(section.section);
  }

  if (typeof ResizeObserver !== "undefined") {
    const observer = new ResizeObserver(() => drawCanvas());
    observer.observe(canvas);
  }

  function drawCanvas() {
    const { ctx, width, height } = ensureCanvasResolution(canvas);
    config.graph.draw(ctx, width, height, node, config);
  }

  function refresh() {
    metricViews.forEach((metric) => metric.view.setValue(metric.get(node)));
    readoutViews.forEach((readout) => readout.view.setValue(readout.get(node)));
    controlViews.forEach(({ spec, control }) => control.setValue(readControlValue(node, spec)));
    drawCanvas();
  }

  refresh();
  return { panel, refresh };
}

function prepareNode(node) {
  const name = String(node?.comfyClass || node?.type || "");
  const config = CONFIGS[name];
  if (!config) return;

  installBundledSettingsAdapter(node, {
    widgetName: SETTINGS_WIDGET_NAME,
    defaults: config.defaults,
    numericSpecs: config.numericSpecs,
    booleanKeys: config.booleanKeys,
    legacyNames: config.legacyNames,
  });

  const hidden = [SETTINGS_WIDGET_NAME, ...(config.legacyNames || []), ...(config.hiddenWidgets || [])];

  if (node.__mkrGcodePanelInstalled) {
    node.__mkrGcodeRefresh?.();
    normalizePanelNode(node, hidden, config.panelName);
    return;
  }

  node.__mkrGcodePanelInstalled = true;
  const built = buildPanel(node, config);
  node.__mkrGcodeRefresh = built.refresh;
  attachPanel(node, config.panelName, built.panel, config.size[0], config.size[1]);
  normalizePanelNode(node, hidden, config.panelName);
  installRefreshHooks(node, "__mkrGcodeRefreshHooksInstalled", built.refresh);
  requestAnimationFrame(() => built.refresh());
}

app.registerExtension({
  name: EXTENSION_NAME,
  async beforeRegisterNodeDef(nodeType, nodeData) {
    const nodeName = String(nodeData?.name || nodeData?.type || "");
    if (!TARGET_NAMES.has(nodeName)) return;
    const originalOnNodeCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function onNodeCreated() {
      const result = typeof originalOnNodeCreated === "function" ? originalOnNodeCreated.apply(this, arguments) : undefined;
      prepareNode(this);
      return result;
    };
  },
  async nodeCreated(node) {
    prepareNode(node);
  },
  async afterConfigureGraph() {
    for (const node of app.graph?._nodes || []) {
      const name = String(node?.comfyClass || node?.type || "");
      if (TARGET_NAMES.has(name)) prepareNode(node);
    }
  },
});
