const STYLE_ID = "mkr-shift-ui-v3";

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

export function clamp(v, lo, hi) {
  return Math.max(lo, Math.min(hi, v));
}

export function ensureMkrUIStyles() {
  if (document.getElementById(STYLE_ID)) return;

  const style = document.createElement("style");
  style.id = STYLE_ID;
  style.textContent = `
    .mkr-panel {
      --mkr-ink: #13212f;
      --mkr-card: rgba(247, 243, 235, 0.88);
      --mkr-card-alt: rgba(255, 250, 244, 0.96);
      --mkr-accent-a-src: var(--mkr-accent-a, #2d9c8f);
      --mkr-accent-b: #f39f4d;
      --mkr-accent-c: #d9573b;
      --mkr-muted: #5a6a78;
      --mkr-line: rgba(16, 35, 45, 0.14);
      --mkr-shadow: 0 14px 30px rgba(24, 38, 53, 0.12);
      --mkr-accent-a-soft: rgba(45, 156, 143, 0.18);
      --mkr-accent-a-border: rgba(45, 156, 143, 0.45);
      --mkr-accent-a-glow: rgba(45, 156, 143, 0.16);
      --mkr-accent-a-soft: color-mix(in srgb, var(--mkr-accent-a-src) 18%, transparent);
      --mkr-accent-a-border: color-mix(in srgb, var(--mkr-accent-a-src) 52%, transparent);
      --mkr-accent-a-glow: color-mix(in srgb, var(--mkr-accent-a-src) 16%, transparent);

      width: min(100%, 470px);
      max-height: min(84vh, 920px);
      overflow-y: auto;
      padding: 12px;
      border-radius: 18px;
      border: 1px solid rgba(255, 255, 255, 0.55);
      background:
        radial-gradient(120% 120% at 100% 0%, rgba(243, 159, 77, 0.22) 0%, rgba(243, 159, 77, 0) 58%),
        radial-gradient(140% 120% at 0% 100%, rgba(45, 156, 143, 0.2) 0%, rgba(45, 156, 143, 0) 60%),
        linear-gradient(160deg, #fffdf8 0%, #f3f8fb 100%);
      box-shadow: var(--mkr-shadow);
      color: var(--mkr-ink);
      font-family: "Space Grotesk", "Avenir Next", "Gill Sans Nova", sans-serif;
      animation: mkr-panel-rise 260ms ease-out;
      box-sizing: border-box;
    }

    .mkr-header {
      margin-bottom: 10px;
      padding: 8px 10px;
      border-radius: 12px;
      background: linear-gradient(120deg, rgba(45, 156, 143, 0.1), rgba(243, 159, 77, 0.16));
      border: 1px solid rgba(19, 33, 47, 0.08);
    }

    .mkr-kicker {
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.11em;
      color: var(--mkr-muted);
      margin-bottom: 4px;
    }

    .mkr-title {
      font-size: 18px;
      font-weight: 700;
      line-height: 1.15;
      margin: 0;
      color: #10293b;
    }

    .mkr-subtitle {
      margin-top: 4px;
      margin-bottom: 0;
      font-size: 12px;
      color: #365165;
      line-height: 1.35;
    }

    .mkr-section {
      margin-top: 10px;
      padding: 10px;
      border-radius: 13px;
      border: 1px solid var(--mkr-line);
      background: var(--mkr-card);
      backdrop-filter: blur(2px);
      animation: mkr-section-in 240ms ease-out;
      animation-delay: var(--mkr-delay, 0ms);
      animation-fill-mode: both;
      box-sizing: border-box;
    }

    .mkr-section-head {
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      gap: 6px;
      margin-bottom: 8px;
    }

    .mkr-section-title {
      margin: 0;
      font-size: 13px;
      font-weight: 700;
      letter-spacing: 0.01em;
      color: #113046;
    }

    .mkr-section-note {
      margin: 0;
      font-size: 11px;
      color: var(--mkr-muted);
    }

    .mkr-stack {
      display: flex;
      flex-direction: column;
      gap: 8px;
    }

    .mkr-control {
      display: grid;
      grid-template-columns: minmax(92px, 115px) 1fr auto;
      align-items: center;
      gap: 8px;
      padding: 6px 0;
      border-bottom: 1px dashed rgba(19, 33, 47, 0.08);
    }

    .mkr-control:last-child {
      border-bottom: 0;
      padding-bottom: 0;
    }

    .mkr-label {
      font-size: 12px;
      font-weight: 600;
      color: #214158;
    }

    .mkr-input,
    .mkr-select,
    .mkr-number,
    .mkr-btn {
      border: 1px solid rgba(18, 42, 56, 0.2);
      border-radius: 9px;
      background: var(--mkr-card-alt);
      color: #143246;
      padding: 6px 8px;
      font-family: inherit;
      font-size: 12px;
      outline: none;
      box-sizing: border-box;
      transition: border-color 120ms ease, box-shadow 120ms ease, transform 120ms ease;
    }

    .mkr-input:focus,
    .mkr-select:focus,
    .mkr-number:focus,
    .mkr-btn:focus {
      border-color: var(--mkr-accent-a-src);
      box-shadow: 0 0 0 3px var(--mkr-accent-a-glow);
    }

    .mkr-range {
      width: 100%;
      accent-color: var(--mkr-accent-a-src);
    }

    .mkr-number {
      width: 72px;
      text-align: right;
      font-variant-numeric: tabular-nums;
    }

    .mkr-triplet {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 6px;
      min-width: 0;
    }

    .mkr-toggle-wrap {
      display: flex;
      align-items: center;
      gap: 8px;
      justify-content: flex-start;
    }

    .mkr-toggle {
      width: 16px;
      height: 16px;
      accent-color: var(--mkr-accent-c);
    }

    .mkr-btn-row {
      display: flex;
      gap: 7px;
      flex-wrap: wrap;
    }

    .mkr-btn {
      font-weight: 700;
      letter-spacing: 0.01em;
      cursor: pointer;
      background: linear-gradient(180deg, #fffaf2, #f1f8ff);
    }

    .mkr-btn[data-tone="accent"] {
      background: linear-gradient(130deg, var(--mkr-accent-a-soft), var(--mkr-card-alt));
      background: linear-gradient(
        130deg,
        var(--mkr-accent-a-soft),
        color-mix(in srgb, var(--mkr-accent-a-src) 32%, var(--mkr-card-alt))
      );
      border-color: var(--mkr-accent-a-border);
    }

    .mkr-btn:hover {
      transform: translateY(-1px);
    }

    .mkr-viewport {
      position: relative;
      height: 260px;
      border-radius: 12px;
      overflow: hidden;
      border: 1px solid rgba(17, 49, 68, 0.2);
      background: linear-gradient(160deg, rgba(16, 36, 52, 0.98), rgba(34, 56, 70, 0.98));
    }

    .mkr-viewport-note {
      position: absolute;
      left: 10px;
      bottom: 8px;
      padding: 3px 7px;
      font-size: 10px;
      letter-spacing: 0.05em;
      text-transform: uppercase;
      border-radius: 999px;
      color: #cde6f4;
      background: rgba(12, 18, 24, 0.42);
      border: 1px solid rgba(255, 255, 255, 0.12);
      pointer-events: none;
    }

    .mkr-group-chip {
      margin: 8px 0 2px;
      padding: 4px 8px;
      border-radius: 999px;
      width: fit-content;
      font-size: 10px;
      text-transform: uppercase;
      letter-spacing: 0.1em;
      color: #27465a;
      background: rgba(45, 156, 143, 0.15);
      border: 1px solid rgba(45, 156, 143, 0.26);
    }

    .mkr-error {
      color: #9f1f0f;
      font-weight: 700;
      font-size: 12px;
      background: rgba(255, 95, 67, 0.12);
      border: 1px solid rgba(217, 87, 59, 0.3);
      border-radius: 10px;
      padding: 8px;
    }

    @media (max-width: 768px) {
      .mkr-panel {
        width: min(100%, 100vw - 20px);
        max-height: 78vh;
      }

      .mkr-control {
        grid-template-columns: 90px 1fr auto;
      }
    }

    @keyframes mkr-panel-rise {
      from { transform: translateY(6px) scale(0.99); opacity: 0; }
      to { transform: translateY(0) scale(1); opacity: 1; }
    }

    @keyframes mkr-section-in {
      from { transform: translateY(5px); opacity: 0; }
      to { transform: translateY(0); opacity: 1; }
    }
  `;

  document.head.appendChild(style);
}

