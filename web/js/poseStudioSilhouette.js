const SEGMENT_DEFS = [
  ["pelvis", "spine", "torso"],
  ["spine", "chest", "torso"],
  ["chest", "neck", "torso"],
  ["chest", "shoulder_l", "shoulder"],
  ["shoulder_l", "elbow_l", "armUpper"],
  ["elbow_l", "wrist_l", "armLower"],
  ["wrist_l", "hand_l", "hand"],
  ["chest", "shoulder_r", "shoulder"],
  ["shoulder_r", "elbow_r", "armUpper"],
  ["elbow_r", "wrist_r", "armLower"],
  ["wrist_r", "hand_r", "hand"],
  ["pelvis", "hip_l", "hip"],
  ["hip_l", "knee_l", "legUpper"],
  ["knee_l", "ankle_l", "legLower"],
  ["ankle_l", "toe_l", "foot"],
  ["pelvis", "hip_r", "hip"],
  ["hip_r", "knee_r", "legUpper"],
  ["knee_r", "ankle_r", "legLower"],
  ["ankle_r", "toe_r", "foot"],
];

const VARIANTS = {
  female: {
    torso: 0.095,
    shoulder: 0.07,
    armUpper: 0.058,
    armLower: 0.045,
    hand: 0.04,
    hip: 0.078,
    legUpper: 0.072,
    legLower: 0.054,
    foot: 0.045,
    chestScale: [0.34, 0.34, 0.22],
    pelvisScale: [0.3, 0.24, 0.22],
    headScale: [0.145, 0.18, 0.145],
  },
  male: {
    torso: 0.108,
    shoulder: 0.082,
    armUpper: 0.064,
    armLower: 0.05,
    hand: 0.044,
    hip: 0.074,
    legUpper: 0.078,
    legLower: 0.058,
    foot: 0.05,
    chestScale: [0.38, 0.36, 0.25],
    pelvisScale: [0.3, 0.22, 0.2],
    headScale: [0.15, 0.185, 0.15],
  },
};

const CUSTOM_PART_NAMES = ["torso", "shoulder", "armUpper", "armLower", "hand", "hip", "legUpper", "legLower", "foot", "chest", "pelvis", "head"];
const gltfCache = new Map();
let GLTFLoaderMod = null;

function applyScale(mesh, scale) {
  mesh.scale.set(scale[0], scale[1], scale[2]);
}

async function loadGltfLoader() {
  if (GLTFLoaderMod) return GLTFLoaderMod;
  GLTFLoaderMod = await import("https://unpkg.com/three@0.160.0/examples/jsm/loaders/GLTFLoader.js");
  return GLTFLoaderMod;
}

function collectCustomParts(root) {
  const parts = new Map();
  root.traverse((node) => {
    if (!node?.isMesh || !node.name) return;
    const key = String(node.name).trim();
    if (CUSTOM_PART_NAMES.includes(key) && !parts.has(key)) {
      parts.set(key, node);
    }
  });
  return parts;
}

async function loadCustomPartSet(url) {
  const cacheKey = String(url || "").trim();
  if (!cacheKey) return null;
  if (gltfCache.has(cacheKey)) return gltfCache.get(cacheKey);
  const { GLTFLoader } = await loadGltfLoader();
  const loader = new GLTFLoader();
  const asset = await new Promise((resolve, reject) => {
    loader.load(cacheKey, resolve, undefined, reject);
  });
  const parts = collectCustomParts(asset.scene);
  gltfCache.set(cacheKey, parts);
  return parts;
}

function applyPartGeometry(targetMesh, sourceMesh) {
  if (!targetMesh || !sourceMesh?.geometry) return;
  targetMesh.geometry = sourceMesh.geometry.clone();
}

function captureDefaultGeometry(mesh) {
  return mesh?.geometry?.clone ? mesh.geometry.clone() : null;
}

function restoreGeometry(mesh, geometry) {
  if (!mesh || !geometry) return;
  mesh.geometry = geometry.clone();
}

function setSegmentTransform(three, mesh, a, b, radius) {
  const av = new three.Vector3(a[0], a[1], a[2]);
  const bv = new three.Vector3(b[0], b[1], b[2]);
  const delta = bv.clone().sub(av);
  const length = Math.max(0.0001, delta.length());
  mesh.position.copy(av.clone().add(bv).multiplyScalar(0.5));
  mesh.scale.set(radius, length * 0.5, radius);
  mesh.quaternion.setFromUnitVectors(new three.Vector3(0, 1, 0), delta.normalize());
}

