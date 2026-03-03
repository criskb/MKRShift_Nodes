import { app } from "../../../scripts/app.js";
import {
  createButtonRow,
  createError,
  createGroupChip,
  createPanelShell,
  createSection,
  createSelectControl,
  createSliderControl,
  createTextControl,
  createVec3Control,
  createViewport,
  ensureMkrUIStyles,
} from "./uiSystem.js";

const EXT = "mkr.character_customizer.proto";
const SETTINGS_SCHEMA_VERSION = 3;

let THREE = null;
let GLTFLoader = null;
let OrbitControls = null;

function decimalsFromStep(step) {
  const text = String(step ?? "0.01");
  const idx = text.indexOf(".");
  return idx < 0 ? 0 : Math.min(5, text.length - idx - 1);
}

async function fetchParamsConfig() {
  const url = new URL("../config/params.json", import.meta.url);
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Failed to load params.json: ${response.status}`);
  }
  const data = await response.json();
  if (!data || typeof data !== "object" || Array.isArray(data)) {
    throw new Error("params.json must be a JSON object");
  }
  if (!Array.isArray(data.params)) data.params = [];
  return data;
}

function syncLegacyAngleFields(data) {
  if (!data.angle || typeof data.angle !== "object" || Array.isArray(data.angle)) {
    data.angle = {};
  }
  const angle = data.angle;
  angle.rotation = Number.isFinite(angle.rotation) ? angle.rotation : 45;
  angle.tilt = Number.isFinite(angle.tilt) ? angle.tilt : -30;
  angle.zoom = Number.isFinite(angle.zoom) ? angle.zoom : 0;
  angle.strength = Number.isFinite(angle.strength) ? angle.strength : 0.85;
  angle.background_mode = typeof angle.background_mode === "string" ? angle.background_mode : "blur";
  angle.sheet_columns = Number.isFinite(angle.sheet_columns) ? Math.round(angle.sheet_columns) : 4;
  angle.label_overlay = !!angle.label_overlay;
  angle.multi12 = !!angle.multi12;

  data.rotation = angle.rotation;
  data.tilt = angle.tilt;
  data.zoom = angle.zoom;
  data.strength = angle.strength;
  data.background_mode = angle.background_mode;
  data.sheet_columns = angle.sheet_columns;
  data.label_overlay = angle.label_overlay;
  data.multi12 = angle.multi12;
}

function ensureSettings(node) {
  const widget = node.widgets?.find((w) => w.name === "settings_json");
  let data = {};
  try {
    data = widget?.value ? JSON.parse(widget.value) : {};
  } catch {
    data = {};
  }

  if (!data || typeof data !== "object" || Array.isArray(data)) data = {};
  data.schema_version = SETTINGS_SCHEMA_VERSION;

  if (!data.params || typeof data.params !== "object" || Array.isArray(data.params)) data.params = {};

  if (!data.camera || typeof data.camera !== "object" || Array.isArray(data.camera)) data.camera = {};
  if (!Array.isArray(data.camera.pos) || data.camera.pos.length !== 3) data.camera.pos = [0, 2.0, 1.4];

  if (!data.light || typeof data.light !== "object" || Array.isArray(data.light)) data.light = {};
  if (!Array.isArray(data.light.pos) || data.light.pos.length !== 3) data.light.pos = [1.2, 2.2, 2.0];

  if (!data.gizmos || typeof data.gizmos !== "object" || Array.isArray(data.gizmos)) data.gizmos = {};
  if (!data.gizmos.camera || typeof data.gizmos.camera !== "object" || Array.isArray(data.gizmos.camera)) {
    data.gizmos.camera = {};
  }
  if (!data.gizmos.light || typeof data.gizmos.light !== "object" || Array.isArray(data.gizmos.light)) {
    data.gizmos.light = {};
  }
  data.gizmos.camera.mode = data.gizmos.camera.mode === "glb" ? "glb" : "procedural";
  data.gizmos.light.mode = data.gizmos.light.mode === "glb" ? "glb" : "procedural";
  if (typeof data.gizmos.camera.glb_url !== "string") data.gizmos.camera.glb_url = "";
  if (typeof data.gizmos.light.glb_url !== "string") data.gizmos.light.glb_url = "";

  syncLegacyAngleFields(data);

  return { widget, data };
}

function writeSettings(node, widget, data) {
  syncLegacyAngleFields(data);
  widget.value = JSON.stringify(data);
  node.setDirtyCanvas(true, true);
}

async function loadThree() {
  if (THREE && GLTFLoader && OrbitControls) {
    return { THREE, GLTFLoader, OrbitControls };
  }

  const threeMod = await import("https://unpkg.com/three@0.160.0/build/three.module.js");
  const gltfMod = await import("https://unpkg.com/three@0.160.0/examples/jsm/loaders/GLTFLoader.js");
  const orbitMod = await import("https://unpkg.com/three@0.160.0/examples/jsm/controls/OrbitControls.js");

  THREE = threeMod;
  GLTFLoader = gltfMod.GLTFLoader;
  OrbitControls = orbitMod.OrbitControls;
  return { THREE, GLTFLoader, OrbitControls };
}

function makeProceduralCameraGizmo(three) {
  const group = new three.Group();

  const body = new three.Mesh(
    new three.BoxGeometry(0.16, 0.1, 0.12),
    new three.MeshStandardMaterial({ color: 0x66c6c8, metalness: 0.12, roughness: 0.38 })
  );
  group.add(body);

  const linesGeo = new three.BufferGeometry();
  const points = [
    new three.Vector3(0, 0, 0.08),
    new three.Vector3(-0.2, -0.13, -0.24),
    new three.Vector3(0.2, -0.13, -0.24),
    new three.Vector3(0.2, 0.13, -0.24),
    new three.Vector3(-0.2, 0.13, -0.24),
  ];

  const segments = [
    [0, 1], [0, 2], [0, 3], [0, 4],
    [1, 2], [2, 3], [3, 4], [4, 1],
  ];

  const verts = [];
  for (const [a, b] of segments) {
    verts.push(points[a].x, points[a].y, points[a].z);
    verts.push(points[b].x, points[b].y, points[b].z);
  }
  linesGeo.setAttribute("position", new three.Float32BufferAttribute(verts, 3));

  const wire = new three.LineSegments(linesGeo, new three.LineBasicMaterial({ color: 0xa9edf2 }));
  group.add(wire);

  return group;
}

function makeProceduralLightGizmo(three) {
  const group = new three.Group();

  const bulb = new three.Mesh(
    new three.SphereGeometry(0.085, 20, 14),
    new three.MeshStandardMaterial({ color: 0xf4bc6a, emissive: 0x6b3e19, emissiveIntensity: 0.55 })
  );
  group.add(bulb);

  const stem = new three.Mesh(
    new three.CylinderGeometry(0.022, 0.022, 0.16, 12),
    new three.MeshStandardMaterial({ color: 0xe5ebee, metalness: 0.18, roughness: 0.5 })
  );
  stem.position.set(0, -0.14, 0);
  group.add(stem);

  const arrow = new three.ArrowHelper(
    new three.Vector3(0, -1, 0),
    new three.Vector3(0, 0.025, 0),
    0.3,
    0xf39f4d
  );
  group.add(arrow);

  return group;
}

async function loadGLBGizmo({ GLTFLoader }, url) {
  return new Promise((resolve, reject) => {
    const loader = new GLTFLoader();
    loader.load(
      url,
      (gltf) => {
        const root = gltf.scene || gltf.scenes?.[0];
        if (!root) {
          reject(new Error("GLB scene not found"));
          return;
        }
        root.traverse((obj) => {
          if (obj.isMesh) {
            obj.castShadow = true;
            obj.receiveShadow = true;
          }
        });
        root.userData.__isGLB = true;
        resolve(root);
      },
      undefined,
      reject
    );
  });
}

function mapScenePos(pos) {
  return [pos[0] ?? 0, pos[2] ?? 0, pos[1] ?? 0];
}

function makePanel(node, cfg) {
  ensureMkrUIStyles();

  const { panel } = createPanelShell({
    kicker: "MKR Shift v3",
    title: "Character Direction Studio",
    subtitle: "Block your camera and light, tune anatomy controls, and export a cleaner directing payload.",
  });

  const { widget, data } = ensureSettings(node);
  if (!widget) {
    panel.appendChild(createError("settings_json widget not found."));
    return panel;
  }

  for (const p of cfg.params || []) {
    if (!p || typeof p !== "object") continue;
    if (typeof p.key !== "string") continue;
    if (data.params[p.key] === undefined) data.params[p.key] = Number(p.default ?? 0);
  }

  let muteCommit = false;
  let scene = null;
  let previewCamera = null;
  let renderer = null;
  let controls = null;
  let rafId = 0;
  let previewLight = null;
  let camGizmo = null;
  let lightGizmo = null;

  function commit(refresh3D = false) {
    if (muteCommit) return;
    writeSettings(node, widget, data);
    if (refresh3D && scene) {
      loadThree().then(applyGizmos).catch(() => {});
    }
  }

  const stageSection = createSection({ title: "Scene Preview", note: "Realtime", delayMs: 20 });
  const viewport = createViewport("drag to orbit");
  stageSection.body.appendChild(viewport);
  panel.appendChild(stageSection.section);

  const sceneSection = createSection({ title: "Camera & Light", note: "XYZ", delayMs: 50 });
  const cameraControl = createVec3Control({
    label: "Camera",
    value: data.camera.pos,
    onChange: () => commit(true),
  });
  const lightControl = createVec3Control({
    label: "Light",
    value: data.light.pos,
    onChange: () => commit(true),
  });
  sceneSection.body.appendChild(cameraControl.element);
  sceneSection.body.appendChild(lightControl.element);

  const presetButtons = createButtonRow([
    {
      label: "Balanced",
      tone: "accent",
      onClick: () => {
        muteCommit = true;
        cameraControl.setValue([0, 2.0, 1.4]);
        lightControl.setValue([1.2, 2.2, 2.0]);
        muteCommit = false;
        commit(true);
      },
    },
    {
      label: "Hero",
      onClick: () => {
        muteCommit = true;
        cameraControl.setValue([0.35, 1.9, 1.15]);
        lightControl.setValue([1.8, 2.35, 2.35]);
        muteCommit = false;
        commit(true);
      },
    },
    {
      label: "Silhouette",
      onClick: () => {
        muteCommit = true;
        cameraControl.setValue([0, 2.1, 1.55]);
        lightControl.setValue([-1.9, 2.45, -2.1]);
        muteCommit = false;
        commit(true);
      },
    },
  ]);
  sceneSection.body.appendChild(presetButtons);
  panel.appendChild(sceneSection.section);

  const gizmoSection = createSection({ title: "Gizmos", note: "Procedural or GLB", delayMs: 85 });
  const camModeControl = createSelectControl({
    label: "Cam Gizmo",
    value: data.gizmos.camera.mode,
    options: [
      { value: "procedural", label: "Procedural" },
      { value: "glb", label: "Custom GLB" },
    ],
    onChange: (mode) => {
      data.gizmos.camera.mode = mode;
      commit(true);
    },
  });
  gizmoSection.body.appendChild(camModeControl.element);

  const camUrlControl = createTextControl({
    label: "Cam GLB",
    value: data.gizmos.camera.glb_url,
    placeholder: "/extensions/.../assets/camera.glb",
    onChange: (value) => {
      data.gizmos.camera.glb_url = value;
      commit(true);
    },
  });
  gizmoSection.body.appendChild(camUrlControl.element);

  const lightModeControl = createSelectControl({
    label: "Light Gizmo",
    value: data.gizmos.light.mode,
    options: [
      { value: "procedural", label: "Procedural" },
      { value: "glb", label: "Custom GLB" },
    ],
    onChange: (mode) => {
      data.gizmos.light.mode = mode;
      commit(true);
    },
  });
  gizmoSection.body.appendChild(lightModeControl.element);

  const lightUrlControl = createTextControl({
    label: "Light GLB",
    value: data.gizmos.light.glb_url,
    placeholder: "/extensions/.../assets/light.glb",
    onChange: (value) => {
      data.gizmos.light.glb_url = value;
      commit(true);
    },
  });
  gizmoSection.body.appendChild(lightUrlControl.element);

  panel.appendChild(gizmoSection.section);

  const paramSection = createSection({ title: "Morph Parameters", note: "Grouped", delayMs: 120 });
  const paramControls = new Map();
  let currentGroup = "";

  for (const spec of cfg.params || []) {
    if (!spec || typeof spec !== "object" || typeof spec.key !== "string") continue;

    const group = String(spec.group || "General");
    if (group !== currentGroup) {
      currentGroup = group;
      paramSection.body.appendChild(createGroupChip(group));
    }

    const slider = createSliderControl({
      label: spec.label || spec.key,
      min: Number(spec.min ?? 0),
      max: Number(spec.max ?? 1),
      step: Number(spec.step ?? 0.01),
      value: Number(data.params[spec.key] ?? spec.default ?? 0),
      decimals: decimalsFromStep(spec.step),
      onChange: (next) => {
        data.params[spec.key] = next;
        commit(false);
      },
    });

    paramControls.set(spec.key, slider);
    paramSection.body.appendChild(slider.element);
  }

  panel.appendChild(paramSection.section);

  const actionSection = createSection({ title: "Actions", note: "Utility", delayMs: 150 });
  actionSection.body.appendChild(
    createButtonRow([
      {
        label: "Reset All",
        tone: "accent",
        onClick: () => {
          muteCommit = true;

          for (const p of cfg.params || []) {
            if (!p || typeof p !== "object" || typeof p.key !== "string") continue;
            const next = Number(p.default ?? 0);
            data.params[p.key] = next;
            paramControls.get(p.key)?.setValue(next);
          }

          cameraControl.setValue([0, 2.0, 1.4]);
          lightControl.setValue([1.2, 2.2, 2.0]);
          data.gizmos.camera.mode = "procedural";
          data.gizmos.camera.glb_url = "";
          data.gizmos.light.mode = "procedural";
          data.gizmos.light.glb_url = "";
          camModeControl.select.value = "procedural";
          camUrlControl.input.value = "";
          lightModeControl.select.value = "procedural";
          lightUrlControl.input.value = "";

          muteCommit = false;
          commit(true);
        },
      },
      {
        label: "Copy JSON",
        onClick: async () => {
          try {
            await navigator.clipboard.writeText(JSON.stringify(data, null, 2));
          } catch {
            // no-op
          }
        },
      },
    ])
  );
  panel.appendChild(actionSection.section);

  async function initThree() {
    const mods = await loadThree();
    const { THREE: three, OrbitControls: orbit } = mods;

    scene = new three.Scene();
    scene.fog = new three.Fog(0x122332, 1.5, 11.0);

    previewCamera = new three.PerspectiveCamera(44, 1, 0.01, 100);
    previewCamera.position.set(0, 2.1, 3.6);
    previewCamera.lookAt(0, 1.0, 0);

    renderer = new three.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(window.devicePixelRatio || 1);
    renderer.setSize(viewport.clientWidth, viewport.clientHeight);
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = three.PCFSoftShadowMap;
    viewport.innerHTML = "";
    viewport.appendChild(renderer.domElement);
    viewport.appendChild(document.createElement("div")).className = "mkr-viewport-note";
    viewport.lastChild.textContent = "drag to orbit";

    controls = new orbit(previewCamera, renderer.domElement);
    controls.enablePan = false;
    controls.minDistance = 1.8;
    controls.maxDistance = 7.0;
    controls.target.set(0, 1.0, 0);
    controls.enableDamping = true;

    previewLight = new three.DirectionalLight(0xfff5e8, 1.22);
    previewLight.castShadow = true;
    scene.add(previewLight);

    scene.add(new three.AmbientLight(0xb6d2e0, 0.48));

    const rimLight = new three.DirectionalLight(0x9dc6e0, 0.25);
    rimLight.position.set(-2.1, 2.4, -2.6);
    scene.add(rimLight);

    const grid = new three.GridHelper(7, 28, 0x7ea4b8, 0x2a3a47);
    scene.add(grid);

    const body = new three.Mesh(
      new three.CapsuleGeometry(0.35, 1.05, 11, 20),
      new three.MeshStandardMaterial({ color: 0x8ea4b1, roughness: 0.78, metalness: 0.04 })
    );
    body.position.set(0, 1.03, 0);
    body.castShadow = true;
    body.receiveShadow = true;
    scene.add(body);

    const floor = new three.Mesh(
      new three.CircleGeometry(2.7, 44),
      new three.MeshStandardMaterial({ color: 0x1e2e3a, roughness: 0.95, metalness: 0.02 })
    );
    floor.rotation.x = -Math.PI / 2;
    floor.position.y = -0.01;
    floor.receiveShadow = true;
    scene.add(floor);

    const resize = () => {
      if (!renderer || !previewCamera) return;
      const width = Math.max(120, viewport.clientWidth);
      const height = Math.max(120, viewport.clientHeight);
      previewCamera.aspect = width / height;
      previewCamera.updateProjectionMatrix();
      renderer.setSize(width, height);
    };
    window.addEventListener("resize", resize);
    resize();

    const loop = () => {
      rafId = requestAnimationFrame(loop);
      controls?.update();
      renderer?.render(scene, previewCamera);
    };
    loop();

    await applyGizmos(mods);
  }

  async function replaceGizmo(current, next) {
    if (current) scene.remove(current);
    scene.add(next);
    return next;
  }

  async function applyGizmos(mods) {
    if (!scene || !mods?.THREE) return;
    const three = mods.THREE;

    const cameraPos = mapScenePos(data.camera.pos);
    const lightPos = mapScenePos(data.light.pos);

    if (previewLight) previewLight.position.set(lightPos[0], lightPos[1], lightPos[2]);

    if (data.gizmos.camera.mode === "glb" && data.gizmos.camera.glb_url) {
      try {
        const glb = await loadGLBGizmo(mods, data.gizmos.camera.glb_url);
        glb.scale.setScalar(0.35);
        camGizmo = await replaceGizmo(camGizmo, glb);
      } catch {
        camGizmo = await replaceGizmo(camGizmo, makeProceduralCameraGizmo(three));
      }
    } else if (!camGizmo || camGizmo.userData.__isGLB) {
      camGizmo = await replaceGizmo(camGizmo, makeProceduralCameraGizmo(three));
    }

    if (data.gizmos.light.mode === "glb" && data.gizmos.light.glb_url) {
      try {
        const glb = await loadGLBGizmo(mods, data.gizmos.light.glb_url);
        glb.scale.setScalar(0.35);
        lightGizmo = await replaceGizmo(lightGizmo, glb);
      } catch {
        lightGizmo = await replaceGizmo(lightGizmo, makeProceduralLightGizmo(three));
      }
    } else if (!lightGizmo || lightGizmo.userData.__isGLB) {
      lightGizmo = await replaceGizmo(lightGizmo, makeProceduralLightGizmo(three));
    }

    if (camGizmo) camGizmo.position.set(cameraPos[0], cameraPos[1], cameraPos[2]);
    if (lightGizmo) lightGizmo.position.set(lightPos[0], lightPos[1], lightPos[2]);
  }

  initThree().catch((error) => {
    console.warn("MKR Character preview init failed:", error);
    viewport.innerHTML = "";
    viewport.appendChild(createError("3D preview failed to load (check console)."));
  });

  commit(true);
  return panel;
}

app.registerExtension({
  name: EXT,

  async nodeCreated(node) {
    if (node.comfyClass !== "MKRCharacterCustomizer") return;

    let cfg;
    try {
      cfg = await fetchParamsConfig();
    } catch (error) {
      console.warn(error);
      cfg = { params: [] };
    }

    const panel = makePanel(node, cfg);

    if (node.addDOMWidget) {
      node.addDOMWidget("mkr_char_panel_v3", "DOM", panel);
    } else {
      node.addCustomWidget({
        name: "mkr_char_panel_v3",
        type: "dom",
        draw: function () {},
        getHeight: function () {
          return 860;
        },
        getWidth: function () {
          return 500;
        },
        element: panel,
      });
    }

    node.setDirtyCanvas(true, true);
  },
});
