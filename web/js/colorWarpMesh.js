import { app } from "../../scripts/app.js";

const TARGETS = new Set(["x1ColorWarpHueSat", "x1ColorWarpChromaLuma"]);
const HIDE_WIDGETS = new Set(["warp_points_json"]);

function widget(node, name) {
  return Array.isArray(node?.widgets) ? node.widgets.find((w) => String(w?.name || "") === name) : null;
}

function hideWidgets(node) {
  for (const w of node.widgets || []) {
    if (!HIDE_WIDGETS.has(String(w?.name || ""))) continue;
    w.hidden = true;
    w.computeSize = () => [0, -4];
  }
}

function parsePoints(text) {
  try {
    const arr = JSON.parse(String(text || "[]"));
    if (!Array.isArray(arr)) return [];
    return arr
      .filter((p) => p && typeof p === "object")
      .slice(0, 12)
      .map((p) => ({
        src_x: Math.max(0, Math.min(1, Number(p.src_x) || 0.5)),
        src_y: Math.max(0, Math.min(1, Number(p.src_y) || 0.5)),
        dst_x: Math.max(0, Math.min(1, Number(p.dst_x ?? p.src_x) || 0.5)),
        dst_y: Math.max(0, Math.min(1, Number(p.dst_y ?? p.src_y) || 0.5)),
        radius: Math.max(0.03, Math.min(0.5, Number(p.radius) || 0.16)),
        weight: Math.max(0, Math.min(2, Number(p.weight) || 1)),
      }));
  } catch {
    return [];
  }
}

function writePoints(node, points) {
  const w = widget(node, "warp_points_json");
  if (!w) return;
  w.value = JSON.stringify(points);
  if (typeof w.callback === "function") w.callback(w.value);
}

function defaultPoints() {
  return [
    { src_x: 0.25, src_y: 0.35, dst_x: 0.22, dst_y: 0.28, radius: 0.18, weight: 1.0 },
    { src_x: 0.50, src_y: 0.50, dst_x: 0.54, dst_y: 0.56, radius: 0.16, weight: 1.0 },
    { src_x: 0.75, src_y: 0.65, dst_x: 0.80, dst_y: 0.60, radius: 0.15, weight: 1.0 },
  ];
}

function addPoint(points, x, y) {
  if (!Array.isArray(points) || points.length >= 12) return points;
  points.push({
    src_x: x,
    src_y: y,
    dst_x: x,
    dst_y: y,
    radius: 0.16,
    weight: 1.0,
  });
  return points;
}

function removeNearestPoint(points, x, y) {
  if (!Array.isArray(points) || points.length <= 1) return points;
  let bestIdx = -1;
  let bestDist = 10e9;
  for (let i = 0; i < points.length; i++) {
    const p = points[i];
    const d = Math.hypot((p.dst_x - x), (p.dst_y - y));
    if (d < bestDist) {
      bestDist = d;
      bestIdx = i;
    }
  }
  if (bestIdx >= 0 && bestDist <= 0.12) {
    points.splice(bestIdx, 1);
  }
  return points;
}

function toScreen(graph, x, y) {
  return { x: graph.x + (x * graph.w), y: graph.y + ((1 - y) * graph.h) };
}

function fromScreen(graph, x, y) {
  const nx = Math.max(0, Math.min(1, (x - graph.x) / Math.max(1, graph.w)));
  const ny = 1 - Math.max(0, Math.min(1, (y - graph.y) / Math.max(1, graph.h)));
  return { x: nx, y: ny };
}