export function createPoseSilhouette(three, variantKey = "female") {
  const variant = VARIANTS[variantKey] || VARIANTS.female;
  const group = new three.Group();

  const bodyMaterial = new three.MeshStandardMaterial({
    color: 0xc9d1d7,
    roughness: 0.92,
    metalness: 0.0,
    transparent: true,
    opacity: 0.52,
  });
  const depthMaterial = new three.MeshDepthMaterial({ depthPacking: three.RGBADepthPacking });

  const segmentGeometry = new three.CylinderGeometry(1, 1, 2, 18, 1, true);
  const ellipsoidGeometry = new three.SphereGeometry(1, 24, 18);
  const segments = [];
  const meshByKind = new Map();

  for (const [start, end, kind] of SEGMENT_DEFS) {
    const mesh = new three.Mesh(segmentGeometry, bodyMaterial);
    mesh.userData.kind = kind;
    mesh.userData.radius = variant[kind] || 0.06;
    group.add(mesh);
    segments.push({ start, end, kind, mesh });
    if (!meshByKind.has(kind)) meshByKind.set(kind, []);
    meshByKind.get(kind).push(mesh);
  }

  const chest = new three.Mesh(ellipsoidGeometry, bodyMaterial);
  const pelvis = new three.Mesh(ellipsoidGeometry, bodyMaterial);
  const head = new three.Mesh(ellipsoidGeometry, bodyMaterial);
  applyScale(chest, variant.chestScale);
  applyScale(pelvis, variant.pelvisScale);
  applyScale(head, variant.headScale);
  group.add(chest);
  group.add(pelvis);
  group.add(head);

  return {
    group,
    variantKey,
    bodyMaterial,
    depthMaterial,
    segments,
    meshByKind,
    chest,
    pelvis,
    head,
    defaultGeometries: {
      segments: segments.map((entry) => captureDefaultGeometry(entry.mesh)),
      chest: captureDefaultGeometry(chest),
      pelvis: captureDefaultGeometry(pelvis),
      head: captureDefaultGeometry(head),
    },
    customAssetUrl: "",
    customPartsApplied: false,
  };
}

export function setPoseSilhouetteVariant(instance, three, variantKey = "female") {
  instance.variantKey = VARIANTS[variantKey] ? variantKey : "female";
  const variant = VARIANTS[instance.variantKey];
  for (const segment of instance.segments) {
    segment.mesh.userData.radius = variant[segment.kind] || 0.06;
  }
  applyScale(instance.chest, variant.chestScale);
  applyScale(instance.pelvis, variant.pelvisScale);
  applyScale(instance.head, variant.headScale);
}

export function updatePoseSilhouette(instance, three, points) {
  for (const segment of instance.segments) {
    const a = points[segment.start];
    const b = points[segment.end];
    if (!a || !b) continue;
    setSegmentTransform(three, segment.mesh, a, b, segment.mesh.userData.radius || 0.06);
  }
  const chestPoint = points.chest;
  const pelvisPoint = points.pelvis;
  const headPoint = points.head;
  if (chestPoint) instance.chest.position.set(chestPoint[0], chestPoint[1], chestPoint[2]);
  if (pelvisPoint) instance.pelvis.position.set(pelvisPoint[0], pelvisPoint[1], pelvisPoint[2]);
  if (headPoint) instance.head.position.set(headPoint[0], headPoint[1], headPoint[2]);
}

export function applyPoseDisplayMode(instance, mode = "bones_only") {
  const meshVisible = mode === "bones_mesh" || mode === "depth_mesh";
  instance.group.visible = meshVisible;
  const activeMaterial = mode === "depth_mesh" ? instance.depthMaterial : instance.bodyMaterial;
  for (const segment of instance.segments) {
    segment.mesh.material = activeMaterial;
  }
  instance.chest.material = activeMaterial;
  instance.pelvis.material = activeMaterial;
  instance.head.material = activeMaterial;
}

export async function applyCustomSilhouetteAsset(instance, three, assetUrl) {
  const nextUrl = String(assetUrl || "").trim();
  if (!nextUrl) {
    instance.customAssetUrl = "";
    instance.customPartsApplied = false;
    return false;
  }
  const parts = await loadCustomPartSet(nextUrl);
  if (!parts || !parts.size) return false;

  for (const kind of ["torso", "shoulder", "armUpper", "armLower", "hand", "hip", "legUpper", "legLower", "foot"]) {
    const source = parts.get(kind);
    if (!source) continue;
    for (const mesh of instance.meshByKind.get(kind) || []) {
      applyPartGeometry(mesh, source);
    }
  }
  if (parts.get("chest")) applyPartGeometry(instance.chest, parts.get("chest"));
  if (parts.get("pelvis")) applyPartGeometry(instance.pelvis, parts.get("pelvis"));
  if (parts.get("head")) applyPartGeometry(instance.head, parts.get("head"));

  instance.customAssetUrl = nextUrl;
  instance.customPartsApplied = true;
  return true;
}

export function restoreDefaultSilhouetteGeometry(instance) {
  if (!instance?.defaultGeometries) return;
  instance.segments.forEach((segment, index) => restoreGeometry(segment.mesh, instance.defaultGeometries.segments[index]));
  restoreGeometry(instance.chest, instance.defaultGeometries.chest);
  restoreGeometry(instance.pelvis, instance.defaultGeometries.pelvis);
  restoreGeometry(instance.head, instance.defaultGeometries.head);
  instance.customAssetUrl = "";
  instance.customPartsApplied = false;
}