export function createPanelShell({ kicker, title, subtitle }) {
  const panel = el("div", "mkr-panel");
  const header = el("div", "mkr-header");
  header.appendChild(el("div", "mkr-kicker", kicker));
  header.appendChild(el("h3", "mkr-title", title));
  if (subtitle) header.appendChild(el("p", "mkr-subtitle", subtitle));
  panel.appendChild(header);
  return { panel, header };
}

export function createSection({ title, note, delayMs = 0 }) {
  const section = el("section", "mkr-section");
  section.style.setProperty("--mkr-delay", `${Math.max(0, delayMs)}ms`);

  const head = el("div", "mkr-section-head");
  head.appendChild(el("h4", "mkr-section-title", title));
  if (note) head.appendChild(el("p", "mkr-section-note", note));
  section.appendChild(head);

  const body = el("div", "mkr-stack");
  section.appendChild(body);
  return { section, body };
}

export function createViewport(noteText) {
  const viewport = el("div", "mkr-viewport");
  if (noteText) {
    viewport.appendChild(el("div", "mkr-viewport-note", noteText));
  }
  return viewport;
}

export function createError(text) {
  return el("div", "mkr-error", text);
}

export function createSliderControl({ label, min, max, step, value, decimals = 2, onChange }) {
  const row = el("div", "mkr-control");
  const labelNode = el("label", "mkr-label", label);
  row.appendChild(labelNode);

  const range = document.createElement("input");
  range.type = "range";
  range.className = "mkr-range";
  range.min = String(min);
  range.max = String(max);
  range.step = String(step);
  range.value = String(value);

  const number = document.createElement("input");
  number.type = "number";
  number.className = "mkr-number";
  number.min = String(min);
  number.max = String(max);
  number.step = String(step);
  number.value = String(value);

  const parse = (raw) => {
    const v = Number.parseFloat(raw);
    if (!Number.isFinite(v)) return Number.parseFloat(range.value);
    return clamp(v, min, max);
  };

  const commit = (next) => {
    const rounded = Number.isFinite(next) ? Number(next.toFixed(decimals)) : value;
    range.value = String(rounded);
    number.value = String(rounded);
    onChange?.(rounded);
  };

  range.addEventListener("input", () => commit(parse(range.value)));
  number.addEventListener("change", () => commit(parse(number.value)));

  row.appendChild(range);
  row.appendChild(number);

  return {
    element: row,
    labelNode,
    setValue(next) {
      commit(next);
    },
    setLabel(next) {
      labelNode.textContent = next;
    },
  };
}

