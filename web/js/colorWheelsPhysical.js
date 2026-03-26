import { app } from "../../scripts/app.js";

const TARGET_NODE = "x1ColorWheels";
const HIDDEN_WIDGETS = new Set([
  "lift_r", "lift_g", "lift_b",
  "gamma_r", "gamma_g", "gamma_b",
  "gain_r", "gain_g", "gain_b",
  "offset_r", "offset_g", "offset_b",
]);

const WHEELS = [
  { key: "lift", label: "Shadows", mode: "centered" },
  { key: "gamma", label: "Midtones", mode: "pivot" },
  { key: "gain", label: "Highlights", mode: "pivot" },
  { key: "offset", label: "Offset", mode: "centered" },
];

function widgetByName(node, name) {
  return Array.isArray(node?.widgets) ? node.widgets.find((w) => String(w?.name || "") === name) : null;
}

function setWidgetValue(node, name, value) {
  const w = widgetByName(node, name);
  if (!w) return;
  w.value = value;
  if (typeof w.callback === "function") w.callback(value);
}

function getWidgetValue(node, name, fallback = 0) {
  const w = widgetByName(node, name);
  const n = Number(w?.value);
  return Number.isFinite(n) ? n : fallback;
}

function rgbFromPoint(x, y, mode) {
  const r = x;
  const g = (-0.5 * x) + (0.8660254 * y);
  const b = (-0.5 * x) - (0.8660254 * y);
  if (mode === "pivot") {
    return {
      r: Math.max(0.1, Math.min(3.0, 1.0 + r)),
      g: Math.max(0.1, Math.min(3.0, 1.0 + g)),
      b: Math.max(0.1, Math.min(3.0, 1.0 + b)),
    };
  }
  return {
    r: Math.max(-1.0, Math.min(1.0, r)),
    g: Math.max(-1.0, Math.min(1.0, g)),
    b: Math.max(-1.0, Math.min(1.0, b)),
  };
}

function pointFromRgb(r, g, b, mode) {
  const rr = mode === "pivot" ? (r - 1.0) : r;
  const gg = mode === "pivot" ? (g - 1.0) : g;
  const bb = mode === "pivot" ? (b - 1.0) : b;
  const x = rr;
  const y = (gg - bb) / 1.7320508;
  const len = Math.hypot(x, y);
  if (len > 1.0) {
    return { x: x / len, y: y / len };
  }
  return { x, y };
}

function drawHueWheel(ctx, cx, cy, radius) {
  const ring = 12;
  for (let i = 0; i < 72; i++) {
    const a0 = (Math.PI * 2 * i) / 72;
    const a1 = (Math.PI * 2 * (i + 1)) / 72;
    ctx.beginPath();
    ctx.arc(cx, cy, radius, a0, a1);
    ctx.strokeStyle = `hsl(${Math.round((360 * i) / 72)} 90% 55%)`;
    ctx.lineWidth = ring;
    ctx.stroke();
  }

  const grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, radius - ring - 2);
  grad.addColorStop(0, "rgba(255,255,255,0.95)");
  grad.addColorStop(1, "rgba(30,34,42,0.92)");
  ctx.beginPath();
  ctx.fillStyle = grad;
  ctx.arc(cx, cy, radius - ring - 2, 0, Math.PI * 2);
  ctx.fill();

  ctx.strokeStyle = "rgba(180,190,205,0.35)";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(cx - radius + 14, cy);
  ctx.lineTo(cx + radius - 14, cy);
  ctx.moveTo(cx, cy - radius + 14);
  ctx.lineTo(cx, cy + radius - 14);
  ctx.stroke();
}

function hideTechnicalWidgets(node) {
  for (const widget of node.widgets || []) {
    if (!HIDDEN_WIDGETS.has(String(widget?.name || ""))) continue;
    widget.hidden = true;
    widget.computeSize = () => [0, -4];
  }
}

