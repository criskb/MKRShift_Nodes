import { app } from "../../../scripts/app.js";
import {
  clamp,
  createButtonRow,
  createError,
  createPanelShell,
  createSection,
  createSelectControl,
  createSliderControl,
  createToggleControl,
  createViewport,
  ensureMkrUIStyles,
} from "./uiSystem.js";

const EXT = "mkr.angleshift";
const SETTINGS_SCHEMA_VERSION = 3;

let THREE = null;
let OrbitControls = null;

async function loadThree() {
  if (THREE && OrbitControls) return { THREE, OrbitControls };
  THREE = await import("https://unpkg.com/three@0.160.0/build/three.module.js");
  const controls = await import("https://unpkg.com/three@0.160.0/examples/jsm/controls/OrbitControls.js");
  OrbitControls = controls.OrbitControls;
  return { THREE, OrbitControls };
}

function syncLegacyAngleFields(data) {
  if (!data.angle || typeof data.angle !== "object" || Array.isArray(data.angle)) data.angle = {};
  const angle = data.angle;

  angle.rotation = Number.isFinite(angle.rotation) ? angle.rotation : Number(data.rotation ?? 45);
  angle.tilt = Number.isFinite(angle.tilt) ? angle.tilt : Number(data.tilt ?? -30);
  angle.zoom = Number.isFinite(angle.zoom) ? angle.zoom : Number(data.zoom ?? 0);
  angle.strength = Number.isFinite(angle.strength) ? angle.strength : Number(data.strength ?? 0.85);
  angle.background_mode = typeof angle.background_mode === "string" ? angle.background_mode : String(data.background_mode ?? "blur");
  angle.sheet_columns = Number.isFinite(angle.sheet_columns) ? Math.round(angle.sheet_columns) : Number(data.sheet_columns ?? 4);
  angle.label_overlay = typeof angle.label_overlay === "boolean" ? angle.label_overlay : !!data.label_overlay;
  angle.multi12 = typeof angle.multi12 === "boolean" ? angle.multi12 : !!data.multi12;

  angle.rotation = ((angle.rotation % 360) + 360) % 360;
  angle.tilt = clamp(angle.tilt, -90, 90);
  angle.zoom = clamp(angle.zoom, -1, 1);
  angle.strength = clamp(angle.strength, 0, 1.5);
  angle.sheet_columns = Math.max(3, Math.min(6, Math.round(angle.sheet_columns)));

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

  syncLegacyAngleFields(data);

  return { widget, data };
}

function writeSettings(node, widget, data) {
  syncLegacyAngleFields(data);
  widget.value = JSON.stringify(data);
  node.setDirtyCanvas(true, true);
}

function deg(rad) {
  return (rad * 180) / Math.PI;
}

function rad(degVal) {
  return (degVal * Math.PI) / 180;
}

function calcCameraPosFromAngles(rotation, tilt, zoom) {
  const distance = clamp(2.0 - zoom * 0.9, 0.8, 4.0);
  const yaw = rad(rotation);
  const pitch = rad(tilt);

  return {
    x: distance * Math.sin(yaw) * Math.cos(pitch),
    y: distance * Math.sin(pitch),
    z: distance * Math.cos(yaw) * Math.cos(pitch),
  };
}

function makeCameraIcon(three) {
  const group = new three.Group();

  const body = new three.Mesh(
    new three.BoxGeometry(0.12, 0.08, 0.06),
    new three.MeshBasicMaterial({ color: 0xfff2d6, wireframe: true, transparent: true, opacity: 0.9 })
  );
  group.add(body);

  const lens = new three.Mesh(
    new three.CylinderGeometry(0.02, 0.02, 0.05, 10),
    new three.MeshBasicMaterial({ color: 0xfff2d6, wireframe: true, transparent: true, opacity: 0.9 })
  );
  lens.rotation.x = Math.PI / 2;
  lens.position.z = 0.05;
  group.add(lens);

  return group;
}