export function createVec3Control({ label, value, step = 0.05, onChange }) {
  const row = el("div", "mkr-control");
  row.appendChild(el("label", "mkr-label", label));

  const triplet = el("div", "mkr-triplet");
  const inputs = [0, 1, 2].map((i) => {
    const input = document.createElement("input");
    input.type = "number";
    input.className = "mkr-number";
    input.step = String(step);
    input.value = String(value[i] ?? 0);
    input.addEventListener("change", () => {
      const next = Number.parseFloat(input.value);
      if (!Number.isFinite(next)) {
        input.value = String(value[i] ?? 0);
        return;
      }
      value[i] = next;
      onChange?.(value);
    });
    triplet.appendChild(input);
    return input;
  });

  row.appendChild(triplet);
  row.appendChild(document.createElement("span"));

  return {
    element: row,
    setValue(next) {
      for (let i = 0; i < 3; i += 1) {
        value[i] = Number.isFinite(next[i]) ? next[i] : value[i];
        inputs[i].value = String(value[i]);
      }
      onChange?.(value);
    },
  };
}

export function createSelectControl({ label, value, options, onChange }) {
  const row = el("div", "mkr-control");
  row.appendChild(el("label", "mkr-label", label));

  const select = document.createElement("select");
  select.className = "mkr-select";
  for (const option of options) {
    const opt = document.createElement("option");
    opt.value = option.value;
    opt.textContent = option.label;
    select.appendChild(opt);
  }
  select.value = value;
  select.addEventListener("change", () => onChange?.(select.value));

  row.appendChild(select);
  row.appendChild(document.createElement("span"));

  return { element: row, select };
}

export function createTextControl({ label, value, placeholder = "", onChange }) {
  const row = el("div", "mkr-control");
  row.appendChild(el("label", "mkr-label", label));

  const input = document.createElement("input");
  input.type = "text";
  input.className = "mkr-input";
  input.value = value || "";
  input.placeholder = placeholder;
  input.addEventListener("change", () => onChange?.(input.value));

  row.appendChild(input);
  row.appendChild(document.createElement("span"));

  return { element: row, input };
}

export function createToggleControl({ label, checked, onChange }) {
  const row = el("div", "mkr-control");
  row.appendChild(el("label", "mkr-label", label));

  const wrap = el("div", "mkr-toggle-wrap");
  const checkbox = document.createElement("input");
  checkbox.type = "checkbox";
  checkbox.className = "mkr-toggle";
  checkbox.checked = !!checked;
  checkbox.addEventListener("change", () => onChange?.(checkbox.checked));
  wrap.appendChild(checkbox);
  wrap.appendChild(el("span", "mkr-section-note", checked ? "On" : "Off"));

  checkbox.addEventListener("change", () => {
    wrap.lastChild.textContent = checkbox.checked ? "On" : "Off";
  });

  row.appendChild(wrap);
  row.appendChild(document.createElement("span"));

  return { element: row, checkbox };
}

export function createButtonRow(buttons) {
  const row = el("div", "mkr-btn-row");
  for (const btn of buttons) {
    const node = document.createElement("button");
    node.className = "mkr-btn";
    node.textContent = btn.label;
    if (btn.tone) node.dataset.tone = btn.tone;
    node.addEventListener("click", (event) => {
      event.preventDefault();
      btn.onClick?.();
    });
    row.appendChild(node);
  }
  return row;
}

export function createGroupChip(text) {
  return el("div", "mkr-group-chip", text);
}
