import { app } from "../../scripts/app.js";

const TARGET_NODE = "x1Curves";
const HIDE_WIDGETS = new Set([
  "master_shadows",
  "master_midtones",
  "master_highlights",
  "red_curve",
  "green_curve",
  "blue_curve",
]);

const MASTER_KEYS = [
  { key: "master_shadows", x: 0.2, color: "#d8dde7", label: "Shadows" },
  { key: "master_midtones", x: 0.5, color: "#d8dde7", label: "Mid" },
  { key: "master_highlights", x: 0.8, color: "#d8dde7", label: "High" },
];

const CHANNEL_KEYS = [
  { key: "red_curve", color: "#ff4e4e", label: "R" },
  { key: "green_curve", color: "#4bd65f", label: "G" },
  { key: "blue_curve", color: "#4e8fff", label: "B" },
];

function widget(node, name) {
  return Array.isArray(node?.widgets) ? node.widgets.find((w) => String(w?.name || "") === name) : null;
}

function getValue(node, name) {
  const v = Number(widget(node, name)?.value);
  return Number.isFinite(v) ? Math.max(-1, Math.min(1, v)) : 0;
}

function setValue(node, name, value) {
  const clamped = Math.max(-1, Math.min(1, Number(value) || 0));
  const w = widget(node, name);
  if (!w) return;
  w.value = Number(clamped.toFixed(4));
  if (typeof w.callback === "function") w.callback(w.value);
}

function hideWidgets(node) {
  for (const w of node.widgets || []) {
    if (!HIDE_WIDGETS.has(String(w?.name || ""))) continue;
    w.hidden = true;
    w.computeSize = () => [0, -4];
  }
}

function valueToY(value, top, height) {
  const t = (value + 1) * 0.5;
  return top + ((1 - t) * height);
}

function yToValue(y, top, height) {
  const t = 1 - ((y - top) / Math.max(1, height));
  return (t * 2) - 1;
}

app.registerExtension({
  name: "MKRShift.ColorCurvesPhysical",
  beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData?.name !== TARGET_NODE) return;

    const onCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function onNodeCreated() {
      const out = onCreated?.apply(this, arguments);
      hideWidgets(this);
      this.__mkrCurves = { active: null, hit: [] };
      this.setSize([Math.max(this.size?.[0] || 690, 690), Math.max(this.size?.[1] || 420, 420)]);
      return out;
    };

    const onDrawForeground = nodeType.prototype.onDrawForeground;
    nodeType.prototype.onDrawForeground = function onDrawForeground(ctx) {
      onDrawForeground?.apply(this, arguments);
      if (this.flags?.collapsed) return;
      hideWidgets(this);

      const width = this.size?.[0] || 690;
      const graph = { x: 24, y: 68, w: Math.max(360, width - 48), h: 250 };

      ctx.save();
      ctx.fillStyle = "rgba(35,38,46,0.9)";
      ctx.fillRect(graph.x, graph.y, graph.w, graph.h);

      ctx.strokeStyle = "rgba(120,130,150,0.24)";
      ctx.lineWidth = 1;
      for (let i = 0; i <= 10; i++) {
        const gx = graph.x + (graph.w * i / 10);
        const gy = graph.y + (graph.h * i / 10);
        ctx.beginPath();
        ctx.moveTo(gx, graph.y);
        ctx.lineTo(gx, graph.y + graph.h);
        ctx.stroke();
        ctx.beginPath();
        ctx.moveTo(graph.x, gy);
        ctx.lineTo(graph.x + graph.w, gy);
        ctx.stroke();
      }

      ctx.strokeStyle = "rgba(220,226,236,0.85)";
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(graph.x, graph.y + graph.h);
      ctx.lineTo(graph.x + graph.w, graph.y);
      ctx.stroke();

      const hit = [];

      ctx.font = "12px sans-serif";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";

      for (const item of MASTER_KEYS) {
        const x = graph.x + (graph.w * item.x);
        const y = valueToY(getValue(this, item.key), graph.y, graph.h);
        ctx.fillStyle = item.color;
        ctx.beginPath();
        ctx.arc(x, y, 5, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillText(item.label, x, graph.y + graph.h + 16);
        hit.push({ key: item.key, x, y, r: 8 });
      }

      const channelXs = [0.45, 0.5, 0.55];
      for (let i = 0; i < CHANNEL_KEYS.length; i++) {
        const item = CHANNEL_KEYS[i];
        const x = graph.x + (graph.w * channelXs[i]);
        const y = valueToY(getValue(this, item.key), graph.y, graph.h);
        ctx.fillStyle = item.color;
        ctx.beginPath();
        ctx.arc(x, y, 5, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillText(item.label, x, graph.y - 12);
        hit.push({ key: item.key, x, y, r: 8 });
      }

      this.__mkrCurves.hit = hit;
      this.__mkrCurves.graph = graph;
      ctx.restore();
    };

    const onMouseDown = nodeType.prototype.onMouseDown;
    nodeType.prototype.onMouseDown = function onMouseDown(e, pos, graphCanvas) {
      for (const p of this.__mkrCurves?.hit || []) {
        if (Math.hypot(pos[0] - p.x, pos[1] - p.y) <= p.r + 3) {
          this.__mkrCurves.active = p.key;
          this.captureInput?.(true);
          return true;
        }
      }
      return onMouseDown?.apply(this, arguments);
    };

    const onMouseMove = nodeType.prototype.onMouseMove;
    nodeType.prototype.onMouseMove = function onMouseMove(e, pos, graphCanvas) {
      const key = this.__mkrCurves?.active;
      const graph = this.__mkrCurves?.graph;
      if (!key || !graph) return onMouseMove?.apply(this, arguments);
      const y = Math.max(graph.y, Math.min(graph.y + graph.h, pos[1]));
      setValue(this, key, yToValue(y, graph.y, graph.h));
      this.setDirtyCanvas(true, true);
      return true;
    };

    const onMouseUp = nodeType.prototype.onMouseUp;
    nodeType.prototype.onMouseUp = function onMouseUp(e, pos, graphCanvas) {
      if (this.__mkrCurves?.active) {
        this.__mkrCurves.active = null;
        this.captureInput?.(false);
        return true;
      }
      return onMouseUp?.apply(this, arguments);
    };
  },
});