function makePanel(node) {
  ensureMkrUIStyles();

  const { panel } = createPanelShell({
    kicker: "MKR Shift v3",
    title: "AngleShift Director",
    subtitle: "Orbit in 3D, then generate perspective-warped views and contact sheets.",
  });

  const { widget, data } = ensureSettings(node);
  if (!widget) {
    panel.appendChild(createError("settings_json widget not found."));
    return panel;
  }

  let muteCommit = false;
  let scene = null;
  let renderer = null;
  let camera = null;
  let controls = null;
  let imagePlane = null;
  let multiGroup = null;

  function commit() {
    if (muteCommit) return;
    writeSettings(node, widget, data);
    updateMultiCams();
  }

  const stageSection = createSection({ title: "3D Orbit", note: "Drag to steer", delayMs: 20 });
  const viewport = createViewport("orbit camera path");
  stageSection.body.appendChild(viewport);
  panel.appendChild(stageSection.section);

  const modeSection = createSection({ title: "Mode", note: "Batch behavior", delayMs: 55 });
  modeSection.body.appendChild(
    createToggleControl({
      label: "12-angle batch",
      checked: !!data.angle.multi12,
      onChange: (checked) => {
        data.angle.multi12 = checked;
        commit();
      },
    }).element
  );
  panel.appendChild(modeSection.section);

  const controlsSection = createSection({ title: "Camera Controls", note: "Primary", delayMs: 90 });

  const rotControl = createSliderControl({
    label: "Rotation",
    min: 0,
    max: 360,
    step: 1,
    value: Number(data.angle.rotation),
    decimals: 0,
    onChange: (next) => {
      data.angle.rotation = next;
      syncCameraFromData();
      commit();
    },
  });

  const tiltControl = createSliderControl({
    label: "Tilt",
    min: -90,
    max: 90,
    step: 1,
    value: Number(data.angle.tilt),
    decimals: 0,
    onChange: (next) => {
      data.angle.tilt = next;
      syncCameraFromData();
      commit();
    },
  });

  const zoomControl = createSliderControl({
    label: "Zoom",
    min: -1,
    max: 1,
    step: 0.01,
    value: Number(data.angle.zoom),
    decimals: 2,
    onChange: (next) => {
      data.angle.zoom = next;
      syncCameraFromData();
      commit();
    },
  });

  const strengthControl = createSliderControl({
    label: "Warp",
    min: 0,
    max: 1.5,
    step: 0.01,
    value: Number(data.angle.strength),
    decimals: 2,
    onChange: (next) => {
      data.angle.strength = next;
      commit();
    },
  });

  const columnsControl = createSliderControl({
    label: "Sheet Cols",
    min: 3,
    max: 6,
    step: 1,
    value: Number(data.angle.sheet_columns),
    decimals: 0,
    onChange: (next) => {
      data.angle.sheet_columns = Math.round(next);
      commit();
    },
  });

  controlsSection.body.appendChild(rotControl.element);
  controlsSection.body.appendChild(tiltControl.element);
  controlsSection.body.appendChild(zoomControl.element);
  controlsSection.body.appendChild(strengthControl.element);
  controlsSection.body.appendChild(columnsControl.element);

  controlsSection.body.appendChild(
    createSelectControl({
      label: "Background",
      value: data.angle.background_mode,
      options: [
        { value: "blur", label: "Blur" },
        { value: "black", label: "Black" },
        { value: "gray", label: "Gray" },
        { value: "white", label: "White" },
      ],
      onChange: (next) => {
        data.angle.background_mode = next;
        commit();
      },
    }).element
  );

  controlsSection.body.appendChild(
    createToggleControl({
      label: "Sheet labels",
      checked: !!data.angle.label_overlay,
      onChange: (checked) => {
        data.angle.label_overlay = checked;
        commit();
      },
    }).element
  );

  panel.appendChild(controlsSection.section);

  const actionSection = createSection({ title: "Quick Actions", note: "Presets", delayMs: 125 });
  actionSection.body.appendChild(
    createButtonRow([
      {
        label: "Front",
        tone: "accent",
        onClick: () => {
          muteCommit = true;
          data.angle.rotation = 0;
          data.angle.tilt = -20;
          rotControl.setValue(0);
          tiltControl.setValue(-20);
          muteCommit = false;
          syncCameraFromData();
          commit();
        },
      },
      {
        label: "Three-Quarter",
        onClick: () => {
          muteCommit = true;
          data.angle.rotation = 35;
          data.angle.tilt = -25;
          rotControl.setValue(35);
          tiltControl.setValue(-25);
          muteCommit = false;
          syncCameraFromData();
          commit();
        },
      },
      {
        label: "Back",
        onClick: () => {
          muteCommit = true;
          data.angle.rotation = 180;
          data.angle.tilt = -18;
          rotControl.setValue(180);
          tiltControl.setValue(-18);
          muteCommit = false;
          syncCameraFromData();
          commit();
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

  function syncCameraFromData() {
    if (!camera || !controls) return;
    const p = calcCameraPosFromAngles(data.angle.rotation, data.angle.tilt, data.angle.zoom);
    camera.position.set(p.x, p.y, p.z);
    controls.update();
  }

  function updateMultiCams() {
    if (!scene || !THREE) return;

    if (multiGroup) {
      scene.remove(multiGroup);
      multiGroup = null;
    }

    if (!data.angle.multi12) return;

    multiGroup = new THREE.Group();
    const rots = [0, 30, 60, 90, 120, 150, 180, 210, 240, 270, 300, 330];

    for (const r of rots) {
      const icon = makeCameraIcon(THREE);
      const p = calcCameraPosFromAngles(r, data.angle.tilt, data.angle.zoom);
      icon.position.set(p.x, p.y, p.z);

      const lineGeo = new THREE.BufferGeometry().setFromPoints([
        new THREE.Vector3(p.x, p.y, p.z),
        new THREE.Vector3(0, 0, 0),
      ]);
      const line = new THREE.Line(
        lineGeo,
        new THREE.LineBasicMaterial({ color: 0xa5c7da, transparent: true, opacity: 0.32 })
      );

      multiGroup.add(line);
      multiGroup.add(icon);
    }

    scene.add(multiGroup);
  }

  async function initThree() {
    const mods = await loadThree();
    const three = mods.THREE;

    scene = new three.Scene();

    camera = new three.PerspectiveCamera(45, 1, 0.01, 100);
    syncCameraFromData();
    camera.lookAt(0, 0, 0);

    renderer = new three.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(window.devicePixelRatio || 1);
    renderer.setSize(viewport.clientWidth, viewport.clientHeight);
    viewport.innerHTML = "";
    viewport.appendChild(renderer.domElement);
    viewport.appendChild(document.createElement("div")).className = "mkr-viewport-note";
    viewport.lastChild.textContent = "orbit camera path";

    controls = new mods.OrbitControls(camera, renderer.domElement);
    controls.enablePan = false;
    controls.enableZoom = false;
    controls.enableDamping = true;
    controls.target.set(0, 0, 0);
    controls.update();

    scene.add(new three.AmbientLight(0xe6f2fc, 0.9));

    const wireSphere = new three.Mesh(
      new three.SphereGeometry(1.1, 24, 16),
      new three.MeshBasicMaterial({ color: 0xffd08b, wireframe: true, transparent: true, opacity: 0.22 })
    );
    scene.add(wireSphere);

    const baseRing = new three.Mesh(
      new three.RingGeometry(1.05, 1.08, 60),
      new three.MeshBasicMaterial({ color: 0x9ccbe1, side: three.DoubleSide, transparent: true, opacity: 0.35 })
    );
    baseRing.rotation.x = Math.PI / 2;
    scene.add(baseRing);

    const planeGeo = new three.PlaneGeometry(0.62, 0.62);
    const planeMat = new three.MeshBasicMaterial({ color: 0xf8efe2, transparent: true, opacity: 0.95 });
    imagePlane = new three.Mesh(planeGeo, planeMat);
    scene.add(imagePlane);

    controls.addEventListener("change", () => {
      const v = camera.position.clone();
      const dist = Math.max(1e-6, v.length());

      const yaw = (deg(Math.atan2(v.x, v.z)) + 360) % 360;
      const pitch = deg(Math.asin(clamp(v.y / dist, -1, 1)));

      muteCommit = true;
      data.angle.rotation = yaw;
      data.angle.tilt = pitch;
      rotControl.setValue(Math.round(yaw));
      tiltControl.setValue(Math.round(pitch));
      muteCommit = false;

      commit();
    });

    const resize = () => {
      const width = Math.max(120, viewport.clientWidth);
      const height = Math.max(120, viewport.clientHeight);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
      renderer.setSize(width, height);
    };
    window.addEventListener("resize", resize);
    resize();

    const tick = () => {
      requestAnimationFrame(tick);
      controls?.update();
      if (imagePlane) imagePlane.lookAt(camera.position);
      renderer?.render(scene, camera);
    };
    tick();

    updateMultiCams();
    syncCameraFromData();
  }

  initThree().catch((error) => {
    console.warn("AngleShift preview init failed:", error);
    viewport.innerHTML = "";
    viewport.appendChild(createError("3D preview failed to load (check console)."));
  });

  commit();
  return panel;
}

app.registerExtension({
  name: EXT,

  async nodeCreated(node) {
    if (node.comfyClass !== "AngleShift") return;

    const panel = makePanel(node);

    if (node.addDOMWidget) {
      node.addDOMWidget("angleshift_panel_v3", "DOM", panel);
    } else {
      node.addCustomWidget({
        name: "angleshift_panel_v3",
        type: "dom",
        draw: function () {},
        getHeight: function () {
          return 760;
        },
        getWidth: function () {
          return 470;
        },
        element: panel,
      });
    }

    node.setDirtyCanvas(true, true);
  },
});