app.registerExtension({
  name: "MKRShift.ColorWheelsPhysical",
  beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData?.name !== TARGET_NODE) return;

    const onCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function onNodeCreated() {
      const created = onCreated?.apply(this, arguments);
      hideTechnicalWidgets(this);
      this.__mkrWheels = { active: null, hit: [] };
      this.setSize([Math.max(this.size?.[0] || 880, 880), Math.max(this.size?.[1] || 420, 420)]);
      return created;
    };

    const drawFg = nodeType.prototype.onDrawForeground;
    nodeType.prototype.onDrawForeground = function onDrawForeground(ctx) {
      drawFg?.apply(this, arguments);
      if (this.flags?.collapsed) return;

      hideTechnicalWidgets(this);

      const width = this.size?.[0] || 880;
      const startX = 95;
      const topY = 92;
      const spacing = Math.max(175, (width - 160) / 4);
      const radius = 58;
      const hit = [];

      ctx.save();
      ctx.font = "12px sans-serif";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";

      for (let i = 0; i < WHEELS.length; i++) {
        const wheel = WHEELS[i];
        const cx = startX + (i * spacing);
        const cy = topY;
        drawHueWheel(ctx, cx, cy, radius);

        const r = getWidgetValue(this, `${wheel.key}_r`, wheel.mode === "pivot" ? 1.0 : 0.0);
        const g = getWidgetValue(this, `${wheel.key}_g`, wheel.mode === "pivot" ? 1.0 : 0.0);
        const b = getWidgetValue(this, `${wheel.key}_b`, wheel.mode === "pivot" ? 1.0 : 0.0);
        const pos = pointFromRgb(r, g, b, wheel.mode);
        const px = cx + (pos.x * (radius - 16));
        const py = cy + (pos.y * (radius - 16));

        ctx.fillStyle = "#ffffff";
        ctx.strokeStyle = "#1b1f27";
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.arc(px, py, 4.5, 0, Math.PI * 2);
        ctx.fill();
        ctx.stroke();

        ctx.fillStyle = "#cfd7e6";
        ctx.fillText(wheel.label, cx, cy - radius - 18);
        hit.push({ key: wheel.key, mode: wheel.mode, cx, cy, radius: radius - 16 });
      }

      this.__mkrWheels.hit = hit;
      ctx.restore();
    };

    const mouseDown = nodeType.prototype.onMouseDown;
    nodeType.prototype.onMouseDown = function onMouseDown(e, pos, graphCanvas) {
      const hit = this.__mkrWheels?.hit || [];
      for (const wheel of hit) {
        const dx = pos[0] - wheel.cx;
        const dy = pos[1] - wheel.cy;
        if (Math.hypot(dx, dy) <= wheel.radius + 4) {
          this.__mkrWheels.active = wheel;
          this.captureInput?.(true);
          return true;
        }
      }
      return mouseDown?.apply(this, arguments);
    };

    const mouseMove = nodeType.prototype.onMouseMove;
    nodeType.prototype.onMouseMove = function onMouseMove(e, pos, graphCanvas) {
      const active = this.__mkrWheels?.active;
      if (!active) return mouseMove?.apply(this, arguments);

      const dx = pos[0] - active.cx;
      const dy = pos[1] - active.cy;
      const len = Math.max(1e-6, Math.hypot(dx, dy));
      const clamped = Math.min(active.radius, len);
      const nx = (dx / len) * (clamped / active.radius);
      const ny = (dy / len) * (clamped / active.radius);
      const rgb = rgbFromPoint(nx, ny, active.mode);

      setWidgetValue(this, `${active.key}_r`, Number(rgb.r.toFixed(4)));
      setWidgetValue(this, `${active.key}_g`, Number(rgb.g.toFixed(4)));
      setWidgetValue(this, `${active.key}_b`, Number(rgb.b.toFixed(4)));
      this.setDirtyCanvas(true, true);
      return true;
    };

    const mouseUp = nodeType.prototype.onMouseUp;
    nodeType.prototype.onMouseUp = function onMouseUp(e, pos, graphCanvas) {
      if (this.__mkrWheels?.active) {
        this.__mkrWheels.active = null;
        this.captureInput?.(false);
        return true;
      }
      return mouseUp?.apply(this, arguments);
    };
  },
});