app.registerExtension({
  name: "MKRShift.ColorWarpMesh",
  beforeRegisterNodeDef(nodeType, nodeData) {
    if (!TARGETS.has(nodeData?.name)) return;

    const onCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function onNodeCreated() {
      const out = onCreated?.apply(this, arguments);
      hideWidgets(this);
      this.__mkrWarp = { active: -1, hit: [], points: defaultPoints() };
      const w = widget(this, "warp_points_json");
      const parsed = parsePoints(w?.value);
      this.__mkrWarp.points = parsed.length ? parsed : defaultPoints();
      writePoints(this, this.__mkrWarp.points);
      this.setSize([Math.max(this.size?.[0] || 660, 660), Math.max(this.size?.[1] || 420, 420)]);
      return out;
    };

    const onDrawForeground = nodeType.prototype.onDrawForeground;
    nodeType.prototype.onDrawForeground = function onDrawForeground(ctx) {
      onDrawForeground?.apply(this, arguments);
      if (this.flags?.collapsed) return;
      hideWidgets(this);

      const graph = { x: 24, y: 72, w: (this.size?.[0] || 660) - 48, h: 270 };
      const points = this.__mkrWarp?.points || defaultPoints();

      ctx.save();
      const grad = ctx.createLinearGradient(graph.x, graph.y, graph.x + graph.w, graph.y + graph.h);
      grad.addColorStop(0.0, "rgba(148,126,58,0.28)");
      grad.addColorStop(0.5, "rgba(70,76,88,0.32)");
      grad.addColorStop(1.0, "rgba(78,114,190,0.28)");
      ctx.fillStyle = grad;
      ctx.fillRect(graph.x, graph.y, graph.w, graph.h);

      ctx.strokeStyle = "rgba(200,208,222,0.2)";
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

      const hit = [];
      for (let i = 0; i < points.length; i++) {
        const p = points[i];
        const s = toScreen(graph, p.src_x, p.src_y);
        const d = toScreen(graph, p.dst_x, p.dst_y);

        ctx.strokeStyle = "rgba(173,183,204,0.5)";
        ctx.lineWidth = 1.4;
        ctx.beginPath();
        ctx.moveTo(s.x, s.y);
        ctx.lineTo(d.x, d.y);
        ctx.stroke();

        ctx.fillStyle = "#cfd7e6";
        ctx.beginPath();
        ctx.arc(s.x, s.y, 3.8, 0, Math.PI * 2);
        ctx.fill();

        ctx.fillStyle = "#ff6b5f";
        ctx.beginPath();
        ctx.arc(d.x, d.y, 4.4, 0, Math.PI * 2);
        ctx.fill();

        hit.push({ idx: i, x: d.x, y: d.y, r: 8 });
      }

      ctx.fillStyle = "#c7cfde";
      ctx.font = "12px sans-serif";
      ctx.textAlign = "left";
      ctx.fillText("Drag red mesh points to warp color mapping", graph.x, graph.y - 12);
      ctx.fillStyle = "rgba(199,207,222,0.75)";
      ctx.fillText("Shift+Click add point • Alt+Click remove nearest", graph.x, graph.y + graph.h + 16);

      this.__mkrWarp.hit = hit;
      this.__mkrWarp.graph = graph;
      ctx.restore();
    };

    const onMouseDown = nodeType.prototype.onMouseDown;
    nodeType.prototype.onMouseDown = function onMouseDown(e, pos, graphCanvas) {
      const graph = this.__mkrWarp?.graph;
      const points = this.__mkrWarp?.points;
      if (graph && Array.isArray(points) && (e?.shiftKey || e?.altKey)) {
        const uv = fromScreen(graph, pos[0], pos[1]);
        if (e.shiftKey) {
          addPoint(points, uv.x, uv.y);
        } else if (e.altKey) {
          removeNearestPoint(points, uv.x, uv.y);
        }
        writePoints(this, points);
        this.setDirtyCanvas(true, true);
        return true;
      }
      for (const h of this.__mkrWarp?.hit || []) {
        if (Math.hypot(pos[0] - h.x, pos[1] - h.y) <= h.r + 3) {
          this.__mkrWarp.active = h.idx;
          this.captureInput?.(true);
          return true;
        }
      }
      return onMouseDown?.apply(this, arguments);
    };

    const onMouseMove = nodeType.prototype.onMouseMove;
    nodeType.prototype.onMouseMove = function onMouseMove(e, pos, graphCanvas) {
      const idx = this.__mkrWarp?.active;
      const graph = this.__mkrWarp?.graph;
      const points = this.__mkrWarp?.points;
      if (!Number.isInteger(idx) || idx < 0 || !graph || !Array.isArray(points) || !points[idx]) {
        return onMouseMove?.apply(this, arguments);
      }
      const uv = fromScreen(graph, pos[0], pos[1]);
      points[idx].dst_x = uv.x;
      points[idx].dst_y = uv.y;
      writePoints(this, points);
      this.setDirtyCanvas(true, true);
      return true;
    };

    const onMouseUp = nodeType.prototype.onMouseUp;
    nodeType.prototype.onMouseUp = function onMouseUp(e, pos, graphCanvas) {
      if ((this.__mkrWarp?.active ?? -1) >= 0) {
        this.__mkrWarp.active = -1;
        this.captureInput?.(false);
        return true;
      }
      return onMouseUp?.apply(this, arguments);
    };
  },
});
