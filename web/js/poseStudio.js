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
  createToggleControl,
  createViewport,
  ensureMkrUIStyles,
} from "./uiSystem.js";
import {
  applyPoseDisplayMode,
  applyCustomSilhouetteAsset,
  createPoseSilhouette,
  restoreDefaultSilhouetteGeometry,
  setPoseSilhouetteVariant,
  updatePoseSilhouette,
} from "./poseStudioSilhouette.js";

const EXT = "mkr.pose_studio";
const SETTINGS_SCHEMA_VERSION = 1;
const STYLE_ID = "mkr-pose-studio-theme-v3";
const DEFAULT_NODE_WIDTH = 340;
const DEFAULT_NODE_HEIGHT = 196;
const DOM_WIDGET_HEIGHT = 720;
const LAUNCHER_WIDGET_HEIGHT = 126;
const USER_PRESET_STORAGE_KEY = "mkr.poseStudio.userPresets.v1";
const FIT_VIEW = { yaw: 0, pitch: 0, zoom: 1, pan_x: 0, pan_y: 0 };
const FIT_CONTROL_WEIGHTS = {
  root_yaw: 0.8,
  root_pitch: 0.7,
  root_roll: 1.2,
  spine_bend: 0.8,
  spine_twist: 0.9,
  head_yaw: 0.5,
  head_pitch: 0.5,
  head_roll: 0.8,
  arm_raise_l: 0.4,
  arm_forward_l: 0.5,
  arm_twist_l: 0.85,
  elbow_bend_l: 0.7,
  wrist_twist_l: 0.95,
  arm_raise_r: 0.4,
  arm_forward_r: 0.5,
  arm_twist_r: 0.85,
  elbow_bend_r: 0.7,
  wrist_twist_r: 0.95,
  hip_lift_l: 0.8,
  hip_side_l: 1.0,
  knee_bend_l: 1.25,
  foot_point_l: 1.1,
  hip_lift_r: 0.8,
  hip_side_r: 1.0,
  knee_bend_r: 1.25,
  foot_point_r: 1.1,
};
const FIT_CONTROL_ORDER = [
  "root_yaw",
  "root_pitch",
  "root_roll",
  "spine_bend",
  "spine_twist",
  "hip_lift_l",
  "hip_side_l",
  "knee_bend_l",
  "foot_point_l",
  "hip_lift_r",
  "hip_side_r",
  "knee_bend_r",
  "foot_point_r",
  "arm_raise_l",
  "arm_forward_l",
  "arm_twist_l",
  "elbow_bend_l",
  "wrist_twist_l",
  "arm_raise_r",
  "arm_forward_r",
  "arm_twist_r",
  "elbow_bend_r",
  "wrist_twist_r",
  "head_yaw",
  "head_pitch",
  "head_roll",
];
const FIT_EXTRA_SEEDS = [
  {
    name: "dual_kneel",
    preset: "kneel_pose",
    controls: {
      root_pitch: 16,
      spine_bend: 20,
      spine_twist: 8,
      head_pitch: -8,
      hip_lift_l: 24,
      hip_side_l: 10,
      knee_bend_l: 104,
      foot_point_l: 20,
      hip_lift_r: 18,
      hip_side_r: -10,
      knee_bend_r: 110,
      foot_point_r: 18,
    },
  },
  {
    name: "dual_kneel_overhead_l",
    preset: "kneel_pose",
    controls: {
      root_yaw: 28,
      root_pitch: 18,
      root_roll: 6,
      spine_bend: 22,
      spine_twist: 18,
      head_yaw: 18,
      head_pitch: -6,
      arm_raise_l: 118,
      arm_forward_l: 18,
      arm_twist_l: 18,
      elbow_bend_l: 24,
      arm_raise_r: 92,
      arm_forward_r: -54,
      arm_twist_r: 32,
      elbow_bend_r: 78,
      hip_lift_l: 18,
      hip_side_l: 8,
      knee_bend_l: 112,
      foot_point_l: 16,
      hip_lift_r: 22,
      hip_side_r: -12,
      knee_bend_r: 96,
      foot_point_r: 12,
    },
  },
  {
    name: "dual_kneel_overhead_r",
    preset: "kneel_pose",
    controls: {
      root_yaw: -28,
      root_pitch: 18,
      root_roll: -6,
      spine_bend: 22,
      spine_twist: -18,
      head_yaw: -18,
      head_pitch: -6,
      arm_raise_l: 92,
      arm_forward_l: 54,
      arm_twist_l: -32,
      elbow_bend_l: 78,
      arm_raise_r: 118,
      arm_forward_r: -18,
      arm_twist_r: -18,
      elbow_bend_r: 24,
      hip_lift_l: 22,
      hip_side_l: 12,
      knee_bend_l: 96,
      foot_point_l: 12,
      hip_lift_r: 18,
      hip_side_r: -8,
      knee_bend_r: 112,
      foot_point_r: 16,
    },
  },
  {
    name: "airborne_reach_l",
    preset: "neutral",
    controls: {
      root_yaw: 18,
      root_pitch: 24,
      root_roll: -10,
      spine_bend: 18,
      spine_twist: 12,
      head_yaw: 10,
      head_pitch: -4,
      arm_raise_l: 98,
      arm_forward_l: 36,
      elbow_bend_l: 20,
      arm_raise_r: 62,
      arm_forward_r: -42,
      elbow_bend_r: 40,
      hip_lift_l: 70,
      hip_side_l: 16,
      knee_bend_l: 124,
      foot_point_l: 26,
      hip_lift_r: 20,
      hip_side_r: -18,
      knee_bend_r: 34,
      foot_point_r: 10,
    },
  },
  {
    name: "airborne_reach_r",
    preset: "neutral",
    controls: {
      root_yaw: -18,
      root_pitch: 24,
      root_roll: 10,
      spine_bend: 18,
      spine_twist: -12,
      head_yaw: -10,
      head_pitch: -4,
      arm_raise_l: 62,
      arm_forward_l: 42,
      elbow_bend_l: 40,
      arm_raise_r: 98,
      arm_forward_r: -36,
      elbow_bend_r: 20,
      hip_lift_l: 20,
      hip_side_l: 18,
      knee_bend_l: 34,
      foot_point_l: 10,
      hip_lift_r: 70,
      hip_side_r: -16,
      knee_bend_r: 124,
      foot_point_r: 26,
    },
  },
];
const POSE_MASS_WEIGHTS = {
  pelvis: 2.0,
  spine: 1.5,
  chest: 1.7,
  neck: 0.5,
  head: 0.9,
  shoulder_l: 0.3,
  shoulder_r: 0.3,
  elbow_l: 0.25,
  elbow_r: 0.25,
  wrist_l: 0.15,
  wrist_r: 0.15,
  hand_l: 0.1,
  hand_r: 0.1,
  hip_l: 0.8,
  hip_r: 0.8,
  knee_l: 0.7,
  knee_r: 0.7,
  ankle_l: 0.45,
  ankle_r: 0.45,
  toe_l: 0.2,
  toe_r: 0.2,
};
const FALLBACK_SILHOUETTE_RADII = {
  female: {
    torso: 18,
    shoulder: 13,
    upper: 11,
    lower: 9,
    hand: 8,
    hip: 14,
    thigh: 13,
    calf: 10,
    foot: 9,
  },
  male: {
    torso: 20,
    shoulder: 15,
    upper: 12,
    lower: 10,
    hand: 8,
    hip: 15,
    thigh: 14,
    calf: 11,
    foot: 10,
  },
};

let THREE = null;
let OrbitControls = null;
const studioOverlays = new Map();

const CONTROL_SPECS = {
  root_yaw: { label: "Root Yaw", min: -180, max: 180, step: 1, default: 0 },
  root_pitch: { label: "Root Pitch", min: -45, max: 45, step: 1, default: 2 },
  root_roll: { label: "Root Roll", min: -35, max: 35, step: 1, default: 0 },
  spine_bend: { label: "Spine Bend", min: -45, max: 45, step: 1, default: 6 },
  spine_twist: { label: "Spine Twist", min: -60, max: 60, step: 1, default: 0 },
  head_yaw: { label: "Head Yaw", min: -85, max: 85, step: 1, default: 6 },
  head_pitch: { label: "Head Pitch", min: -50, max: 50, step: 1, default: -4 },
  head_roll: { label: "Head Roll", min: -40, max: 40, step: 1, default: 0 },
  arm_raise_l: { label: "Raise L", min: -45, max: 135, step: 1, default: 18 },
  arm_forward_l: { label: "Forward L", min: -120, max: 120, step: 1, default: 10 },
  arm_twist_l: { label: "Twist L", min: -120, max: 120, step: 1, default: 0 },
  elbow_bend_l: { label: "Elbow L", min: 0, max: 150, step: 1, default: 18 },
  wrist_twist_l: { label: "Wrist L", min: -120, max: 120, step: 1, default: 0 },
  arm_raise_r: { label: "Raise R", min: -45, max: 135, step: 1, default: 14 },
  arm_forward_r: { label: "Forward R", min: -120, max: 120, step: 1, default: -8 },
  arm_twist_r: { label: "Twist R", min: -120, max: 120, step: 1, default: 0 },
  elbow_bend_r: { label: "Elbow R", min: 0, max: 150, step: 1, default: 12 },
  wrist_twist_r: { label: "Wrist R", min: -120, max: 120, step: 1, default: 0 },
  hip_lift_l: { label: "Hip Lift L", min: -60, max: 95, step: 1, default: 4 },
  hip_side_l: { label: "Hip Side L", min: -45, max: 45, step: 1, default: 6 },
  knee_bend_l: { label: "Knee L", min: 0, max: 155, step: 1, default: 6 },
  foot_point_l: { label: "Foot L", min: -45, max: 75, step: 1, default: 6 },
  hip_lift_r: { label: "Hip Lift R", min: -60, max: 95, step: 1, default: -2 },
  hip_side_r: { label: "Hip Side R", min: -45, max: 45, step: 1, default: -4 },
  knee_bend_r: { label: "Knee R", min: 0, max: 155, step: 1, default: 2 },
  foot_point_r: { label: "Foot R", min: -45, max: 75, step: 1, default: 2 },
};

const LEFT_RIGHT_KEYS = [
  ["arm_raise_l", "arm_raise_r", "same"],
  ["arm_forward_l", "arm_forward_r", "invert"],
  ["arm_twist_l", "arm_twist_r", "invert"],
  ["elbow_bend_l", "elbow_bend_r", "same"],
  ["wrist_twist_l", "wrist_twist_r", "invert"],
  ["hip_lift_l", "hip_lift_r", "same"],
  ["hip_side_l", "hip_side_r", "invert"],
  ["knee_bend_l", "knee_bend_r", "same"],
  ["foot_point_l", "foot_point_r", "same"],
];

const POSE_PRESETS = {
  neutral: {},
  heroic: {
    root_yaw: 12,
    root_pitch: 4,
    spine_bend: 10,
    head_yaw: 10,
    arm_raise_l: 28,
    arm_forward_l: 14,
    elbow_bend_l: 34,
    arm_raise_r: 10,
    arm_forward_r: -14,
    hip_lift_l: 9,
    hip_side_l: 10,
    hip_lift_r: -6,
    hip_side_r: -7,
    knee_bend_l: 12,
  },
  contrapposto: {
    root_yaw: 18,
    root_roll: 7,
    spine_bend: 8,
    spine_twist: 11,
    head_yaw: 16,
    head_pitch: -6,
    arm_raise_l: 24,
    arm_forward_l: 12,
    elbow_bend_l: 26,
    arm_raise_r: 2,
    arm_forward_r: -18,
    hip_lift_l: 10,
    hip_side_l: 14,
    hip_lift_r: -8,
    hip_side_r: -9,
    knee_bend_l: 18,
    knee_bend_r: 4,
  },
  run_start: {
    root_pitch: 14,
    spine_bend: 18,
    head_pitch: -10,
    arm_raise_l: 40,
    arm_forward_l: 42,
    elbow_bend_l: 64,
    arm_raise_r: 26,
    arm_forward_r: -36,
    elbow_bend_r: 44,
    hip_lift_l: 30,
    hip_side_l: 10,
    knee_bend_l: 44,
    foot_point_l: 18,
    hip_lift_r: -20,
    hip_side_r: -8,
    knee_bend_r: 12,
    foot_point_r: -4,
  },
  power_stance: {
    root_yaw: 10,
    root_pitch: 3,
    root_roll: 4,
    spine_bend: 9,
    spine_twist: 8,
    head_yaw: 8,
    arm_raise_l: 20,
    arm_forward_l: 10,
    elbow_bend_l: 24,
    arm_raise_r: 6,
    arm_forward_r: -10,
    elbow_bend_r: 12,
    hip_lift_l: 8,
    hip_side_l: 10,
    hip_lift_r: -8,
    hip_side_r: -10,
    knee_bend_l: 10,
    knee_bend_r: 4,
  },
  reach_up: {
    root_pitch: 8,
    spine_bend: 16,
    head_pitch: -10,
    arm_raise_l: 84,
    arm_forward_l: 20,
    arm_twist_l: 10,
    elbow_bend_l: 18,
    arm_raise_r: 32,
    arm_forward_r: -12,
    elbow_bend_r: 22,
    hip_lift_l: 14,
    hip_side_l: 8,
    hip_lift_r: -8,
    hip_side_r: -6,
    knee_bend_l: 14,
    foot_point_l: 10,
  },
  kneel_pose: {
    root_pitch: 10,
    spine_bend: 12,
    head_pitch: -6,
    arm_raise_l: 18,
    arm_forward_l: 12,
    elbow_bend_l: 36,
    arm_raise_r: 6,
    arm_forward_r: -16,
    elbow_bend_r: 20,
    hip_lift_l: 26,
    hip_side_l: 8,
    knee_bend_l: 82,
    foot_point_l: 18,
    hip_lift_r: -12,
    hip_side_r: -6,
    knee_bend_r: 24,
    foot_point_r: -6,
  },
  hands_behind_back: {
    root_yaw: 8,
    spine_bend: 6,
    spine_twist: 6,
    head_yaw: 14,
    head_pitch: -4,
    arm_raise_l: -8,
    arm_forward_l: -42,
    arm_twist_l: -36,
    elbow_bend_l: 52,
    wrist_twist_l: -18,
    arm_raise_r: -10,
    arm_forward_r: 42,
    arm_twist_r: 36,
    elbow_bend_r: 48,
    wrist_twist_r: 18,
    hip_lift_l: 8,
    hip_side_l: 8,
    hip_lift_r: -6,
    hip_side_r: -8,
    knee_bend_l: 8,
    knee_bend_r: 4,
  },
  pinup_sway: {
    root_yaw: 16,
    root_roll: 8,
    spine_bend: 10,
    spine_twist: 14,
    head_yaw: 18,
    head_pitch: -8,
    head_roll: 6,
    arm_raise_l: 34,
    arm_forward_l: 18,
    elbow_bend_l: 44,
    wrist_twist_l: 12,
    arm_raise_r: 4,
    arm_forward_r: -22,
    elbow_bend_r: 22,
    hip_lift_l: 14,
    hip_side_l: 16,
    hip_lift_r: -12,
    hip_side_r: -10,
    knee_bend_l: 22,
    foot_point_l: 12,
    knee_bend_r: 6,
  },
  crouch_ready: {
    root_pitch: 18,
    spine_bend: 20,
    head_pitch: -8,
    arm_raise_l: 26,
    arm_forward_l: 24,
    elbow_bend_l: 58,
    arm_raise_r: 18,
    arm_forward_r: -18,
    elbow_bend_r: 46,
    hip_lift_l: 20,
    hip_side_l: 10,
    knee_bend_l: 54,
    foot_point_l: 10,
    hip_lift_r: -18,
    hip_side_r: -8,
    knee_bend_r: 48,
    foot_point_r: 8,
  },
};

const PRESET_OPTIONS = Object.keys(POSE_PRESETS);
const PRESET_LABELS = {
  neutral: "Neutral",
  heroic: "Heroic",
  contrapposto: "Contrapposto",
  run_start: "Run Start",
  power_stance: "Hero Stance",
  reach_up: "Reach Up",
  kneel_pose: "One-Knee Kneel",
  hands_behind_back: "Hands Behind Back",
  pinup_sway: "Glam Sway",
  crouch_ready: "Crouch Ready",
};
const IMAGE_FIT_ANCHOR_OPTIONS = [
  ["head", "Head"],
  ["neck", "Neck"],
  ["eye_l", "Eye L"],
  ["eye_r", "Eye R"],
  ["chin", "Chin"],
  ["chest", "Chest"],
  ["pelvis", "Pelvis"],
  ["shoulder_l", "Shoulder L"],
  ["shoulder_r", "Shoulder R"],
  ["elbow_l", "Elbow L"],
  ["elbow_r", "Elbow R"],
  ["wrist_l", "Wrist L"],
  ["wrist_r", "Wrist R"],
  ["hand_l", "Hand L"],
  ["hand_r", "Hand R"],
  ["thumb_l", "Thumb L"],
  ["thumb_r", "Thumb R"],
  ["index_l", "Index L"],
  ["index_r", "Index R"],
  ["knee_l", "Knee L"],
  ["knee_r", "Knee R"],
  ["ankle_l", "Ankle L"],
  ["ankle_r", "Ankle R"],
  ["heel_l", "Heel L"],
  ["heel_r", "Heel R"],
  ["toe_l", "Toe L"],
  ["toe_r", "Toe R"],
];
const IMAGE_FIT_ANCHOR_SET = new Set(IMAGE_FIT_ANCHOR_OPTIONS.map(([key]) => key));
const IMAGE_FIT_ANCHOR_GROUPS = {
  head_face: ["head", "neck"],
  torso: ["chest", "pelvis", "shoulder_l", "shoulder_r"],
  arms: ["elbow_l", "elbow_r"],
  hands: ["wrist_l", "wrist_r"],
  fingers: ["hand_l", "hand_r"],
  legs: ["knee_l", "knee_r"],
  feet: ["ankle_l", "ankle_r"],
  toes: ["toe_l", "toe_r"],
};
const LEGACY_IMAGE_FIT_GROUP_MAP = {
  face: ["head_face"],
  body: ["torso", "arms", "legs"],
  hands: ["hands", "fingers"],
  feet: ["feet", "toes"],
};
const IMAGE_FIT_GROUP_LABELS = [
  ["head_face", "Head / Face"],
  ["torso", "Torso"],
  ["arms", "Arms"],
  ["hands", "Hands"],
  ["fingers", "Fingers"],
  ["legs", "Legs"],
  ["feet", "Feet"],
  ["toes", "Toes"],
];

function presetLabel(presetKey) {
  const key = String(presetKey || "");
  if (PRESET_LABELS[key]) return PRESET_LABELS[key];
  return key
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function loadUserPresets() {
  try {
    const raw = window.localStorage?.getItem(USER_PRESET_STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : {};
  } catch {
    return {};
  }
}

function saveUserPresets(presets) {
  try {
    window.localStorage?.setItem(USER_PRESET_STORAGE_KEY, JSON.stringify(presets));
  } catch {
  }
}

const POSE_BONES = [
  ["pelvis", "spine"],
  ["spine", "chest"],
  ["chest", "neck"],
  ["neck", "head"],
  ["head", "eye_l"],
  ["head", "eye_r"],
  ["head", "chin"],
  ["chest", "shoulder_l"],
  ["shoulder_l", "elbow_l"],
  ["elbow_l", "wrist_l"],
  ["wrist_l", "hand_l"],
  ["hand_l", "thumb_l"],
  ["hand_l", "index_l"],
  ["chest", "shoulder_r"],
  ["shoulder_r", "elbow_r"],
  ["elbow_r", "wrist_r"],
  ["wrist_r", "hand_r"],
  ["hand_r", "thumb_r"],
  ["hand_r", "index_r"],
  ["pelvis", "hip_l"],
  ["hip_l", "knee_l"],
  ["knee_l", "ankle_l"],
  ["ankle_l", "heel_l"],
  ["ankle_l", "toe_l"],
  ["pelvis", "hip_r"],
  ["hip_r", "knee_r"],
  ["knee_r", "ankle_r"],
  ["ankle_r", "heel_r"],
  ["ankle_r", "toe_r"],
];

const POSE_COLORS = {
  left: "#b0f0d4",
  right: "#78bcff",
  center: "#e1ecf1",
  shadow: "#080c10",
  exportFrame: "rgba(242, 168, 31, 0.9)",
  bgTop: "#0a1017",
  bgBottom: "#1c2631",
  bgPanel: "#0f171f",
};

function jointDisplayRadius(name) {
  const key = String(name || "");
  if (key === "head") return 7;
  if (["eye_l", "eye_r", "chin", "thumb_l", "thumb_r", "index_l", "index_r", "heel_l", "heel_r", "toe_l", "toe_r"].includes(key)) {
    return 3.5;
  }
  if (["hand_l", "hand_r", "neck", "ankle_l", "ankle_r", "wrist_l", "wrist_r"].includes(key)) {
    return 4.5;
  }
  return 5.5;
}

const JOINT_CONTROL_GROUPS = {
  torso: ["root_yaw", "root_pitch", "root_roll", "spine_bend", "spine_twist", "head_yaw", "head_pitch", "head_roll"],
  arms_l: ["arm_raise_l", "arm_forward_l", "arm_twist_l", "elbow_bend_l", "wrist_twist_l"],
  arms_r: ["arm_raise_r", "arm_forward_r", "arm_twist_r", "elbow_bend_r", "wrist_twist_r"],
  legs_l: ["hip_lift_l", "hip_side_l", "knee_bend_l", "foot_point_l"],
  legs_r: ["hip_lift_r", "hip_side_r", "knee_bend_r", "foot_point_r"],
};

function getJointControlGroup(jointName) {
  if (!jointName) return "torso";
  if (["pelvis", "spine", "chest", "neck", "head", "eye_l", "eye_r", "chin"].includes(jointName)) return "torso";
  if (/_l$/.test(jointName) && /^(shoulder|elbow|wrist|hand|thumb|index)_/.test(jointName)) return "arms_l";
  if (/_r$/.test(jointName) && /^(shoulder|elbow|wrist|hand|thumb|index)_/.test(jointName)) return "arms_r";
  if (/_l$/.test(jointName) && /^(hip|knee|ankle|heel|toe)_/.test(jointName)) return "legs_l";
  if (/_r$/.test(jointName) && /^(hip|knee|ankle|heel|toe)_/.test(jointName)) return "legs_r";
  return "torso";
}

function axisLabel(axis, text) {
  return `${String(axis || "").toUpperCase()} • ${text}`;
}

function getJointAxisControlLabels(jointName) {
  if (!jointName || ["pelvis", "spine", "chest"].includes(jointName)) {
    return {
      root_yaw: axisLabel("x", "Yaw"),
      root_pitch: axisLabel("y", "Pitch"),
      root_roll: axisLabel("z", "Roll"),
      spine_bend: axisLabel("y", "Bend"),
      spine_twist: axisLabel("x", "Twist"),
      head_yaw: "Head Yaw",
      head_pitch: "Head Pitch",
      head_roll: "Head Roll",
    };
  }

  if (["neck", "head", "eye_l", "eye_r", "chin"].includes(jointName)) {
    return {
      head_yaw: axisLabel("x", "Yaw"),
      head_pitch: axisLabel("y", "Pitch"),
      head_roll: axisLabel("z", "Roll"),
      spine_bend: "Spine Bend Assist",
      spine_twist: "Spine Twist Assist",
      root_yaw: "Root Yaw Assist",
      root_pitch: "Root Pitch Assist",
      root_roll: "Root Roll Assist",
    };
  }

  if (/^shoulder_[lr]$/.test(jointName)) {
    const side = jointName.endsWith("_l") ? "l" : "r";
    return {
      [`arm_forward_${side}`]: axisLabel("x", "Forward"),
      [`arm_raise_${side}`]: axisLabel("y", "Raise"),
      [`arm_twist_${side}`]: axisLabel("z", "Twist"),
      [`elbow_bend_${side}`]: "Elbow Bend",
      [`wrist_twist_${side}`]: "Wrist Twist",
    };
  }

  if (/^elbow_[lr]$/.test(jointName)) {
    const side = jointName.endsWith("_l") ? "l" : "r";
    return {
      [`elbow_bend_${side}`]: axisLabel("x", "Bend"),
      [`arm_raise_${side}`]: axisLabel("y", "Raise Assist"),
      [`arm_twist_${side}`]: axisLabel("z", "Twist"),
      [`arm_forward_${side}`]: "Forward Assist",
      [`wrist_twist_${side}`]: "Wrist Twist",
    };
  }

  if (/^(wrist|hand|thumb|index)_[lr]$/.test(jointName)) {
    const side = jointName.endsWith("_l") ? "l" : "r";
    return {
      [`wrist_twist_${side}`]: axisLabel("x", "Wrist Twist"),
      [`elbow_bend_${side}`]: axisLabel("y", "Bend Assist"),
      [`arm_forward_${side}`]: axisLabel("z", "Forward Assist"),
      [`arm_raise_${side}`]: "Raise Assist",
      [`arm_twist_${side}`]: "Arm Twist",
    };
  }

  if (/^hip_[lr]$/.test(jointName)) {
    const side = jointName.endsWith("_l") ? "l" : "r";
    return {
      [`hip_side_${side}`]: axisLabel("x", "Side"),
      [`hip_lift_${side}`]: axisLabel("y", "Lift"),
      [`foot_point_${side}`]: axisLabel("z", "Point"),
      [`knee_bend_${side}`]: "Knee Bend",
    };
  }

  if (/^knee_[lr]$/.test(jointName)) {
    const side = jointName.endsWith("_l") ? "l" : "r";
    return {
      [`knee_bend_${side}`]: axisLabel("y", "Bend"),
      [`hip_side_${side}`]: axisLabel("x", "Side Assist"),
      [`hip_lift_${side}`]: "Hip Lift Assist",
      [`foot_point_${side}`]: axisLabel("z", "Point Assist"),
    };
  }

  if (/^(ankle|heel|toe)_[lr]$/.test(jointName)) {
    const side = jointName.endsWith("_l") ? "l" : "r";
    return {
      [`foot_point_${side}`]: axisLabel("z", "Point"),
      [`knee_bend_${side}`]: axisLabel("y", "Bend Assist"),
      [`hip_side_${side}`]: axisLabel("x", "Side Assist"),
      [`hip_lift_${side}`]: "Lift Assist",
    };
  }

  return {};
}

function ensurePoseStudioStyles() {
  if (document.getElementById(STYLE_ID)) return;
  const style = document.createElement("style");
  style.id = STYLE_ID;
  style.textContent = `
    .mkr-pose-panel {
      --mkr-ink: #edf2f7;
      --mkr-card: rgba(27, 32, 38, 0.98);
      --mkr-card-alt: rgba(15, 20, 26, 0.96);
      --mkr-muted: #97a6b6;
      --mkr-line: rgba(123, 142, 161, 0.18);
      --mkr-accent-a: #4761ff;
      --mkr-accent-a-src: #4761ff;
      --mkr-accent-b: #f3a03f;
      --mkr-accent-c: #d9573b;
      --mkr-shadow: 0 18px 44px rgba(0, 0, 0, 0.26);
      width: 100%;
      max-width: none;
      height: 100%;
      max-height: none;
      border-radius: 14px;
      border: 1px solid rgba(124, 143, 160, 0.18);
      background: #24282d;
      padding: 4px;
      overflow: hidden;
      box-sizing: border-box;
      contain: layout size paint;
      container-type: inline-size;
    }

    .mkr-pose-panel--studio {
      width: 100% !important;
      max-width: none !important;
      max-height: none !important;
      height: 100%;
      min-height: 0;
      border-radius: 0 !important;
      border: 0 !important;
      background: transparent !important;
      padding: 0;
      overflow: hidden;
      box-shadow: none !important;
      animation: none !important;
    }

    .mkr-pose-launcher {
      width: 100%;
      height: 100%;
      min-height: ${LAUNCHER_WIDGET_HEIGHT}px;
      display: grid;
      grid-template-rows: auto auto 1fr;
      gap: 10px;
      padding: 12px;
      border-radius: 14px;
      border: 1px solid rgba(124, 143, 160, 0.18);
      background: #22272d;
      box-sizing: border-box;
      color: #eef4fa;
    }

    .mkr-pose-launcher-head {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 12px;
    }

    .mkr-pose-launcher-kicker {
      font: 700 10px/1 sans-serif;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      color: #9bacbb;
      margin-bottom: 5px;
    }

    .mkr-pose-launcher-title {
      font: 700 18px/1.05 sans-serif;
      color: #f2f5f8;
    }

    .mkr-pose-launcher-meta {
      font: 600 11px/1.35 sans-serif;
      color: #97a6b6;
      text-align: right;
    }

    .mkr-pose-launcher-summary {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 8px;
    }

    .mkr-pose-launcher-pill {
      padding: 8px 9px;
      border-radius: 10px;
      background: #171c21;
      border: 1px solid rgba(124, 143, 160, 0.16);
      min-width: 0;
    }

    .mkr-pose-launcher-pill-label {
      font: 700 10px/1 sans-serif;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: #92a4b4;
      margin-bottom: 5px;
    }

    .mkr-pose-launcher-pill-value {
      font: 700 13px/1.15 sans-serif;
      color: #eef4fa;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .mkr-pose-launcher-actions {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 8px;
      align-items: stretch;
    }

    .mkr-pose-launcher-btn,
    .mkr-pose-modal-btn {
      border: 1px solid rgba(103, 129, 255, 0.32);
      background: #4761ff;
      color: #eef4fa;
      border-radius: 10px;
      font: 700 12px/1 sans-serif;
      padding: 10px 12px;
      cursor: pointer;
    }

    .mkr-pose-launcher-btn[data-tone="ghost"],
    .mkr-pose-modal-btn[data-tone="ghost"] {
      background: #14191e;
      color: #cdd7e0;
      border-color: rgba(124, 143, 160, 0.2);
    }

    .mkr-pose-modal-backdrop {
      position: fixed;
      inset: 0;
      z-index: 100000;
      display: flex;
      align-items: stretch;
      justify-content: stretch;
      padding: 0;
      background: rgba(8, 11, 16, 0.76);
      backdrop-filter: blur(6px);
      box-sizing: border-box;
    }

    .mkr-pose-modal-shell {
      width: 100%;
      height: 100%;
      min-width: 0;
      min-height: 0;
      display: grid;
      grid-template-rows: auto minmax(0, 1fr);
      border-radius: 0;
      overflow: hidden;
      border: 0;
      background: transparent;
      box-shadow: none;
    }

    .mkr-pose-modal-head {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 12px;
      align-items: center;
      padding: 14px 16px;
      border-bottom: 1px solid rgba(124, 143, 160, 0.12);
      background: rgba(17, 22, 29, 0.92);
      color: #eef4fa;
    }

    .mkr-pose-modal-title {
      font: 700 18px/1.1 sans-serif;
    }

    .mkr-pose-modal-subtitle {
      margin-top: 4px;
      font: 500 12px/1.35 sans-serif;
      color: #9aabba;
    }

    .mkr-pose-modal-actions {
      display: flex;
      gap: 8px;
      align-items: center;
    }

    .mkr-pose-modal-body {
      min-width: 0;
      min-height: 0;
      padding: 0;
      box-sizing: border-box;
      overflow: hidden;
      background: transparent;
    }

    .mkr-pose-panel .mkr-header {
      display: none;
    }

    .mkr-pose-panel .mkr-title { color: #f2f5f8; }
    .mkr-pose-panel .mkr-subtitle,
    .mkr-pose-panel .mkr-kicker,
    .mkr-pose-panel .mkr-section-note { color: #99a6b3; }

    .mkr-pose-layout {
      display: grid;
      grid-template-columns: minmax(176px, 0.9fr) minmax(0, 1.6fr) minmax(170px, 0.82fr);
      gap: 8px;
      align-items: start;
      height: 100%;
      min-height: 0;
      width: 100%;
      min-width: 0;
    }

    .mkr-pose-layout--studio {
      position: relative;
      display: block;
      width: 100%;
      height: 100%;
      min-height: 0;
      overflow: hidden;
      background: #171b34;
    }

    .mkr-pose-left,
    .mkr-pose-right,
    .mkr-pose-center {
      display: flex;
      flex-direction: column;
      gap: 8px;
      min-width: 0;
      min-height: 0;
      width: 100%;
      box-sizing: border-box;
    }

    .mkr-pose-layout--studio .mkr-pose-center {
      position: absolute;
      inset: 0;
      display: block;
      width: 100%;
      height: 100%;
      z-index: 1;
    }

    .mkr-pose-layout--studio .mkr-pose-left,
    .mkr-pose-layout--studio .mkr-pose-right {
      position: absolute;
      top: 16px;
      bottom: 16px;
      width: min(292px, 24vw);
      min-width: 232px;
      z-index: 3;
      pointer-events: none;
      overflow: hidden;
    }

    .mkr-pose-layout--studio .mkr-pose-left {
      left: 16px;
    }

    .mkr-pose-layout--studio .mkr-pose-right {
      right: 16px;
    }

    .mkr-pose-layout--studio .mkr-pose-left > *,
    .mkr-pose-layout--studio .mkr-pose-right > * {
      pointer-events: auto;
    }

    .mkr-pose-layout--studio .mkr-pose-left {
      display: grid;
      grid-template-rows: auto minmax(0, 1fr);
      gap: 8px;
    }

    .mkr-pose-layout--studio .mkr-pose-right {
      gap: 8px;
    }

    .mkr-pose-layout--studio .mkr-pose-tabbar {
      display: none;
    }

    .mkr-pose-layout--studio .mkr-pose-left,
    .mkr-pose-layout--studio .mkr-pose-right {
      background: rgba(22, 28, 35, 0.72);
      border: 1px solid rgba(124, 143, 160, 0.14);
      border-radius: 14px;
      backdrop-filter: blur(10px);
      padding: 10px;
      box-sizing: border-box;
    }

    .mkr-pose-layout--studio .mkr-pose-left-panelhost,
    .mkr-pose-layout--studio .mkr-pose-right-scroll {
      min-height: 0;
      overflow: auto;
      padding-right: 2px;
    }

    .mkr-pose-layout--studio .mkr-pose-stage-section {
      position: absolute;
      inset: 0;
      margin: 0;
      padding: 0;
      border: 0;
      border-radius: 0;
      background: transparent;
      box-shadow: none;
    }

    .mkr-pose-layout--studio .mkr-pose-stage-section > .mkr-section-head {
      display: none;
    }

    .mkr-pose-layout--studio .mkr-pose-stage-section > .mkr-stack {
      height: 100%;
      min-height: 0;
    }

    .mkr-pose-layout--studio .mkr-pose-action-dock {
      position: static;
      width: 100%;
      z-index: auto;
      pointer-events: auto;
      background: transparent;
      border: 0;
      border-radius: 0;
      backdrop-filter: none;
      box-sizing: border-box;
    }

    .mkr-pose-layout--studio .mkr-pose-tool-dock {
      position: absolute;
      top: 16px;
      left: 50%;
      transform: translateX(-50%);
      z-index: 4;
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 8px 10px;
      background: rgba(22, 28, 35, 0.82);
      border: 1px solid rgba(124, 143, 160, 0.14);
      border-radius: 14px;
      backdrop-filter: blur(12px);
      box-sizing: border-box;
    }

    .mkr-pose-tool-btn {
      border: 1px solid rgba(124, 143, 160, 0.18);
      background: #14191e;
      color: #d3dde6;
      border-radius: 9px;
      font: 700 11px/1 sans-serif;
      padding: 8px 10px;
      cursor: pointer;
    }

    .mkr-pose-tool-btn[data-active="true"] {
      background: #4761ff;
      border-color: rgba(103, 129, 255, 0.48);
      color: #eef4fa;
    }

    .mkr-pose-tool-status {
      padding-left: 4px;
      font: 600 11px/1.2 sans-serif;
      color: #9eb0bf;
      white-space: nowrap;
    }

    .mkr-pose-selection-card {
      display: grid;
      gap: 6px;
      padding: 10px;
      border-radius: 12px;
      background: rgba(14, 18, 24, 0.72);
      border: 1px solid rgba(124, 143, 160, 0.16);
    }

    .mkr-pose-selection-kicker {
      font: 700 10px/1 sans-serif;
      text-transform: uppercase;
      letter-spacing: 0.1em;
      color: #8fa1b1;
    }

    .mkr-pose-selection-title {
      font: 700 15px/1.1 sans-serif;
      color: #eef4fa;
    }

    .mkr-pose-selection-note {
      font: 600 11px/1.35 sans-serif;
      color: #9eb0bf;
    }

    .mkr-pose-layout--studio .mkr-pose-action-dock .mkr-section {
      background: transparent;
      border: 0;
      box-shadow: none;
      padding: 10px;
    }

    .mkr-pose-layout--studio .mkr-pose-action-dock .mkr-section-head {
      margin-bottom: 6px;
    }

    .mkr-pose-left {
      overflow-y: auto;
      overflow-x: hidden;
    }

    .mkr-pose-right {
      overflow-y: auto;
      overflow-x: hidden;
    }

    .mkr-pose-center {
      display: grid;
      grid-template-rows: minmax(0, 1fr) auto;
      overflow: hidden;
    }

    .mkr-pose-center > .mkr-section:first-child {
      height: 100%;
      min-height: 0;
    }

    .mkr-pose-center > .mkr-section:first-child .mkr-stack {
      height: 100%;
      min-height: 0;
    }

    .mkr-pose-tabbar {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 4px;
      margin-bottom: 6px;
    }

    .mkr-pose-tab {
      border: 1px solid rgba(120, 141, 160, 0.2);
      background: #12171c;
      color: #aebdcb;
      border-radius: 7px;
      font: 700 10px/1 sans-serif;
      padding: 7px 4px;
      cursor: pointer;
    }

    .mkr-pose-tab[data-active="true"] {
      background: #2a3650;
      color: #eef4fa;
      border-color: rgba(93, 120, 255, 0.5);
    }

    .mkr-pose-panel-group {
      display: none;
      min-height: 0;
    }

    .mkr-pose-panel-group[data-active="true"] {
      display: flex;
      flex-direction: column;
      gap: 8px;
      min-height: 0;
    }

    .mkr-pose-panel .mkr-section {
      margin-top: 0;
      background: #1d2329;
      border-color: rgba(120, 141, 160, 0.16);
      border-radius: 8px;
      padding: 8px;
      box-shadow: inset 0 1px 0 rgba(255,255,255,0.02);
      min-width: 0;
      box-sizing: border-box;
    }

    .mkr-pose-panel .mkr-control {
      grid-template-columns: 78px 1fr auto;
      gap: 6px;
      padding: 5px 0;
      border-bottom-color: rgba(120, 141, 160, 0.16);
    }

    .mkr-pose-panel .mkr-label,
    .mkr-pose-panel .mkr-section-title {
      color: #dbe4ec;
    }

    .mkr-pose-panel .mkr-input,
    .mkr-pose-panel .mkr-select,
    .mkr-pose-panel .mkr-number,
    .mkr-pose-panel .mkr-btn {
      background: rgba(13, 18, 24, 0.96);
      color: #eef4fa;
      border-color: rgba(120, 141, 160, 0.22);
    }

    .mkr-pose-panel .mkr-btn[data-tone="accent"] {
      background: #4761ff;
      border-color: rgba(103, 129, 255, 0.5);
      color: #eef4fa;
    }

    .mkr-pose-panel .mkr-range { accent-color: #b9d63e; }

    .mkr-pose-panel .mkr-group-chip {
      background: rgba(71, 97, 255, 0.15);
      color: #9db0ff;
      border: 1px solid rgba(71, 97, 255, 0.32);
    }

    .mkr-pose-viewport-shell .mkr-section {
      padding: 6px;
    }

    .mkr-pose-panel .mkr-viewport {
      height: 100%;
      min-height: 520px;
      border-radius: 6px;
      border: 1px solid rgba(196, 145, 51, 0.56);
      background: linear-gradient(180deg, ${POSE_COLORS.bgTop} 0%, ${POSE_COLORS.bgBottom} 100%);
      min-width: 0;
      touch-action: none;
      user-select: none;
    }

    .mkr-pose-layout--studio .mkr-pose-panel .mkr-viewport,
    .mkr-pose-layout--studio .mkr-viewport {
      width: 100%;
      height: 100%;
      min-height: 0;
      border-radius: 0;
      border: 0;
      background: linear-gradient(180deg, ${POSE_COLORS.bgTop} 0%, ${POSE_COLORS.bgBottom} 100%);
    }

    .mkr-pose-overlay-canvas {
      position: absolute;
      inset: 0;
      width: 100%;
      height: 100%;
      z-index: 5;
      pointer-events: none;
      touch-action: none;
      cursor: crosshair;
    }

    .mkr-pose-render-layer {
      position: absolute;
      inset: 0;
      z-index: 1;
      overflow: hidden;
    }

    .mkr-pose-render-layer canvas {
      display: block;
      width: 100%;
      height: 100%;
      touch-action: none;
      user-select: none;
    }

    .mkr-pose-charbox textarea {
      width: 100%;
      min-height: 88px;
      max-height: 120px;
      resize: none;
      border-radius: 8px;
      border: 1px solid rgba(120, 141, 160, 0.2);
      background: rgba(13, 18, 24, 0.96);
      color: #eef4fa;
      padding: 8px;
      font: 12px/1.4 ui-monospace, SFMono-Regular, Menlo, monospace;
      box-sizing: border-box;
    }

    .mkr-pose-panel .mkr-control {
      min-height: 24px;
    }

    .mkr-pose-panel .mkr-label {
      font-size: 10px;
    }

    .mkr-pose-panel .mkr-number {
      width: 52px;
      padding: 4px 6px;
      font-size: 11px;
      flex: 0 0 52px;
    }

    .mkr-pose-panel .mkr-input,
    .mkr-pose-panel .mkr-select {
      padding: 5px 6px;
      font-size: 11px;
    }

    .mkr-pose-action-grid {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 6px;
    }

    .mkr-pose-action-grid .mkr-btn {
      width: 100%;
    }

    .mkr-pose-panel .mkr-stack {
      gap: 6px;
    }

    @container (max-width: 880px) {
      .mkr-pose-layout {
        grid-template-columns: minmax(168px, 0.95fr) minmax(0, 1.45fr);
        grid-template-areas:
          "left center"
          "right center";
      }

      .mkr-pose-left {
        grid-area: left;
      }

      .mkr-pose-center {
        grid-area: center;
      }

      .mkr-pose-right {
        grid-area: right;
      }
    }

    @container (max-width: 720px) {
      .mkr-pose-layout {
        grid-template-columns: 1fr;
        grid-template-areas:
          "center"
          "left"
          "right";
        height: 100%;
      }

      .mkr-pose-left {
        grid-area: left;
        max-height: 220px;
      }

      .mkr-pose-center {
        grid-area: center;
      }

      .mkr-pose-right {
        grid-area: right;
        max-height: 220px;
      }

      .mkr-pose-panel .mkr-viewport {
        min-height: 360px;
      }
    }

    @media (max-width: 980px) {
      .mkr-pose-layout--studio .mkr-pose-left,
      .mkr-pose-layout--studio .mkr-pose-right {
        width: min(260px, 31vw);
        min-width: 208px;
      }

      .mkr-pose-layout--studio .mkr-pose-action-dock {
        width: min(720px, calc(100% - 32px));
      }
    }
  `;
  document.head.appendChild(style);
}

async function loadThree() {
  if (THREE && OrbitControls) return { THREE, OrbitControls };
  THREE = await import("https://unpkg.com/three@0.160.0/build/three.module.js");
  const controls = await import("https://unpkg.com/three@0.160.0/examples/jsm/controls/OrbitControls.js");
  OrbitControls = controls.OrbitControls;
  return { THREE, OrbitControls };
}

function getWidget(node, name) {
  const visible = node?.widgets?.find((w) => w?.name === name);
  if (visible) return visible;
  const hidden = node?.__mkrPoseSerialWidgets?.find((w) => w?.name === name);
  if (hidden) return hidden;
  const virtual = node?.__mkrPoseVirtualWidgets?.get?.(name);
  if (virtual) return virtual;
  return null;
}

function ensureVirtualWidget(node, name, defaultValue) {
  if (!node.__mkrPoseVirtualWidgets) {
    node.__mkrPoseVirtualWidgets = new Map();
  }
  if (!node.__mkrPoseVirtualWidgets.has(name)) {
    node.__mkrPoseVirtualWidgets.set(name, {
      name,
      value: defaultValue,
      hidden: true,
      serialize: true,
      type: "hidden",
      visible: false,
      options: { hidden: true, visible: false, serialize: true },
      computeSize: () => [0, 0],
      computeLayoutSize: () => ({ minHeight: 0, maxHeight: 0, minWidth: 0 }),
      draw: () => {},
    });
  }
  return node.__mkrPoseVirtualWidgets.get(name);
}

function ensurePoseBackingWidgets(node) {
  return {
    settings_json: getWidget(node, "settings_json") || ensureVirtualWidget(node, "settings_json", "{}"),
    pose_name: getWidget(node, "pose_name") || ensureVirtualWidget(node, "pose_name", ""),
    pose_preset: getWidget(node, "pose_preset") || ensureVirtualWidget(node, "pose_preset", "from_settings"),
    mirror_mode: getWidget(node, "mirror_mode") || ensureVirtualWidget(node, "mirror_mode", "from_settings"),
    capture_w: getWidget(node, "capture_w") || ensureVirtualWidget(node, "capture_w", 1024),
    capture_h: getWidget(node, "capture_h") || ensureVirtualWidget(node, "capture_h", 1024),
    character_state_json: getWidget(node, "character_state_json") || ensureVirtualWidget(node, "character_state_json", ""),
    pose_from_image_mode: getWidget(node, "pose_from_image_mode") || ensureVirtualWidget(node, "pose_from_image_mode", "off"),
    pose_image_strength: getWidget(node, "pose_image_strength") || ensureVirtualWidget(node, "pose_image_strength", 1.0),
  };
}

function sanitizeDisplaySettings(display) {
  const next = display && typeof display === "object" && !Array.isArray(display) ? display : {};
  const viewMode = ["bones_only", "bones_mesh", "depth_mesh"].includes(String(next.view_mode)) ? String(next.view_mode) : "bones_only";
  const silhouetteModel = ["female", "male"].includes(String(next.silhouette_model)) ? String(next.silhouette_model) : "female";
  const silhouetteSource = ["procedural", "custom_asset"].includes(String(next.silhouette_source)) ? String(next.silhouette_source) : "procedural";
  const customAssetUrl = String(next.custom_asset_url || "/extensions/MKRShift_Nodes/assets/pose_studio/custom_silhouette.glb").trim();
  return { view_mode: viewMode, silhouette_model: silhouetteModel, silhouette_source: silhouetteSource, custom_asset_url: customAssetUrl };
}

function clamp(value, lo, hi, fallback) {
  const num = Number.isFinite(Number(value)) ? Number(value) : Number(fallback);
  return Math.max(lo, Math.min(hi, num));
}

function hideWidget(widget) {
  if (!widget) return;
  widget.__mkrPoseOrigType ??= widget.type;
  widget.__mkrPoseOrigVisible ??= widget.visible;
  widget.__mkrPoseOrigOptions ??= widget.options ? { ...widget.options } : null;
  widget.hidden = true;
  widget.serialize = true;
  widget.type = "hidden";
  widget.visible = false;
  widget.options = {
    ...(widget.options || {}),
    hidden: true,
    visible: false,
    serialize: true,
  };
  widget.__mkrPoseOrigComputeSize ??= widget.computeSize;
  widget.__mkrPoseOrigComputeLayoutSize ??= widget.computeLayoutSize;
  widget.computeSize = () => [0, 0];
  widget.computeLayoutSize = () => ({ minHeight: 0, maxHeight: 0, minWidth: 0 });
  widget.draw = () => {};
  widget.disabled = true;
  widget.last_y = 0;
  widget.y = 0;
  widget.__mkrPoseHidden = true;
}

function compactNodeWidgets(node, hiddenWidgets, domWidgetName, keepNames = new Set()) {
  if (!node || !Array.isArray(node.widgets)) return;
  const keep = [];
  const serialOrder = [];
  const hiddenSet = new Set(hiddenWidgets.filter(Boolean));

  for (const widget of node.widgets) {
    if (!widget) continue;
    const name = String(widget.name || "");
    if (name === domWidgetName) {
      keep.push(widget);
      continue;
    }
    if (keepNames.has(name)) {
      keep.push(widget);
      continue;
    }
    if (hiddenSet.has(widget)) {
      serialOrder.push(widget);
      continue;
    }
    keep.push(widget);
  }

  node.widgets = keep;
  node.__mkrPoseSerialWidgets = serialOrder;
  node.__mkrPoseWidgetByName = new Map(
    [...keep, ...serialOrder]
      .filter(Boolean)
      .map((widget) => [String(widget.name || ""), widget])
      .filter(([name]) => !!name)
  );
  node.widgets_values = serialOrder.map((widget) => widget.value);
}

function removeLegacyPoseInputs(node) {
  if (!node || !Array.isArray(node.inputs)) return;
  const legacyNames = new Set(["settings_json", "capture_w", "capture_h", "pose_reference_image", "pose_from_image_mode", "pose_image_strength"]);
  const keep = [];
  let changed = false;
  for (const input of node.inputs) {
    const name = String(input?.name || "");
    if (legacyNames.has(name)) {
      changed = true;
      continue;
    }
    keep.push(input);
  }
  if (changed) {
    node.inputs = keep;
  }
}

function removeLegacyPoseWidgets(node) {
  if (!node || !Array.isArray(node.widgets)) return;
  const legacyNames = new Set(["capture_w", "capture_h", "pose_reference_image", "pose_from_image_mode", "pose_image_strength"]);
  let changed = false;
  node.widgets = node.widgets.filter((widget) => {
    const keep = !legacyNames.has(String(widget?.name || ""));
    if (!keep) changed = true;
    return keep;
  });
  if (changed) {
    node.__mkrPoseSerialWidgets = Array.isArray(node.__mkrPoseSerialWidgets)
      ? node.__mkrPoseSerialWidgets.filter((widget) => !legacyNames.has(String(widget?.name || "")))
      : node.__mkrPoseSerialWidgets;
  }
}

function ensurePoseSerializeHook(node) {
  if (!node) return;
  const currentSerialize = typeof node.onSerialize === "function" ? node.onSerialize : null;
  if (!node.__mkrPoseBaseOnSerialize) {
    node.__mkrPoseBaseOnSerialize = currentSerialize && !currentSerialize.__mkrPoseSerializeWrapper ? currentSerialize : null;
  } else if (node.__mkrPoseBaseOnSerialize === currentSerialize && currentSerialize?.__mkrPoseSerializeWrapper) {
    node.__mkrPoseBaseOnSerialize = null;
  }
  if (node.__mkrPoseSerializeHookInstalled) return;
  node.__mkrPoseSerializeHookInstalled = true;
  const wrapper = function onSerializePoseStudio(o) {
    this.__mkrPoseBaseOnSerialize?.call(this, o);
    if (Array.isArray(this.__mkrPoseSerialWidgets)) {
      o.widgets_values = this.__mkrPoseSerialWidgets.map((entry) => entry?.value);
    }
  };
  wrapper.__mkrPoseSerializeWrapper = true;
  node.onSerialize = wrapper;
}

function normalizePoseWidgetTopology(node) {
  if (!node) return;
  const backing = ensurePoseBackingWidgets(node);
  const hiddenWidgets = Object.values(backing).filter(Boolean);

  hiddenWidgets.forEach(hideWidget);

  if (Array.isArray(node.widgets)) {
    compactNodeWidgets(node, hiddenWidgets, "mkr_pose_studio_panel");
  }
  ensurePoseSerializeHook(node);
  node.widgets_values = Array.isArray(node.__mkrPoseSerialWidgets)
    ? node.__mkrPoseSerialWidgets.map((entry) => entry?.value)
    : node.widgets_values;
}

function trySetWidgetY(widget, y) {
  let changed = false;
  for (const key of ["y", "last_y", "_y"]) {
    const current = Number(widget?.[key]);
    if (Number.isFinite(current) && Math.abs(current - y) <= 0.5) continue;
    try {
      widget[key] = y;
      changed = true;
    } catch {
    }
  }
  return changed;
}

function layoutPoseDomWidget(node, domWidget) {
  if (!node || !domWidget) return;
  const targetY = 6;
  const nodeWidth = Math.round(Number(node.size?.[0]) || DEFAULT_NODE_WIDTH);
  const width = Math.max(320, nodeWidth - 18);
  const height = DOM_WIDGET_HEIGHT;

  domWidget.computeSize = () => [width, height];
  domWidget.computeLayoutSize = () => ({ minHeight: height, maxHeight: height, minWidth: 0, preferredWidth: width });
  if (domWidget.element?.style) {
    domWidget.element.style.width = `${width}px`;
    domWidget.element.style.maxWidth = "100%";
    domWidget.element.style.height = `${height}px`;
    domWidget.element.style.minHeight = `${height}px`;
    domWidget.element.style.maxHeight = `${height}px`;
    domWidget.element.style.overflow = "hidden";
    domWidget.element.style.boxSizing = "border-box";
  }
  trySetWidgetY(domWidget, targetY);

  const minNodeH = targetY + height + 12;
  const minNodeW = Math.max(360, width + 14);
  node.__mkrPoseMinSize = [minNodeW, minNodeH];
  if (!Array.isArray(node.size) || node.size.length < 2) {
    node.size = [minNodeW, minNodeH];
    node.__mkrPoseLockedSize = [node.size[0], node.size[1]];
  }
}

function destroyStudioOverlay(node) {
  const state = studioOverlays.get(node);
  if (!state) return;
  try {
    state.panel?.__mkrPoseDispose?.();
  } catch {
  }
  try {
    state.backdrop?.remove();
  } catch {
  }
  if (state.onKeyDown) {
    document.removeEventListener("keydown", state.onKeyDown, true);
  }
  studioOverlays.delete(node);
}

function matMul(a, b) {
  const out = [[0, 0, 0], [0, 0, 0], [0, 0, 0]];
  for (let row = 0; row < 3; row += 1) {
    for (let col = 0; col < 3; col += 1) {
      out[row][col] = a[row][0] * b[0][col] + a[row][1] * b[1][col] + a[row][2] * b[2][col];
    }
  }
  return out;
}

function matVec(m, v) {
  return [
    m[0][0] * v[0] + m[0][1] * v[1] + m[0][2] * v[2],
    m[1][0] * v[0] + m[1][1] * v[1] + m[1][2] * v[2],
    m[2][0] * v[0] + m[2][1] * v[1] + m[2][2] * v[2],
  ];
}

function rotX(deg) {
  const rad = (deg * Math.PI) / 180;
  const c = Math.cos(rad);
  const s = Math.sin(rad);
  return [[1, 0, 0], [0, c, -s], [0, s, c]];
}

function rotY(deg) {
  const rad = (deg * Math.PI) / 180;
  const c = Math.cos(rad);
  const s = Math.sin(rad);
  return [[c, 0, s], [0, 1, 0], [-s, 0, c]];
}

function rotZ(deg) {
  const rad = (deg * Math.PI) / 180;
  const c = Math.cos(rad);
  const s = Math.sin(rad);
  return [[c, -s, 0], [s, c, 0], [0, 0, 1]];
}

function composeRot(rx = 0, ry = 0, rz = 0) {
  return matMul(rotY(ry), matMul(rotX(rx), rotZ(rz)));
}

function addVec(a, b) {
  return [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
}

function subVec(a, b) {
  return [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
}

function scaleVec(v, s) {
  return [v[0] * s, v[1] * s, v[2] * s];
}

function dotVec(a, b) {
  return a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
}

function crossVec(a, b) {
  return [
    a[1] * b[2] - a[2] * b[1],
    a[2] * b[0] - a[0] * b[2],
    a[0] * b[1] - a[1] * b[0],
  ];
}

function lengthVec(v) {
  return Math.hypot(v[0], v[1], v[2]);
}

function normalizeVec(v, fallback = [1, 0, 0]) {
  const len = lengthVec(v);
  if (len <= 1e-5) return [...fallback];
  return [v[0] / len, v[1] / len, v[2] / len];
}

function getJointBasis(points, jointName) {
  return {
    x: [1, 0, 0],
    y: [0, 1, 0],
    z: [0, 0, 1],
  };
}

function defaultSettings() {
  const controls = {};
  for (const [key, spec] of Object.entries(CONTROL_SPECS)) {
    controls[key] = spec.default;
  }
  return {
    schema: "mkr_pose_studio_v1",
    schema_version: SETTINGS_SCHEMA_VERSION,
    pose_name: "Neutral",
    pose_preset: "neutral",
    mirror_mode: "off",
    view: { yaw: 28, pitch: 8, zoom: 1, pan_x: 0, pan_y: 0 },
    display: {
      view_mode: "bones_only",
      silhouette_model: "female",
      silhouette_source: "procedural",
      custom_asset_url: "/extensions/MKRShift_Nodes/assets/pose_studio/custom_silhouette.glb",
    },
    image_fit: {
      fit_mode: "fit_from_image_structured",
      strength: 1,
      selected_anchor: "head",
      anchors: {},
      frame_hint: null,
      reference_image_data_url: "",
      reference_image_name: "",
      enabled_groups: Object.fromEntries(Object.keys(IMAGE_FIT_ANCHOR_GROUPS).map((key) => [key, true])),
    },
    controls,
  };
}

function sanitizeImageFitSettings(imageFit) {
  const next = imageFit && typeof imageFit === "object" && !Array.isArray(imageFit) ? imageFit : {};
  const rawAnchors = next.anchors && typeof next.anchors === "object" && !Array.isArray(next.anchors) ? next.anchors : {};
  const rawEnabledGroups =
    next.enabled_groups && typeof next.enabled_groups === "object" && !Array.isArray(next.enabled_groups) ? next.enabled_groups : {};
  const rawFrameHint = next.frame_hint && typeof next.frame_hint === "object" && !Array.isArray(next.frame_hint) ? next.frame_hint : null;
  const anchors = {};
  for (const [key] of IMAGE_FIT_ANCHOR_OPTIONS) {
    const entry = rawAnchors[key];
    if (!entry || typeof entry !== "object" || Array.isArray(entry)) continue;
    anchors[key] = {
      x: clamp(entry.x, 0, 1, 0.5),
      y: clamp(entry.y, 0, 1, 0.5),
    };
  }
  const selectedAnchor = IMAGE_FIT_ANCHOR_SET.has(String(next.selected_anchor || "head")) ? String(next.selected_anchor) : "head";
  const fitMode = ["fit_from_image", "fit_from_image_structured"].includes(String(next.fit_mode))
    ? String(next.fit_mode)
    : "fit_from_image_structured";
  const strength = clamp(next.strength, 0, 1, 1);
  const referenceImageDataUrl = String(next.reference_image_data_url || "").trim();
  const referenceImageName = String(next.reference_image_name || "").trim();
  const enabledGroups = {};
  for (const key of Object.keys(IMAGE_FIT_ANCHOR_GROUPS)) {
    enabledGroups[key] = Boolean(rawEnabledGroups[key] ?? true);
  }
  for (const [legacyKey, mappedKeys] of Object.entries(LEGACY_IMAGE_FIT_GROUP_MAP)) {
    if (!(legacyKey in rawEnabledGroups)) continue;
    for (const mappedKey of mappedKeys) {
      if (!(mappedKey in rawEnabledGroups)) {
        enabledGroups[mappedKey] = Boolean(rawEnabledGroups[legacyKey]);
      }
    }
  }
  const frameHint = rawFrameHint ? {
    cx: clamp(rawFrameHint.cx, 0, 1, 0.5),
    cy: clamp(rawFrameHint.cy, 0, 1, 0.5),
    bw: clamp(rawFrameHint.bw, 0, 1, 0),
    bh: clamp(rawFrameHint.bh, 0, 1, 0),
  } : null;
  return {
    fit_mode: fitMode,
    strength,
    selected_anchor: selectedAnchor,
    anchors,
    frame_hint: frameHint,
    reference_image_data_url: referenceImageDataUrl,
    reference_image_name: referenceImageName,
    enabled_groups: enabledGroups,
  };
}

function applyPreset(data, presetName) {
  const preset = POSE_PRESETS[presetName] || {};
  for (const [key, spec] of Object.entries(CONTROL_SPECS)) {
    data.controls[key] = spec.default;
  }
  for (const [key, value] of Object.entries(preset)) {
    if (!CONTROL_SPECS[key]) continue;
    const spec = CONTROL_SPECS[key];
    data.controls[key] = clamp(value, spec.min, spec.max, spec.default);
  }
  data.pose_preset = presetName;
}

function mirrorControls(data, sourceMode) {
  if (sourceMode !== "left_to_right" && sourceMode !== "right_to_left") return;
  for (const [leftKey, rightKey, mode] of LEFT_RIGHT_KEYS) {
    if (sourceMode === "left_to_right") {
      data.controls[rightKey] = mode === "same" ? data.controls[leftKey] : -data.controls[leftKey];
    } else {
      data.controls[leftKey] = mode === "same" ? data.controls[rightKey] : -data.controls[rightKey];
    }
  }
  data.mirror_mode = sourceMode;
}

function swapPoseSides(data) {
  for (const [leftKey, rightKey, mode] of LEFT_RIGHT_KEYS) {
    const leftValue = Number(data.controls[leftKey] ?? CONTROL_SPECS[leftKey].default);
    const rightValue = Number(data.controls[rightKey] ?? CONTROL_SPECS[rightKey].default);
    data.controls[leftKey] = mode === "same" ? rightValue : -rightValue;
    data.controls[rightKey] = mode === "same" ? leftValue : -leftValue;
  }
}

function ensureSettings(node) {
  const backing = ensurePoseBackingWidgets(node);
  const widget = backing.settings_json;
  let data = {};
  try {
    data = widget?.value ? JSON.parse(widget.value) : {};
  } catch {
    data = {};
  }
  if (!data || typeof data !== "object" || Array.isArray(data)) data = {};

  const base = defaultSettings();
  base.pose_name = String(data.pose_name || base.pose_name).trim() || base.pose_name;
  base.pose_preset = PRESET_OPTIONS.includes(String(data.pose_preset))
    ? String(data.pose_preset)
    : base.pose_preset;
  base.mirror_mode = ["off", "left_to_right", "right_to_left"].includes(String(data.mirror_mode))
    ? String(data.mirror_mode)
    : base.mirror_mode;

  const view = data.view && typeof data.view === "object" && !Array.isArray(data.view) ? data.view : {};
  base.view = {
    yaw: clamp(view.yaw, -180, 180, base.view.yaw),
    pitch: clamp(view.pitch, -85, 85, base.view.pitch),
    zoom: clamp(view.zoom, 0.4, 2.4, base.view.zoom),
    pan_x: clamp(view.pan_x, -4, 4, base.view.pan_x),
    pan_y: clamp(view.pan_y, -4, 4, base.view.pan_y),
  };

  const rawControls = data.controls && typeof data.controls === "object" && !Array.isArray(data.controls) ? data.controls : {};
  for (const [key, spec] of Object.entries(CONTROL_SPECS)) {
    base.controls[key] = clamp(rawControls[key], spec.min, spec.max, spec.default);
  }
  base.display = sanitizeDisplaySettings(data.display);
  base.image_fit = sanitizeImageFitSettings(data.image_fit);
  if (!data.image_fit || typeof data.image_fit !== "object") {
    base.image_fit.fit_mode = ["fit_from_image", "fit_from_image_structured"].includes(String(backing.pose_from_image_mode?.value))
      ? String(backing.pose_from_image_mode.value)
      : base.image_fit.fit_mode;
    base.image_fit.strength = clamp(backing.pose_image_strength?.value, 0, 1, base.image_fit.strength);
  }
  return { widget, data: base };
}

function writeSettings(node, widget, data) {
  widget.value = JSON.stringify(data);
  node.setDirtyCanvas(true, true);
}

function computePosePoints(data) {
  const c = data.controls;
  const pelvis = [0, 1.05, 0];
  const rootRot = composeRot(c.root_pitch, c.root_yaw, c.root_roll);
  const spineRot = matMul(rootRot, composeRot(c.spine_bend, c.spine_twist, 0));
  const headRot = matMul(spineRot, composeRot(c.head_pitch, c.head_yaw, c.head_roll));

  const spine = addVec(pelvis, matVec(rootRot, [0, 0.22, 0]));
  const chest = addVec(spine, matVec(spineRot, [0, 0.24, 0]));
  const neck = addVec(chest, matVec(spineRot, [0, 0.15, 0]));
  const head = addVec(neck, matVec(headRot, [0, 0.18, 0]));
  const eye_l = addVec(head, matVec(headRot, [-0.055, 0.025, 0.075]));
  const eye_r = addVec(head, matVec(headRot, [0.055, 0.025, 0.075]));
  const chin = addVec(head, matVec(headRot, [0, -0.07, 0.085]));

  const points = { pelvis, spine, chest, neck, head, eye_l, eye_r, chin };
  for (const [sideName, sign] of [["l", -1], ["r", 1]]) {
    const shoulder = addVec(chest, matVec(spineRot, [0.22 * sign, 0.05, 0]));
    const shoulderRot = matMul(
      spineRot,
      composeRot(-c[`arm_forward_${sideName}`], c[`arm_twist_${sideName}`], -sign * c[`arm_raise_${sideName}`])
    );
    const elbow = addVec(shoulder, matVec(shoulderRot, [0.32 * sign, -0.06, 0.01]));
    const elbowRot = matMul(shoulderRot, composeRot(0, c[`wrist_twist_${sideName}`] * 0.12, -sign * c[`elbow_bend_${sideName}`]));
    const wrist = addVec(elbow, matVec(elbowRot, [0.28 * sign, -0.04, 0.02]));
    const hand = addVec(wrist, matVec(elbowRot, [0.16 * sign, -0.02, 0.04]));
    const thumb = addVec(hand, matVec(elbowRot, [0.045 * sign, 0.012, 0.055]));
    const index = addVec(hand, matVec(elbowRot, [0.085 * sign, -0.004, 0.105]));

    const hip = addVec(pelvis, matVec(rootRot, [0.12 * sign, -0.04, 0]));
    const hipRot = matMul(rootRot, composeRot(-c[`hip_lift_${sideName}`], 0, -sign * c[`hip_side_${sideName}`]));
    const knee = addVec(hip, matVec(hipRot, [0.06 * sign, -0.5, 0.02]));
    const kneeRot = matMul(hipRot, composeRot(c[`knee_bend_${sideName}`], 0, 0));
    const ankle = addVec(knee, matVec(kneeRot, [0.03 * sign, -0.46, 0.02]));
    const footRot = matMul(kneeRot, composeRot(-c[`foot_point_${sideName}`], 0, 0));
    const heel = addVec(ankle, matVec(footRot, [-0.035 * sign, -0.015, -0.085]));
    const toe = addVec(ankle, matVec(footRot, [0.05 * sign, -0.03, 0.22]));

    points[`shoulder_${sideName}`] = shoulder;
    points[`elbow_${sideName}`] = elbow;
    points[`wrist_${sideName}`] = wrist;
    points[`hand_${sideName}`] = hand;
    points[`thumb_${sideName}`] = thumb;
    points[`index_${sideName}`] = index;
    points[`hip_${sideName}`] = hip;
    points[`knee_${sideName}`] = knee;
    points[`ankle_${sideName}`] = ankle;
    points[`heel_${sideName}`] = heel;
    points[`toe_${sideName}`] = toe;
  }
  return points;
}

function descriptorFromData(data) {
  const tags = [String(data.pose_preset || "neutral").replace(/_/g, " ")];
  if (Math.abs(Number(data.controls.spine_twist || 0)) > 8) tags.push("torso twist");
  if (Math.max(Number(data.controls.arm_raise_l || 0), Number(data.controls.arm_raise_r || 0)) > 45) {
    tags.push("raised arm read");
  } else if (Math.max(Number(data.controls.arm_raise_l || 0), Number(data.controls.arm_raise_r || 0)) > 20) {
    tags.push("open arm gesture");
  }
  if (Number(data.controls.knee_bend_l || 0) > 22 || Number(data.controls.knee_bend_r || 0) > 22) {
    tags.push("active leg bend");
  }
  if (Math.abs(Number(data.controls.head_yaw || 0)) > 10) tags.push("head turn");
  if (
    Math.abs(Number(data.controls.root_roll || 0)) > 5 ||
    Math.abs(Number(data.controls.hip_side_l || 0) - Number(data.controls.hip_side_r || 0)) > 8
  ) {
    tags.push("weight shift");
  }
  return tags.join(", ");
}

function setControlValue(data, key, nextValue) {
  const spec = CONTROL_SPECS[key];
  if (!spec) return;
  data.controls[key] = clamp(nextValue, spec.min, spec.max, spec.default);
}

function applyJointToolDelta(data, jointName, toolName, dx, dy) {
  const x = Number(dx || 0);
  const y = Number(dy || 0);
  if (!jointName || toolName === "cursor" || toolName === "orbit") return;

  if (toolName === "move") {
    if (["pelvis", "spine", "chest"].includes(jointName)) {
      setControlValue(data, "root_yaw", data.controls.root_yaw + x * 0.32);
      setControlValue(data, "root_pitch", data.controls.root_pitch - y * 0.18);
      setControlValue(data, "spine_bend", data.controls.spine_bend - y * 0.24);
      setControlValue(data, "spine_twist", data.controls.spine_twist + x * 0.28);
      return;
    }
    if (["neck", "head", "eye_l", "eye_r", "chin"].includes(jointName)) {
      setControlValue(data, "head_yaw", data.controls.head_yaw + x * 0.34);
      setControlValue(data, "head_pitch", data.controls.head_pitch - y * 0.28);
      return;
    }
    if (jointName.endsWith("_l") || jointName.endsWith("_r")) {
      const side = jointName.endsWith("_l") ? "l" : "r";
      const sign = side === "l" ? 1 : -1;
      if (jointName.startsWith("shoulder_") || jointName.startsWith("elbow_") || jointName.startsWith("wrist_") || jointName.startsWith("hand_") || jointName.startsWith("thumb_") || jointName.startsWith("index_")) {
        setControlValue(data, `arm_raise_${side}`, data.controls[`arm_raise_${side}`] - y * 0.44);
        setControlValue(data, `arm_forward_${side}`, data.controls[`arm_forward_${side}`] + x * 0.46 * sign);
        if (jointName.startsWith("elbow_") || jointName.startsWith("wrist_") || jointName.startsWith("hand_") || jointName.startsWith("thumb_") || jointName.startsWith("index_")) {
          setControlValue(data, `elbow_bend_${side}`, data.controls[`elbow_bend_${side}`] + (x - y) * 0.18);
        }
        return;
      }
      if (jointName.startsWith("hip_") || jointName.startsWith("knee_") || jointName.startsWith("ankle_") || jointName.startsWith("heel_") || jointName.startsWith("toe_")) {
        setControlValue(data, `hip_lift_${side}`, data.controls[`hip_lift_${side}`] - y * 0.32);
        setControlValue(data, `hip_side_${side}`, data.controls[`hip_side_${side}`] + x * 0.22 * sign);
        if (jointName.startsWith("knee_") || jointName.startsWith("ankle_") || jointName.startsWith("heel_") || jointName.startsWith("toe_")) {
          setControlValue(data, `knee_bend_${side}`, data.controls[`knee_bend_${side}`] - y * 0.26);
        }
      }
    }
    return;
  }

  if (toolName === "rotate") {
    if (["pelvis", "spine", "chest"].includes(jointName)) {
      setControlValue(data, "root_roll", data.controls.root_roll + x * 0.24);
      setControlValue(data, "spine_twist", data.controls.spine_twist + x * 0.32);
      return;
    }
    if (["neck", "head", "eye_l", "eye_r", "chin"].includes(jointName)) {
      setControlValue(data, "head_roll", data.controls.head_roll + x * 0.28);
      setControlValue(data, "head_yaw", data.controls.head_yaw + x * 0.2);
      return;
    }
    if (jointName.endsWith("_l") || jointName.endsWith("_r")) {
      const side = jointName.endsWith("_l") ? "l" : "r";
      const sign = side === "l" ? 1 : -1;
      if (jointName.startsWith("shoulder_") || jointName.startsWith("elbow_") || jointName.startsWith("wrist_") || jointName.startsWith("hand_") || jointName.startsWith("thumb_") || jointName.startsWith("index_")) {
        setControlValue(data, `arm_twist_${side}`, data.controls[`arm_twist_${side}`] + x * 0.44 * sign);
        setControlValue(data, `wrist_twist_${side}`, data.controls[`wrist_twist_${side}`] + x * 0.32 * sign);
        return;
      }
      if (jointName.startsWith("hip_") || jointName.startsWith("knee_") || jointName.startsWith("ankle_") || jointName.startsWith("heel_") || jointName.startsWith("toe_")) {
        setControlValue(data, `foot_point_${side}`, data.controls[`foot_point_${side}`] - y * 0.24);
        setControlValue(data, `hip_side_${side}`, data.controls[`hip_side_${side}`] + x * 0.16 * sign);
      }
    }
  }
}

function applyJointAxisDelta(data, jointName, toolName, axis, amount) {
  const value = Number(amount || 0);
  if (!jointName || !axis || !value || toolName === "cursor" || toolName === "orbit") return;

  if (toolName === "move") {
    const axisVec = axis === "x" ? [1, 0, 0] : axis === "y" ? [0, 1, 0] : [0, 0, 1];
    const candidates = getJointControlCandidates(jointName);
    applyWorldAxisMoveDelta(data, jointName, axisVec, value, candidates);
    return;
  }

  if (["pelvis", "spine", "chest"].includes(jointName)) {
    if (axis === "x") setControlValue(data, jointName === "pelvis" ? "root_yaw" : "spine_twist", data.controls[jointName === "pelvis" ? "root_yaw" : "spine_twist"] + value * 0.42);
    if (axis === "y") setControlValue(data, jointName === "pelvis" ? "root_pitch" : "spine_bend", data.controls[jointName === "pelvis" ? "root_pitch" : "spine_bend"] - value * 0.36);
    if (axis === "z") setControlValue(data, "root_roll", data.controls.root_roll + value * 0.34);
    return;
  }

  if (["neck", "head", "eye_l", "eye_r", "chin"].includes(jointName)) {
    if (axis === "x") setControlValue(data, "head_yaw", data.controls.head_yaw + value * 0.42);
    if (axis === "y") setControlValue(data, "head_pitch", data.controls.head_pitch - value * 0.36);
    if (axis === "z") setControlValue(data, "head_roll", data.controls.head_roll + value * 0.34);
    return;
  }

  if (!jointName.endsWith("_l") && !jointName.endsWith("_r")) return;
  const side = jointName.endsWith("_l") ? "l" : "r";
  const sign = side === "l" ? 1 : -1;

  if (/^(shoulder|elbow|wrist|hand|thumb|index)_/.test(jointName)) {
    if (jointName.startsWith("shoulder_")) {
      if (axis === "x") setControlValue(data, `arm_forward_${side}`, data.controls[`arm_forward_${side}`] + value * 0.52 * sign);
      if (axis === "y") setControlValue(data, `arm_raise_${side}`, data.controls[`arm_raise_${side}`] - value * 0.48);
      if (axis === "z") setControlValue(data, `arm_twist_${side}`, data.controls[`arm_twist_${side}`] + value * 0.46 * sign);
      return;
    }
    if (jointName.startsWith("elbow_")) {
      if (axis === "x" || axis === "y") setControlValue(data, `elbow_bend_${side}`, data.controls[`elbow_bend_${side}`] + value * 0.48);
      if (axis === "z") setControlValue(data, `arm_twist_${side}`, data.controls[`arm_twist_${side}`] + value * 0.34 * sign);
      return;
    }
    if (jointName.startsWith("wrist_") || jointName.startsWith("hand_") || jointName.startsWith("thumb_") || jointName.startsWith("index_")) {
      if (axis === "x") setControlValue(data, `wrist_twist_${side}`, data.controls[`wrist_twist_${side}`] + value * 0.52 * sign);
      if (axis === "y") setControlValue(data, `elbow_bend_${side}`, data.controls[`elbow_bend_${side}`] + value * 0.16);
      if (axis === "z") setControlValue(data, `arm_forward_${side}`, data.controls[`arm_forward_${side}`] + value * 0.22 * sign);
    }
    return;
  }

  if (/^(hip|knee|ankle|heel|toe)_/.test(jointName)) {
    if (jointName.startsWith("hip_")) {
      if (axis === "x") setControlValue(data, `hip_side_${side}`, data.controls[`hip_side_${side}`] + value * 0.34 * sign);
      if (axis === "y") setControlValue(data, `hip_lift_${side}`, data.controls[`hip_lift_${side}`] - value * 0.42);
      if (axis === "z") setControlValue(data, `foot_point_${side}`, data.controls[`foot_point_${side}`] - value * 0.18);
      return;
    }
    if (jointName.startsWith("knee_")) {
      if (axis === "x" || axis === "y") setControlValue(data, `knee_bend_${side}`, data.controls[`knee_bend_${side}`] + value * 0.46);
      if (axis === "z") setControlValue(data, `hip_side_${side}`, data.controls[`hip_side_${side}`] + value * 0.2 * sign);
      return;
    }
    if (jointName.startsWith("ankle_") || jointName.startsWith("heel_") || jointName.startsWith("toe_")) {
      if (axis === "x" || axis === "y") setControlValue(data, `foot_point_${side}`, data.controls[`foot_point_${side}`] - value * 0.34);
      if (axis === "z") setControlValue(data, `knee_bend_${side}`, data.controls[`knee_bend_${side}`] + value * 0.14);
    }
  }
}

function getJointControlCandidates(jointName) {
  if (["pelvis", "spine", "chest"].includes(jointName)) {
    return ["root_yaw", "root_pitch", "root_roll", "spine_bend", "spine_twist"];
  }
  if (["neck", "head", "eye_l", "eye_r", "chin"].includes(jointName)) {
    return ["head_yaw", "head_pitch", "head_roll", "spine_bend", "spine_twist"];
  }
  if (!jointName.endsWith("_l") && !jointName.endsWith("_r")) return [];
  const side = jointName.endsWith("_l") ? "l" : "r";
  if (/^(shoulder|elbow|wrist|hand|thumb|index)_/.test(jointName)) {
    return [`arm_raise_${side}`, `arm_forward_${side}`, `arm_twist_${side}`, `elbow_bend_${side}`, `wrist_twist_${side}`];
  }
  if (/^(hip|knee|ankle|heel|toe)_/.test(jointName)) {
    return [`hip_lift_${side}`, `hip_side_${side}`, `knee_bend_${side}`, `foot_point_${side}`];
  }
  return [];
}

function clonePoseData(data) {
  return {
    ...data,
    controls: { ...(data.controls || {}) },
    view: { ...(data.view || {}) },
  };
}

function applyWorldAxisMoveDelta(data, jointName, axisVec, worldDelta, candidates) {
  if (!Array.isArray(candidates) || !candidates.length) return;
  const basePoints = computePosePoints(data);
  const basePoint = basePoints[jointName];
  if (!basePoint) return;
  const step = 1.0;
  const influences = [];

  for (const controlKey of candidates) {
    const testData = clonePoseData(data);
    setControlValue(testData, controlKey, Number(testData.controls[controlKey] || 0) + step);
    const testPoints = computePosePoints(testData);
    const movedPoint = testPoints[jointName];
    if (!movedPoint) continue;
    const derivative = dotVec(subVec(movedPoint, basePoint), axisVec) / step;
    if (Math.abs(derivative) > 1e-4) {
      influences.push({ controlKey, derivative, strength: Math.abs(derivative) });
    }
  }

  influences.sort((a, b) => b.strength - a.strength);
  const active = influences.slice(0, 3);
  const denom = active.reduce((sum, entry) => sum + entry.derivative * entry.derivative, 0);
  if (denom <= 1e-6) return;

  for (const entry of active) {
    const controlDelta = (worldDelta * entry.derivative) / denom;
    setControlValue(data, entry.controlKey, Number(data.controls[entry.controlKey] || 0) + controlDelta);
  }
}

function projectPoseToViewport(viewport, data, camera3D = null) {
  const width = Math.max(180, viewport.clientWidth || 260);
  const height = Math.max(180, viewport.clientHeight || 260);
  const points = computePosePoints(data);
  const screen = {};

  if (camera3D && THREE) {
    for (const [key, pos] of Object.entries(points)) {
      const projected = new THREE.Vector3(pos[0], pos[1], pos[2]).project(camera3D);
      screen[key] = [
        (projected.x * 0.5 + 0.5) * width,
        (-projected.y * 0.5 + 0.5) * height,
      ];
    }
    return { width, height, screen };
  }

  const yaw = -Number(data.view.yaw || 0);
  const pitch = -Number(data.view.pitch || 0);
  const zoom = Number(data.view.zoom || 1);
  const rot = matMul(rotX(pitch), rotY(yaw));
  const flat = {};
  const all = [];
  for (const [key, pos] of Object.entries(points)) {
    const v = matVec(rot, pos);
    flat[key] = [v[0], v[1]];
    all.push(v);
  }
  const xs = all.map((v) => v[0]);
  const ys = all.map((v) => v[1]);
  const frameX = width * 0.06;
  const frameY = height * 0.04;
  const frameW = width * 0.88;
  const frameH = height * 0.92;
  const scale = Math.min(
    (frameW * 0.92) / Math.max(0.001, Math.max(...xs) - Math.min(...xs)),
    (frameH * 0.94) / Math.max(0.001, Math.max(...ys) - Math.min(...ys))
  ) * zoom;
  const centerX = width * 0.5 + (Number(data.view.pan_x) || 0) * scale;
  const centerY = frameY + frameH * 0.78 + (Number(data.view.pan_y) || 0) * scale;
  for (const [key, [x, y]] of Object.entries(flat)) {
    screen[key] = [centerX + x * scale, centerY - (y - 1.0) * scale];
  }
  return { width, height, screen };
}

function computeExportFrameRect(stageWidth, stageHeight, captureWidth, captureHeight) {
  const width = Math.max(1, Number(stageWidth) || 1);
  const height = Math.max(1, Number(stageHeight) || 1);
  const pad = Math.max(18, Math.round(Math.min(width, height) * 0.045));
  const innerW = Math.max(1, width - pad * 2);
  const innerH = Math.max(1, height - pad * 2);
  const aspect = Math.max(1, Number(captureWidth) || 1024) / Math.max(1, Number(captureHeight) || 1024);

  let frameW = innerW;
  let frameH = frameW / aspect;
  if (frameH > innerH) {
    frameH = innerH;
    frameW = frameH * aspect;
  }
  return {
    x: Math.round((width - frameW) * 0.5),
    y: Math.round((height - frameH) * 0.5),
    w: Math.round(frameW),
    h: Math.round(frameH),
  };
}

function renderPoseMaskForFit(data, width = 128, height = 128) {
  const points = computePosePoints(data);
  const yaw = -Number(FIT_VIEW.yaw || 0);
  const pitch = -Number(FIT_VIEW.pitch || 0);
  const zoom = Number(FIT_VIEW.zoom || 1);
  const rot = matMul(rotX(pitch), rotY(yaw));
  const projected = {};
  const all = [];
  for (const [key, pos] of Object.entries(points)) {
    const v = matVec(rot, pos);
    projected[key] = [v[0], v[1]];
    all.push(v);
  }
  const xs = all.map((v) => v[0]);
  const ys = all.map((v) => v[1]);
  const spanX = Math.max(0.001, Math.max(...xs) - Math.min(...xs));
  const spanY = Math.max(0.001, Math.max(...ys) - Math.min(...ys));
  const scale = Math.min((width * 0.56) / spanX, (height * 0.72) / spanY) * zoom;
  const centerX = width * 0.5;
  const centerY = height * 0.63;

  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d");
  if (!ctx) return new Uint8Array(width * height);
  ctx.clearRect(0, 0, width, height);
  const screen = {};
  for (const [key, [x, y]] of Object.entries(projected)) {
    screen[key] = [centerX + x * scale, centerY - (y - 1.0) * scale];
  }
  ctx.strokeStyle = "#fff";
  ctx.fillStyle = "#fff";
  ctx.lineWidth = 9;
  for (const [start, end] of POSE_BONES) {
    ctx.beginPath();
    ctx.moveTo(screen[start][0], screen[start][1]);
    ctx.lineTo(screen[end][0], screen[end][1]);
    ctx.stroke();
  }
  for (const point of Object.values(screen)) {
    ctx.beginPath();
    ctx.arc(point[0], point[1], 6, 0, Math.PI * 2);
    ctx.fill();
  }
  const imageData = ctx.getImageData(0, 0, width, height).data;
  const out = new Uint8Array(width * height);
  for (let i = 0; i < out.length; i += 1) {
    out[i] = imageData[i * 4] >= 96 ? 1 : 0;
  }
  return out;
}

function flipMaskHorizontal(mask, width, height) {
  const out = new Uint8Array(mask.length);
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      out[y * width + x] = mask[y * width + (width - 1 - x)];
    }
  }
  return out;
}

function extractReferenceMaskFromImage(image, targetSize = 128) {
  const canvas = document.createElement("canvas");
  canvas.width = targetSize;
  canvas.height = targetSize;
  const ctx = canvas.getContext("2d");
  if (!ctx) return new Uint8Array(targetSize * targetSize);
  ctx.clearRect(0, 0, targetSize, targetSize);
  const aspect = image.naturalWidth / Math.max(1, image.naturalHeight);
  let drawW = targetSize;
  let drawH = drawW / Math.max(0.001, aspect);
  if (drawH > targetSize) {
    drawH = targetSize;
    drawW = drawH * aspect;
  }
  const dx = (targetSize - drawW) * 0.5;
  const dy = (targetSize - drawH) * 0.5;
  ctx.drawImage(image, dx, dy, drawW, drawH);
  const data = ctx.getImageData(0, 0, targetSize, targetSize).data;
  const lumas = new Float32Array(targetSize * targetSize);
  const alphas = new Float32Array(targetSize * targetSize);
  const sats = new Float32Array(targetSize * targetSize);
  const rgbs = new Float32Array(targetSize * targetSize * 3);
  for (let i = 0; i < lumas.length; i += 1) {
    const r = data[i * 4] / 255;
    const g = data[i * 4 + 1] / 255;
    const b = data[i * 4 + 2] / 255;
    const a = data[i * 4 + 3] / 255;
    lumas[i] = r * 0.2126 + g * 0.7152 + b * 0.0722;
    alphas[i] = a;
    sats[i] = Math.max(r, g, b) - Math.min(r, g, b);
    rgbs[i * 3] = r;
    rgbs[i * 3 + 1] = g;
    rgbs[i * 3 + 2] = b;
  }
  const borderIndices = [];
  for (let x = 0; x < targetSize; x += 1) {
    borderIndices.push(x, (targetSize - 1) * targetSize + x);
  }
  for (let y = 1; y < targetSize - 1; y += 1) {
    borderIndices.push(y * targetSize, y * targetSize + (targetSize - 1));
  }
  const borderStats = { r: [], g: [], b: [], l: [], s: [] };
  for (const idx of borderIndices) {
    borderStats.r.push(rgbs[idx * 3]);
    borderStats.g.push(rgbs[idx * 3 + 1]);
    borderStats.b.push(rgbs[idx * 3 + 2]);
    borderStats.l.push(lumas[idx]);
    borderStats.s.push(sats[idx]);
  }
  const median = (values) => {
    const ordered = [...values].sort((a, b) => a - b);
    return ordered[Math.max(0, Math.floor(ordered.length * 0.5) - 1)] ?? 0;
  };
  const quantile = (values, q) => {
    const ordered = [...values].sort((a, b) => a - b);
    return ordered[Math.max(0, Math.floor(ordered.length * q) - 1)] ?? 0;
  };
  const bgColor = [median(borderStats.r), median(borderStats.g), median(borderStats.b)];
  const bgLuma = median(borderStats.l);
  const borderColorDelta = borderIndices.map((idx) => {
    const dr = rgbs[idx * 3] - bgColor[0];
    const dg = rgbs[idx * 3 + 1] - bgColor[1];
    const db = rgbs[idx * 3 + 2] - bgColor[2];
    return Math.hypot(dr, dg, db);
  });
  const borderLumaDelta = borderIndices.map((idx) => Math.abs(lumas[idx] - bgLuma));
  const colorThreshold = Math.max(0.06, quantile(borderColorDelta, 0.92) + 0.035);
  const lumaThreshold = Math.max(0.055, quantile(borderLumaDelta, 0.92) + 0.035);
  const satThreshold = Math.max(0.08, quantile(borderStats.s, 0.92) + 0.05);
  const sorted = Array.from(lumas).sort((a, b) => a - b);
  const darkThreshold = sorted[Math.max(0, Math.floor(sorted.length * 0.38) - 1)] ?? 0.35;
  const lightThreshold = sorted[Math.max(0, Math.floor(sorted.length * 0.72) - 1)] ?? 0.72;
  const foregroundMask = new Uint8Array(targetSize * targetSize);
  const darkMask = new Uint8Array(targetSize * targetSize);
  const lightMask = new Uint8Array(targetSize * targetSize);
  for (let y = 0; y < targetSize; y += 1) {
    for (let x = 0; x < targetSize; x += 1) {
      const idx = y * targetSize + x;
      if (alphas[idx] <= 0.05) continue;
      const dr = rgbs[idx * 3] - bgColor[0];
      const dg = rgbs[idx * 3 + 1] - bgColor[1];
      const db = rgbs[idx * 3 + 2] - bgColor[2];
      const colorDelta = Math.hypot(dr, dg, db);
      const lumaDelta = Math.abs(lumas[idx] - bgLuma);
      if (
        ((colorDelta >= colorThreshold) && ((lumaDelta >= lumaThreshold * 0.65) || (sats[idx] >= satThreshold)))
        || (lumaDelta >= lumaThreshold * 1.35)
        || (sats[idx] >= satThreshold * 1.2)
      ) {
        foregroundMask[idx] = 1;
      }
      if (lumas[idx] <= darkThreshold) darkMask[idx] = 1;
      if (lumas[idx] >= lightThreshold) lightMask[idx] = 1;
    }
  }
  function removeBorderConnected(mask) {
    const out = new Uint8Array(mask);
    const visited = new Uint8Array(mask.length);
    const stack = [];
    for (let x = 0; x < targetSize; x += 1) {
      if (out[x]) stack.push([0, x]);
      const bottomIdx = (targetSize - 1) * targetSize + x;
      if (out[bottomIdx]) stack.push([targetSize - 1, x]);
    }
    for (let y = 0; y < targetSize; y += 1) {
      const leftIdx = y * targetSize;
      const rightIdx = y * targetSize + (targetSize - 1);
      if (out[leftIdx]) stack.push([y, 0]);
      if (out[rightIdx]) stack.push([y, targetSize - 1]);
    }
    while (stack.length) {
      const [y, x] = stack.pop();
      const idx = y * targetSize + x;
      if (y < 0 || y >= targetSize || x < 0 || x >= targetSize || visited[idx] || !out[idx]) continue;
      visited[idx] = 1;
      out[idx] = 0;
      stack.push([y - 1, x], [y + 1, x], [y, x - 1], [y, x + 1]);
    }
    return out;
  }
  function largestComponent(mask) {
    const visited = new Uint8Array(mask.length);
    let best = [];
    for (let y = 0; y < targetSize; y += 1) {
      for (let x = 0; x < targetSize; x += 1) {
        const idx = y * targetSize + x;
        if (!mask[idx] || visited[idx]) continue;
        const stack = [[y, x]];
        visited[idx] = 1;
        const points = [];
        while (stack.length) {
          const [cy, cx] = stack.pop();
          points.push([cy, cx]);
          for (const [ny, nx] of [[cy - 1, cx], [cy + 1, cx], [cy, cx - 1], [cy, cx + 1]]) {
            if (ny < 0 || ny >= targetSize || nx < 0 || nx >= targetSize) continue;
            const nidx = ny * targetSize + nx;
            if (!mask[nidx] || visited[nidx]) continue;
            visited[nidx] = 1;
            stack.push([ny, nx]);
          }
        }
        if (points.length > best.length) best = points;
      }
    }
    const out = new Uint8Array(mask.length);
    for (const [y, x] of best) out[y * targetSize + x] = 1;
    return out;
  }
  const foregroundCore = largestComponent(removeBorderConnected(foregroundMask));
  const darkCore = largestComponent(removeBorderConnected(darkMask));
  const lightCore = largestComponent(removeBorderConnected(lightMask));
  const areaDark = darkCore.reduce((s, v) => s + v, 0) / darkCore.length;
  const areaLight = lightCore.reduce((s, v) => s + v, 0) / lightCore.length;
  const scoreMask = (mask, preferLight = false) => {
    const area = mask.reduce((s, v) => s + v, 0) / mask.length;
    if (area < 0.002 || area > 0.72) return -1e9;
    let score = 1.0 - Math.abs(area - 0.12) * 1.6;
    if (preferLight && areaLight > 0.002 && (areaDark <= 0.002 || areaLight < areaDark * 1.4)) {
      score += 0.12;
    }
    return score;
  };
  const candidates = [
    { mask: foregroundCore, preferLight: false },
    { mask: darkCore, preferLight: false },
    { mask: lightCore, preferLight: true },
  ];
  return candidates.reduce((best, candidate) => (
    scoreMask(candidate.mask, candidate.preferLight) > scoreMask(best.mask, best.preferLight) ? candidate : best
  )).mask;
}

function maskIoU(a, b) {
  let inter = 0;
  let union = 0;
  for (let i = 0; i < a.length; i += 1) {
    const av = a[i] > 0;
    const bv = b[i] > 0;
    if (av && bv) inter += 1;
    if (av || bv) union += 1;
  }
  return union > 0 ? inter / union : -1;
}

function upperMaskIoU(a, b, width, height) {
  const cutoff = Math.max(1, Math.floor(height * 0.62));
  let inter = 0;
  let union = 0;
  for (let y = 0; y < cutoff; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const idx = y * width + x;
      const av = a[idx] > 0;
      const bv = b[idx] > 0;
      if (av && bv) inter += 1;
      if (av || bv) union += 1;
    }
  }
  return union > 0 ? inter / union : -1;
}

function lowerMaskIoU(a, b, width, height) {
  const cutoff = Math.max(1, Math.floor(height * 0.5));
  let inter = 0;
  let union = 0;
  for (let y = cutoff; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const idx = y * width + x;
      const av = a[idx] > 0;
      const bv = b[idx] > 0;
      if (av && bv) inter += 1;
      if (av || bv) union += 1;
    }
  }
  return union > 0 ? inter / union : -1;
}

function maskBoundingBox(mask, width, height) {
  let minX = width;
  let maxX = -1;
  let minY = height;
  let maxY = -1;
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      if (!mask[y * width + x]) continue;
      if (x < minX) minX = x;
      if (x > maxX) maxX = x;
      if (y < minY) minY = y;
      if (y > maxY) maxY = y;
    }
  }
  if (maxX < minX || maxY < minY) return { cx: 0.5, cy: 0.5, w: 0, h: 0 };
  return {
    cx: ((minX + maxX) * 0.5) / Math.max(1, width - 1),
    cy: ((minY + maxY) * 0.5) / Math.max(1, height - 1),
    w: (maxX - minX + 1) / Math.max(1, width),
    h: (maxY - minY + 1) / Math.max(1, height),
  };
}

function normalizeAnchorPoints(points) {
  const entries = Object.entries(points || {});
  if (!entries.length) return {};
  const xs = entries.map(([, point]) => point[0]);
  const ys = entries.map(([, point]) => point[1]);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const spanX = Math.max(1e-6, maxX - minX);
  const spanY = Math.max(1e-6, maxY - minY);
  const out = {};
  for (const [key, point] of entries) {
    out[key] = [(point[0] - minX) / spanX, (point[1] - minY) / spanY];
  }
  return out;
}

function projectPosePointsForAnchorScore(points, width, height) {
  const yaw = -Number(FIT_VIEW.yaw || 0);
  const pitch = -Number(FIT_VIEW.pitch || 0);
  const zoom = Number(FIT_VIEW.zoom || 1);
  const rot = matMul(rotX(pitch), rotY(yaw));
  const projected = {};
  const all = [];
  for (const [key, pos] of Object.entries(points)) {
    const v = matVec(rot, pos);
    projected[key] = [v[0], v[1]];
    all.push(v);
  }
  const xs = all.map((v) => v[0]);
  const ys = all.map((v) => v[1]);
  const spanX = Math.max(0.001, Math.max(...xs) - Math.min(...xs));
  const spanY = Math.max(0.001, Math.max(...ys) - Math.min(...ys));
  const scale = Math.min((width * 0.56) / spanX, (height * 0.72) / spanY) * zoom;
  const centerX = width * 0.5;
  const centerY = height * 0.63;
  const screen = {};
  for (const [key, [x, y]] of Object.entries(projected)) {
    screen[key] = [centerX + x * scale, centerY - (y - 1.0) * scale];
  }
  return screen;
}

function anchorAlignmentScore(poseData, anchors) {
  const activeAnchors = {};
  const enabledGroups = poseData?.image_fit?.enabled_groups || {};
  const groupLookup = {};
  for (const [group, keys] of Object.entries(IMAGE_FIT_ANCHOR_GROUPS)) {
    for (const key of keys) groupLookup[key] = group;
  }
  for (const [key] of IMAGE_FIT_ANCHOR_OPTIONS) {
    const entry = anchors?.[key];
    if (!entry) continue;
    if (enabledGroups[groupLookup[key]] === false) continue;
    activeAnchors[key] = [clamp(entry.x, 0, 1, 0.5), clamp(entry.y, 0, 1, 0.5)];
  }
  const anchorKeys = Object.keys(activeAnchors);
  if (!anchorKeys.length) return 0;
  const screen = projectPosePointsForAnchorScore(computePosePoints(poseData), 128, 128);
  const modelPoints = {};
  for (const key of anchorKeys) {
    if (screen[key]) modelPoints[key] = screen[key];
  }
  if (!Object.keys(modelPoints).length) return 0;
  const normModel = normalizeAnchorPoints(modelPoints);
  const normReference = normalizeAnchorPoints(activeAnchors);
  const distances = [];
  for (const key of Object.keys(normModel)) {
    if (!normReference[key]) continue;
    const dx = normModel[key][0] - normReference[key][0];
    const dy = normModel[key][1] - normReference[key][1];
    distances.push(Math.hypot(dx, dy));
  }
  if (!distances.length) return 0;
  const meanDistance = distances.reduce((sum, value) => sum + value, 0) / distances.length;
  return Math.max(-1, 1 - meanDistance * 1.55);
}

function bboxAlignmentScore(a, b, width, height) {
  const boxA = maskBoundingBox(a, width, height);
  const boxB = maskBoundingBox(b, width, height);
  if (boxA.w <= 1e-6 || boxA.h <= 1e-6 || boxB.w <= 1e-6 || boxB.h <= 1e-6) return -1;
  const centerDx = Math.abs(boxA.cx - boxB.cx);
  const centerDy = Math.abs(boxA.cy - boxB.cy);
  const spanDw = Math.abs(boxA.w - boxB.w);
  const spanDh = Math.abs(boxA.h - boxB.h);
  const penalty = (centerDx * 1.05) + (centerDy * 1.2) + (spanDw * 0.8) + (spanDh * 0.95);
  return Math.max(-1, 1 - penalty * 1.6);
}

function maskFrameHint(mask, width, height) {
  const box = maskBoundingBox(mask, width, height);
  return {
    cx: Number(box.cx.toFixed(4)),
    cy: Number(box.cy.toFixed(4)),
    bw: Number(box.w.toFixed(4)),
    bh: Number(box.h.toFixed(4)),
  };
}

function airborneScore(mask, width, height) {
  let minX = width;
  let maxX = -1;
  let minY = height;
  let maxY = -1;
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      if (!mask[y * width + x]) continue;
      if (x < minX) minX = x;
      if (x > maxX) maxX = x;
      if (y < minY) minY = y;
      if (y > maxY) maxY = y;
    }
  }
  if (maxX < minX || maxY < minY) return 0;
  const bodyH = Math.max(1, maxY - minY + 1);
  const bodyW = Math.max(1, maxX - minX + 1);
  const bottomStart = Math.max(minY, maxY - Math.max(2, Math.floor(bodyH * 0.08)));
  let maxBottomWidth = 0;
  for (let y = bottomStart; y <= maxY; y += 1) {
    let rowWidth = 0;
    for (let x = minX; x <= maxX; x += 1) {
      if (mask[y * width + x]) rowWidth += 1;
    }
    if (rowWidth > maxBottomWidth) maxBottomWidth = rowWidth;
  }
  const bottomRatio = maxBottomWidth / Math.max(1, bodyW);
  const airborne = (0.28 - bottomRatio) * 3.4;
  return clamp(airborne, 0, 1, 0);
}

function extractPoseReferenceAnchors(mask, width, height) {
  let minX = width;
  let maxX = -1;
  let minY = height;
  let maxY = -1;
  const rowBounds = new Map();
  for (let y = 0; y < height; y += 1) {
    let rowMin = width;
    let rowMax = -1;
    for (let x = 0; x < width; x += 1) {
      if (!mask[y * width + x]) continue;
      minX = Math.min(minX, x);
      maxX = Math.max(maxX, x);
      minY = Math.min(minY, y);
      maxY = Math.max(maxY, y);
      rowMin = Math.min(rowMin, x);
      rowMax = Math.max(rowMax, x);
    }
    if (rowMax >= rowMin) rowBounds.set(y, [rowMin, rowMax]);
  }
  if (maxX < minX || maxY < minY) return {};

  const bodyH = Math.max(1, maxY - minY + 1);
  const centerline = [];
  for (let y = minY + Math.floor(bodyH * 0.18); y <= minY + Math.floor(bodyH * 0.82); y += 1) {
    const bounds = rowBounds.get(y);
    if (!bounds) continue;
    centerline.push((bounds[0] + bounds[1]) * 0.5);
  }
  const centerX = centerline.length ? centerline.reduce((sum, x) => sum + x, 0) / centerline.length : (minX + maxX) * 0.5;

  const bandPoints = (startFrac, endFrac, side = "") => {
    const points = [];
    const start = minY + Math.floor(bodyH * startFrac);
    const end = minY + Math.floor(bodyH * endFrac);
    for (let y = Math.max(minY, start); y <= Math.min(maxY, end); y += 1) {
      for (let x = 0; x < width; x += 1) {
        if (!mask[y * width + x]) continue;
        if (side === "l" && x > centerX) continue;
        if (side === "r" && x < centerX) continue;
        points.push([x, y]);
      }
    }
    return points;
  };
  const centroid = (points) => {
    if (!points.length) return null;
    return [
      points.reduce((sum, point) => sum + point[0], 0) / points.length,
      points.reduce((sum, point) => sum + point[1], 0) / points.length,
    ];
  };
  const norm = (point) => point ? ({
    x: clamp(point[0] / Math.max(1, width - 1), 0, 1, 0.5),
    y: clamp(point[1] / Math.max(1, height - 1), 0, 1, 0.5),
  }) : null;

  const anchors = {};
  const topRows = [];
  for (let y = minY; y <= Math.min(maxY, minY + Math.max(4, Math.floor(bodyH * 0.06))); y += 1) {
    if (rowBounds.has(y)) topRows.push(y);
  }
  if (topRows.length) {
    const topXs = [];
    for (const y of topRows) {
      const [left, right] = rowBounds.get(y);
      for (let x = left; x <= right; x += 1) topXs.push(x);
    }
    if (topXs.length) {
      anchors.head = norm([topXs.reduce((sum, x) => sum + x, 0) / topXs.length, Math.min(...topRows)]);
    }
  }

  for (const [key, startFrac, endFrac, side] of [
    ["chest", 0.2, 0.38, ""],
    ["pelvis", 0.5, 0.66, ""],
    ["knee_l", 0.62, 0.8, "l"],
    ["knee_r", 0.62, 0.8, "r"],
    ["ankle_l", 0.8, 0.96, "l"],
    ["ankle_r", 0.8, 0.96, "r"],
  ]) {
    const point = norm(centroid(bandPoints(startFrac, endFrac, side)));
    if (point) anchors[key] = point;
  }

  const shoulderBand = bandPoints(0.18, 0.34);
  if (shoulderBand.length) {
    const leftPoints = shoulderBand.filter((point) => point[0] <= centerX);
    const rightPoints = shoulderBand.filter((point) => point[0] >= centerX);
    if (leftPoints.length) {
      const leftmost = leftPoints.reduce((best, point) => (point[0] < best[0] ? point : best), leftPoints[0]);
      anchors.shoulder_l = norm(leftmost);
    }
    if (rightPoints.length) {
      const rightmost = rightPoints.reduce((best, point) => (point[0] > best[0] ? point : best), rightPoints[0]);
      anchors.shoulder_r = norm(rightmost);
    }
  }

  const handBand = bandPoints(0.08, 0.58);
  if (handBand.length) {
    const leftPoints = handBand.filter((point) => point[0] <= centerX);
    const rightPoints = handBand.filter((point) => point[0] >= centerX);
    if (leftPoints.length) {
      const leftmost = leftPoints.reduce((best, point) => (point[0] < best[0] ? point : best), leftPoints[0]);
      anchors.hand_l = norm(leftmost);
    }
    if (rightPoints.length) {
      const rightmost = rightPoints.reduce((best, point) => (point[0] > best[0] ? point : best), rightPoints[0]);
      anchors.hand_r = norm(rightmost);
    }
  }

  const footBand = bandPoints(0.84, 1.0);
  if (footBand.length) {
    const leftPoints = footBand.filter((point) => point[0] <= centerX);
    const rightPoints = footBand.filter((point) => point[0] >= centerX);
    if (leftPoints.length) {
      const leftToe = leftPoints.reduce((best, point) => ((point[1] > best[1] || (point[1] === best[1] && point[0] < best[0])) ? point : best), leftPoints[0]);
      anchors.toe_l = norm(leftToe);
    }
    if (rightPoints.length) {
      const rightToe = rightPoints.reduce((best, point) => ((point[1] > best[1] || (point[1] === best[1] && point[0] > best[0])) ? point : best), rightPoints[0]);
      anchors.toe_r = norm(rightToe);
    }
  }

  return Object.fromEntries(
    Object.entries(anchors).filter(([key, value]) => IMAGE_FIT_ANCHOR_SET.has(key) && value)
  );
}

function poseRegularizationScore(poseData) {
  let penalty = 0;
  for (const [key, spec] of Object.entries(CONTROL_SPECS)) {
    const value = Number(poseData.controls?.[key] ?? spec.default);
    const span = Math.max(1e-6, spec.max - spec.min);
    const deviation = Math.abs(value - spec.default) / span;
    penalty += deviation * (FIT_CONTROL_WEIGHTS[key] || 0.6);
  }
  return penalty;
}

function supportPenaltyScore(poseData, targetMask = null, width = 0, height = 0) {
  const points = computePosePoints(poseData);
  const groundKeys = ["knee_l", "ankle_l", "toe_l", "knee_r", "ankle_r", "toe_r"];
  const groundY = Math.min(...groundKeys.map((key) => points[key]?.[1] ?? 0));

  const totalWeight = Object.values(POSE_MASS_WEIGHTS).reduce((sum, weight) => sum + weight, 0) || 1;
  const comX = Object.entries(POSE_MASS_WEIGHTS).reduce((sum, [key, weight]) => sum + (points[key]?.[0] ?? 0) * weight, 0) / totalWeight;
  const comZ = Object.entries(POSE_MASS_WEIGHTS).reduce((sum, [key, weight]) => sum + (points[key]?.[2] ?? 0) * weight, 0) / totalWeight;

  let supportContacts = groundKeys
    .map((key) => points[key])
    .filter((point) => point && point[1] <= groundY + 0.16);
  if (supportContacts.length < 2) {
    supportContacts = ["ankle_l", "toe_l", "ankle_r", "toe_r"].map((key) => points[key]).filter(Boolean);
  }

  const xs = supportContacts.map((point) => point[0]);
  const zs = supportContacts.map((point) => point[2]);
  const xMin = Math.min(...xs) - 0.08;
  const xMax = Math.max(...xs) + 0.08;
  const zMin = Math.min(...zs) - 0.06;
  const zMax = Math.max(...zs) + 0.1;

  let penalty = 0;
  if (comX < xMin) penalty += (xMin - comX) * 2.6;
  else if (comX > xMax) penalty += (comX - xMax) * 2.6;
  if (comZ < zMin) penalty += (zMin - comZ) * 1.8;
  else if (comZ > zMax) penalty += (comZ - zMax) * 1.8;

  for (const side of ["l", "r"]) {
    const bend = Number(poseData.controls?.[`knee_bend_${side}`] ?? 0);
    const contactClearance = Math.min(
      points[`knee_${side}`]?.[1] ?? groundY,
      points[`ankle_${side}`]?.[1] ?? groundY,
      points[`toe_${side}`]?.[1] ?? groundY
    ) - groundY;
    if (bend >= 90 && contactClearance > 0.14) penalty += (contactClearance - 0.14) * 3.0;
    else if (bend >= 60 && contactClearance > 0.2) penalty += (contactClearance - 0.2) * 1.8;
  }
  const airborne = targetMask ? airborneScore(targetMask, width, height) : 0;
  return penalty * (1 - airborne * 0.82);
}

function fitObjectiveScore(maskA, maskB, poseData, width, height, anchors = null, mode = "fit_from_image") {
  const full = maskIoU(maskA, maskB);
  const upper = upperMaskIoU(maskA, maskB, width, height);
  const lower = lowerMaskIoU(maskA, maskB, width, height);
  const bbox = bboxAlignmentScore(maskA, maskB, width, height);
  const anchor = anchorAlignmentScore(poseData, anchors || poseData?.image_fit?.anchors);
  const structured = String(mode || "fit_from_image") === "fit_from_image_structured";
  return (
    (upper * (structured ? 0.32 : 0.42)) +
    (lower * (structured ? 0.22 : 0.24)) +
    (full * (structured ? 0.14 : 0.18)) +
    (bbox * (structured ? 0.14 : 0.16)) +
    (anchor * (structured ? 0.44 : 0.22)) -
    (poseRegularizationScore(poseData) * (structured ? 0.06 : 0.085)) -
    (supportPenaltyScore(poseData, maskB, width, height) * (structured ? 0.08 : 0.12))
  );
}

function mirrorAnchorsHorizontal(anchors) {
  const out = {};
  for (const [key, entry] of Object.entries(anchors || {})) {
    if (!entry) continue;
    out[key] = {
      x: 1 - clamp(entry.x, 0, 1, 0.5),
      y: clamp(entry.y, 0, 1, 0.5),
    };
  }
  return out;
}

function filteredAnchorsForPoseData(poseData) {
  const anchors = poseData?.image_fit?.anchors || {};
  const enabledGroups = poseData?.image_fit?.enabled_groups || {};
  const groupLookup = {};
  for (const [group, keys] of Object.entries(IMAGE_FIT_ANCHOR_GROUPS)) {
    for (const key of keys) groupLookup[key] = group;
  }
  const out = {};
  for (const [key, entry] of Object.entries(anchors)) {
    if (enabledGroups[groupLookup[key]] === false) continue;
    out[key] = entry;
  }
  return out;
}

function fitCoarseCandidates(key, current) {
  const spec = CONTROL_SPECS[key];
  let raw = [spec.default];
  if (key === "root_yaw") raw = [-120, -75, -40, 0, 40, 75, 120];
  else if (key === "root_pitch") raw = [-18, -8, 0, 10, 20, 30];
  else if (key === "root_roll") raw = [-18, -8, 0, 8, 18];
  else if (key === "spine_bend") raw = [-18, -8, 0, 12, 24, 34];
  else if (key === "spine_twist") raw = [-40, -20, 0, 20, 40];
  else if (key === "head_yaw") raw = [-35, -18, 0, 18, 35];
  else if (key === "head_pitch") raw = [-20, -8, 0, 10, 20];
  else if (key === "head_roll") raw = [-18, -8, 0, 8, 18];
  else if (key.startsWith("arm_raise_")) raw = [-12, 18, 45, 72, 98, 124];
  else if (key.startsWith("arm_forward_")) raw = [-85, -48, -20, 0, 20, 48, 85];
  else if (key.startsWith("arm_twist_") || key.startsWith("wrist_twist_")) raw = [-72, -36, 0, 36, 72];
  else if (key.startsWith("elbow_bend_")) raw = [0, 20, 48, 78, 108, 135];
  else if (key.startsWith("hip_lift_")) raw = [-24, -8, 8, 22, 40, 60];
  else if (key.startsWith("hip_side_")) raw = [-24, -12, 0, 12, 24];
  else if (key.startsWith("knee_bend_")) raw = [0, 20, 48, 82, 110, 138];
  else if (key.startsWith("foot_point_")) raw = [-18, 0, 12, 24, 42];
  const set = new Set([
    clamp(current, spec.min, spec.max, spec.default),
    spec.default,
    ...raw.map((value) => clamp(value, spec.min, spec.max, spec.default)),
  ]);
  return [...set].sort((a, b) => a - b);
}

function runCoarseFitPass(targetMask, startingPose, width, height, anchors = null, mode = "fit_from_image") {
  let bestPose = JSON.parse(JSON.stringify(startingPose));
  let bestScore = fitObjectiveScore(renderPoseMaskForFit(bestPose, width, height), targetMask, bestPose, width, height, anchors, mode);
  for (let round = 0; round < 2; round += 1) {
    let improved = false;
    for (const key of FIT_CONTROL_ORDER) {
      const spec = CONTROL_SPECS[key];
      const current = Number(bestPose.controls?.[key] ?? spec.default);
      let localBestScore = bestScore;
      let localBestValue = current;
      for (const candidate of fitCoarseCandidates(key, current)) {
        if (Math.abs(candidate - current) < 1e-6) continue;
        const probe = JSON.parse(JSON.stringify(bestPose));
        probe.controls[key] = candidate;
        const probeScore = fitObjectiveScore(renderPoseMaskForFit(probe, width, height), targetMask, probe, width, height, anchors, mode);
        if (probeScore > localBestScore) {
          localBestScore = probeScore;
          localBestValue = candidate;
        }
      }
      if (Math.abs(localBestValue - current) > 1e-6) {
        bestPose.controls[key] = localBestValue;
        bestScore = localBestScore;
        improved = true;
      }
    }
    if (!improved) break;
  }
  return { score: bestScore, pose: bestPose };
}

function applySeedControls(targetPose, controls) {
  for (const [key, value] of Object.entries(controls || {})) {
    const spec = CONTROL_SPECS[key];
    if (!spec) continue;
    targetPose.controls[key] = clamp(value, spec.min, spec.max, spec.default);
  }
}

function createNumberControl({ label, value, min, max, step, onChange }) {
  const row = document.createElement("div");
  row.className = "mkr-control";
  const labelNode = document.createElement("label");
  labelNode.className = "mkr-label";
  labelNode.textContent = label;
  row.appendChild(labelNode);
  const input = document.createElement("input");
  input.type = "number";
  input.className = "mkr-number";
  input.min = String(min);
  input.max = String(max);
  input.step = String(step);
  input.value = String(value);
  input.addEventListener("change", () => onChange?.(Number(input.value)));
  row.appendChild(input);
  row.appendChild(document.createElement("span"));
  return {
    element: row,
    input,
    setValue(next) {
      input.value = String(next);
    },
  };
}

function renderFallbackPreview(viewport, data, renderHost = null) {
  const { width, height, screen } = projectPoseToViewport(viewport, data);
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  canvas.style.width = "100%";
  canvas.style.height = "100%";
  const ctx = canvas.getContext("2d");

  const bgGradient = ctx.createLinearGradient(0, 0, 0, height);
  bgGradient.addColorStop(0, POSE_COLORS.bgTop);
  bgGradient.addColorStop(1, POSE_COLORS.bgBottom);
  ctx.fillStyle = bgGradient;
  ctx.fillRect(0, 0, width, height);

  ctx.fillStyle = POSE_COLORS.bgPanel;
  ctx.fillRect(24, 24, width - 48, height - 48);

  const exportFrame = computeExportFrameRect(width, height, data.capture_w, data.capture_h);
  ctx.strokeStyle = "rgba(196, 145, 51, 0.55)";
  ctx.lineWidth = 2;
  ctx.strokeRect(exportFrame.x, exportFrame.y, exportFrame.w, exportFrame.h);

  const viewMode = data.display?.view_mode || "bones_only";
  if (viewMode !== "bones_only") {
    const variant = FALLBACK_SILHOUETTE_RADII[data.display?.silhouette_model || "female"] || FALLBACK_SILHOUETTE_RADII.female;
    const meshColor = viewMode === "depth_mesh" ? "rgba(202, 214, 228, 0.96)" : "rgba(188, 198, 208, 0.46)";
    const meshShadow = viewMode === "depth_mesh" ? "rgba(8, 12, 18, 0.98)" : "rgba(6, 10, 16, 0.56)";
    const segmentRadius = (name) => {
      if (name.includes("shoulder")) return variant.shoulder;
      if (name.includes("elbow")) return variant.upper;
      if (name.includes("wrist")) return variant.lower;
      if (name.includes("hand")) return variant.hand;
      if (name.includes("hip")) return variant.hip;
      if (name.includes("knee")) return variant.thigh;
      if (name.includes("ankle")) return variant.calf;
      if (name.includes("toe")) return variant.foot;
      return variant.torso;
    };
    const drawMeshStroke = (a, b, radius) => {
      ctx.strokeStyle = meshShadow;
      ctx.lineWidth = radius + (viewMode === "depth_mesh" ? 7 : 5);
      ctx.beginPath();
      ctx.moveTo(a[0], a[1]);
      ctx.lineTo(b[0], b[1]);
      ctx.stroke();
      ctx.strokeStyle = meshColor;
      ctx.lineWidth = radius + (viewMode === "depth_mesh" ? 2 : 0);
      ctx.beginPath();
      ctx.moveTo(a[0], a[1]);
      ctx.lineTo(b[0], b[1]);
      ctx.stroke();
    };
    drawMeshStroke(screen.pelvis, screen.spine, variant.torso);
    drawMeshStroke(screen.spine, screen.chest, variant.torso);
    drawMeshStroke(screen.chest, screen.neck, variant.torso - 2);
    drawMeshStroke(screen.chest, screen.shoulder_l, variant.shoulder);
    drawMeshStroke(screen.shoulder_l, screen.elbow_l, variant.upper);
    drawMeshStroke(screen.elbow_l, screen.wrist_l, variant.lower);
    drawMeshStroke(screen.wrist_l, screen.hand_l, variant.hand);
    drawMeshStroke(screen.chest, screen.shoulder_r, variant.shoulder);
    drawMeshStroke(screen.shoulder_r, screen.elbow_r, variant.upper);
    drawMeshStroke(screen.elbow_r, screen.wrist_r, variant.lower);
    drawMeshStroke(screen.wrist_r, screen.hand_r, variant.hand);
    drawMeshStroke(screen.pelvis, screen.hip_l, variant.hip);
    drawMeshStroke(screen.hip_l, screen.knee_l, variant.thigh);
    drawMeshStroke(screen.knee_l, screen.ankle_l, variant.calf);
    drawMeshStroke(screen.ankle_l, screen.toe_l, variant.foot);
    drawMeshStroke(screen.pelvis, screen.hip_r, variant.hip);
    drawMeshStroke(screen.hip_r, screen.knee_r, variant.thigh);
    drawMeshStroke(screen.knee_r, screen.ankle_r, variant.calf);
    drawMeshStroke(screen.ankle_r, screen.toe_r, variant.foot);
    const fillBlob = (point, rx, ry) => {
      ctx.fillStyle = meshShadow;
      ctx.beginPath();
      ctx.ellipse(point[0], point[1], rx + (viewMode === "depth_mesh" ? 5 : 3), ry + (viewMode === "depth_mesh" ? 5 : 3), 0, 0, Math.PI * 2);
      ctx.fill();
      ctx.fillStyle = meshColor;
      ctx.beginPath();
      ctx.ellipse(point[0], point[1], rx, ry, 0, 0, Math.PI * 2);
      ctx.fill();
    };
    fillBlob(screen.chest, variant.torso * 0.95, variant.torso * 1.2);
    fillBlob(screen.pelvis, variant.hip * 1.1, variant.hip * 0.9);
    fillBlob(screen.head, variant.torso * 0.6, variant.torso * 0.78);
    if (viewMode === "depth_mesh") {
      const depthGradient = ctx.createLinearGradient(exportFrame.x, exportFrame.y, exportFrame.x, exportFrame.y + exportFrame.h);
      depthGradient.addColorStop(0, "rgba(244, 248, 252, 0.18)");
      depthGradient.addColorStop(1, "rgba(46, 60, 72, 0.22)");
      ctx.fillStyle = depthGradient;
      ctx.fillRect(exportFrame.x, exportFrame.y, exportFrame.w, exportFrame.h);
    }
  }

  const showBones = viewMode !== "depth_mesh";
  if (showBones) {
    for (const [start, end] of POSE_BONES) {
      const p0 = screen[start];
      const p1 = screen[end];
      ctx.strokeStyle = start.endsWith("_l") || end.endsWith("_l") ? POSE_COLORS.left : start.endsWith("_r") || end.endsWith("_r") ? POSE_COLORS.right : POSE_COLORS.center;
      ctx.lineWidth = 7;
      ctx.beginPath();
      ctx.moveTo(p0[0], p0[1]);
      ctx.lineTo(p1[0], p1[1]);
      ctx.stroke();
    }

    for (const [name, point] of Object.entries(screen)) {
      const outerRadius = jointDisplayRadius(name);
      const innerRadius = Math.max(2.2, outerRadius - 1.8);
      ctx.fillStyle = POSE_COLORS.shadow;
      ctx.beginPath();
      ctx.arc(point[0], point[1], outerRadius, 0, Math.PI * 2);
      ctx.fill();
      ctx.fillStyle = name.endsWith("_l") ? POSE_COLORS.left : name.endsWith("_r") ? POSE_COLORS.right : POSE_COLORS.center;
      ctx.beginPath();
      ctx.arc(point[0], point[1], innerRadius, 0, Math.PI * 2);
      ctx.fill();
    }
  }

  if (renderHost) {
    renderHost.innerHTML = "";
    renderHost.appendChild(canvas);
  }
}

function makePanel(node, options = {}) {
  ensureMkrUIStyles();
  ensurePoseStudioStyles();
  const externalStudio = options?.externalStudio === true;
  const { panel } = createPanelShell({
    kicker: "MKR Shift 3D",
    title: "Pose Studio",
    subtitle: "Visual pose blocking with reusable pose JSON.",
  });
  panel.classList.add("mkr-pose-panel");
  if (externalStudio) {
    panel.classList.add("mkr-pose-panel--studio");
    panel.style.height = "100%";
  } else {
    panel.style.height = `${DOM_WIDGET_HEIGHT}px`;
  }

  const backing = ensurePoseBackingWidgets(node);
  const { widget, data } = ensureSettings(node);

  const poseNameWidget = backing.pose_name;
  const posePresetWidget = backing.pose_preset;
  const mirrorModeWidget = backing.mirror_mode;
  const captureWWidget = backing.capture_w;
  const captureHWidget = backing.capture_h;
  const characterStateWidget = backing.character_state_json;
  const fitModeWidget = backing.pose_from_image_mode;
  const fitStrengthWidget = backing.pose_image_strength;
  [widget, poseNameWidget, posePresetWidget, mirrorModeWidget, captureWWidget, captureHWidget, characterStateWidget, fitModeWidget, fitStrengthWidget].forEach(hideWidget);

  data.capture_w = clamp(captureWWidget?.value, 384, 2048, 1024);
  data.capture_h = clamp(captureHWidget?.value, 384, 2048, 1024);
  data.character_state_json = String(characterStateWidget?.value || "");

  let muteCommit = false;
  let scene = null;
  let camera = null;
  let renderer = null;
  let controls = null;
  let jointMeshes = new Map();
  let boneMeshes = [];
  let rigRoot = null;
  let cameraSyncMute = false;
  let viewportMode = "fallback";
  let resizeObserver = null;
  let resizeHandler = null;
  let rafId = 0;
  let disposed = false;
  let selectedJoint = "";
  let activeTool = "orbit";
  let dragState = null;
  let overlayCanvas = null;
  let renderLayer = null;
  let overlayStatus = null;
  let toolButtons = new Map();
  let viewportNavState = null;
  let activeGizmoHandle = "";
  let silhouetteRig = null;
  let userPresets = loadUserPresets();
  let referencePoseImage = null;
  let lastImageFitScore = null;
  const fitLocks = { torso: false, head: false, arms: false, legs: false };
  data.image_fit = sanitizeImageFitSettings(data.image_fit);

  function jointLabel(name) {
    return String(name || "")
      .replace(/_/g, " ")
      .replace(/\b\w/g, (char) => char.toUpperCase());
  }

  function applyExternalPresetPayload(payload, fallbackName = "Saved Pose") {
    if (!payload || typeof payload !== "object" || Array.isArray(payload)) return;
    muteCommit = true;
    const next = ensureSettings(node).data;
    next.pose_name = String(payload.pose_name || fallbackName).trim() || fallbackName;
    next.pose_preset = PRESET_OPTIONS.includes(String(payload.pose_preset)) ? String(payload.pose_preset) : "neutral";
    next.mirror_mode = ["off", "left_to_right", "right_to_left"].includes(String(payload.mirror_mode))
      ? String(payload.mirror_mode)
      : "off";
    next.display = sanitizeDisplaySettings(payload.display);
    next.image_fit = sanitizeImageFitSettings(payload.image_fit);
    for (const [key, spec] of Object.entries(CONTROL_SPECS)) {
      next.controls[key] = clamp(payload?.controls?.[key], spec.min, spec.max, spec.default);
    }
    next.view = {
      yaw: clamp(payload?.view?.yaw, -180, 180, 28),
      pitch: clamp(payload?.view?.pitch, -85, 85, 8),
      zoom: clamp(payload?.view?.zoom, 0.4, 2.4, 1),
      pan_x: clamp(payload?.view?.pan_x, -4, 4, 0),
      pan_y: clamp(payload?.view?.pan_y, -4, 4, 0),
    };
    Object.assign(data, next);
    muteCommit = false;
    if (data.image_fit?.reference_image_data_url) {
      loadReferencePoseImageFromDataUrl(data.image_fit.reference_image_data_url, data.image_fit.reference_image_name)
        .catch((error) => console.warn("Pose Studio preset reference image load failed:", error));
    } else {
      referencePoseImage = null;
      lastImageFitScore = null;
    }
  }

  function exportPoseState() {
    return {
      schema: data.schema || "mkr_pose_studio_v1",
      schema_version: data.schema_version || SETTINGS_SCHEMA_VERSION,
      pose_name: data.pose_name,
      pose_preset: data.pose_preset,
      mirror_mode: data.mirror_mode,
      view: { ...(data.view || {}) },
      display: sanitizeDisplaySettings(data.display),
      image_fit: sanitizeImageFitSettings(data.image_fit),
      controls: { ...(data.controls || {}) },
    };
  }

  function isFitControlLocked(key) {
    if (["root_yaw", "root_pitch", "root_roll", "spine_bend", "spine_twist"].includes(key)) return fitLocks.torso;
    if (["head_yaw", "head_pitch", "head_roll"].includes(key)) return fitLocks.head;
    if (/^(arm_raise|arm_forward|arm_twist|elbow_bend|wrist_twist)_/.test(key)) return fitLocks.arms;
    if (/^(hip_lift|hip_side|knee_bend|foot_point)_/.test(key)) return fitLocks.legs;
    return false;
  }

  function updateOverlayStatus() {
    if (!overlayStatus) return;
    const jointText = selectedJoint ? jointLabel(selectedJoint) : "No joint selected";
    const navHint = "MMB orbit • Shift+MMB pan • wheel zoom";
    overlayStatus.textContent = `${activeTool} • ${jointText} • ${navHint}`;
  }

  function buildProjectionState() {
    const width = Math.max(180, viewport.clientWidth || 260);
    const height = Math.max(180, viewport.clientHeight || 260);
    const posePoints = computePosePoints(data);
    if (viewportMode === "3d" && camera && THREE) {
      return {
        width,
        height,
        posePoints,
        project(point) {
          const projected = new THREE.Vector3(point[0], point[1], point[2]).project(camera);
          return [
            (projected.x * 0.5 + 0.5) * width,
            (-projected.y * 0.5 + 0.5) * height,
          ];
        },
      };
    }

    const yaw = -Number(data.view.yaw || 0);
    const pitch = -Number(data.view.pitch || 0);
    const zoom = Number(data.view.zoom || 1);
    const rot = matMul(rotX(pitch), rotY(yaw));
    const all = Object.values(posePoints).map((pos) => matVec(rot, pos));
    const xs = all.map((v) => v[0]);
    const ys = all.map((v) => v[1]);
    const frameX = width * 0.06;
    const frameY = height * 0.04;
    const frameW = width * 0.88;
    const frameH = height * 0.92;
    const scale = Math.min(
      (frameW * 0.92) / Math.max(0.001, Math.max(...xs) - Math.min(...xs)),
      (frameH * 0.94) / Math.max(0.001, Math.max(...ys) - Math.min(...ys))
    ) * zoom;
    const centerX = width * 0.5 + (Number(data.view.pan_x) || 0) * scale;
    const centerY = frameY + frameH * 0.78 + (Number(data.view.pan_y) || 0) * scale;
    return {
      width,
      height,
      posePoints,
      project(point) {
        const rotated = matVec(rot, point);
        return [centerX + rotated[0] * scale, centerY - (rotated[1] - 1.0) * scale];
      },
    };
  }

  function distancePointToSegment(point, start, end) {
    const ax = start[0];
    const ay = start[1];
    const bx = end[0];
    const by = end[1];
    const abx = bx - ax;
    const aby = by - ay;
    const apx = point[0] - ax;
    const apy = point[1] - ay;
    const denom = abx * abx + aby * aby || 1;
    const t = Math.max(0, Math.min(1, (apx * abx + apy * aby) / denom));
    const px = ax + abx * t;
    const py = ay + aby * t;
    return Math.hypot(point[0] - px, point[1] - py);
  }

  function buildRingScreenPoints(centerWorld, basis, axis, radius, project) {
    const steps = 48;
    const points = [];
    const planeA = axis === "x" ? basis.y : axis === "y" ? basis.x : basis.x;
    const planeB = axis === "x" ? basis.z : axis === "y" ? basis.z : basis.y;
    for (let index = 0; index <= steps; index += 1) {
      const theta = (index / steps) * Math.PI * 2;
      const worldPoint = addVec(
        centerWorld,
        addVec(scaleVec(planeA, Math.cos(theta) * radius), scaleVec(planeB, Math.sin(theta) * radius))
      );
      points.push(project(worldPoint));
    }
    return points;
  }

  function getGizmoHandles() {
    if (!selectedJoint) return [];
    const projection = buildProjectionState();
    const centerWorld = projection.posePoints[selectedJoint];
    if (!centerWorld) return [];
    const basis = getJointBasis(projection.posePoints, selectedJoint);
    const center = projection.project(centerWorld);
    const axisLength = 0.24;
    if (activeTool === "move") {
      return [
        {
          id: "move_x",
          axis: "x",
          mode: "move",
          color: "#ff6b5f",
          label: "X",
          center,
          start: center,
          basis,
          worldLength: axisLength,
          end: projection.project(addVec(centerWorld, scaleVec(basis.x, axisLength))),
        },
        {
          id: "move_y",
          axis: "y",
          mode: "move",
          color: "#77d86c",
          label: "Y",
          center,
          start: center,
          basis,
          worldLength: axisLength,
          end: projection.project(addVec(centerWorld, scaleVec(basis.y, axisLength))),
        },
        {
          id: "move_z",
          axis: "z",
          mode: "move",
          color: "#58a6ff",
          label: "Z",
          center,
          start: center,
          basis,
          worldLength: axisLength,
          end: projection.project(addVec(centerWorld, scaleVec(basis.z, axisLength))),
        },
      ];
    }
    if (activeTool === "rotate") {
      return [
        {
          id: "rotate_x",
          axis: "x",
          mode: "rotate",
          color: "#ff6b5f",
          label: "X",
          center,
          basis,
          ringPoints: buildRingScreenPoints(centerWorld, basis, "x", 0.22, projection.project),
        },
        {
          id: "rotate_y",
          axis: "y",
          mode: "rotate",
          color: "#77d86c",
          label: "Y",
          center,
          basis,
          ringPoints: buildRingScreenPoints(centerWorld, basis, "y", 0.28, projection.project),
        },
        {
          id: "rotate_z",
          axis: "z",
          mode: "rotate",
          color: "#58a6ff",
          label: "Z",
          center,
          basis,
          ringPoints: buildRingScreenPoints(centerWorld, basis, "z", 0.34, projection.project),
        },
      ];
    }
    return [];
  }

  function pickGizmoHandle(x, y) {
    const handles = getGizmoHandles();
    for (const handle of handles) {
      if (handle.mode === "move") {
        const tipDistance = Math.hypot(handle.end[0] - x, handle.end[1] - y);
        const axisDistance = distancePointToSegment([x, y], handle.start, handle.end);
        if (tipDistance <= 12 || axisDistance <= 8) return handle;
      }
      if (handle.mode === "rotate") {
        let best = Infinity;
        for (let index = 1; index < handle.ringPoints.length; index += 1) {
          best = Math.min(best, distancePointToSegment([x, y], handle.ringPoints[index - 1], handle.ringPoints[index]));
        }
        if (best <= 8) return handle;
      }
    }
    return null;
  }

  function setActiveTool(nextTool) {
    activeTool = nextTool;
    if (controls) {
      controls.enabled = false;
      controls.enableRotate = true;
      controls.enablePan = true;
      controls.enableZoom = true;
    }
    for (const [key, button] of toolButtons.entries()) {
      button.dataset.active = key === nextTool ? "true" : "false";
    }
    if (nextTool === "cursor") {
      selectedJoint = "";
      activeGizmoHandle = "";
    }
    const cursor = nextTool === "cursor" ? "default" : nextTool === "rotate" ? "alias" : nextTool === "orbit" ? "grab" : "crosshair";
    if (overlayCanvas) overlayCanvas.style.cursor = cursor;
    if (viewport) viewport.style.cursor = cursor;
    updateSelectionPanel();
    updateOverlayStatus();
    refreshViewportOverlay();
  }

  function pickJointAt(x, y) {
    const projection = projectPoseToViewport(viewport, data, viewportMode === "3d" ? camera : null);
    let best = "";
    let bestDistance = 18;
    for (const [name, [sx, sy]] of Object.entries(projection.screen)) {
      const dx = sx - x;
      const dy = sy - y;
      const distance = Math.hypot(dx, dy);
      if (distance < bestDistance) {
        bestDistance = distance;
        best = name;
      }
    }
    return best;
  }

  function refreshViewportOverlay() {
    if (!overlayCanvas || disposed) return;
    const projection = projectPoseToViewport(viewport, data, viewportMode === "3d" ? camera : null);
    const width = Math.max(1, Math.round(projection.width));
    const height = Math.max(1, Math.round(projection.height));
    if (overlayCanvas.width !== width) overlayCanvas.width = width;
    if (overlayCanvas.height !== height) overlayCanvas.height = height;
    const ctx = overlayCanvas.getContext("2d");
    if (!ctx) return;
    ctx.clearRect(0, 0, width, height);

    const exportFrame = computeExportFrameRect(width, height, data.capture_w, data.capture_h);
    ctx.strokeStyle = POSE_COLORS.exportFrame;
    ctx.lineWidth = 2;
    ctx.strokeRect(exportFrame.x, exportFrame.y, exportFrame.w, exportFrame.h);

    ctx.fillStyle = POSE_COLORS.exportFrame;
    ctx.font = "700 11px sans-serif";
    ctx.textBaseline = "bottom";
    ctx.fillText(`${Math.round(Number(data.capture_w || 1024))}×${Math.round(Number(data.capture_h || 1024))}`, exportFrame.x + 8, exportFrame.y - 6);

    const showBonesOverlay = (data.display?.view_mode || "bones_only") !== "depth_mesh";
    if (showBonesOverlay) {
      for (const [start, end] of POSE_BONES) {
        const p0 = projection.screen[start];
        const p1 = projection.screen[end];
        if (!p0 || !p1) continue;
        ctx.strokeStyle = start.endsWith("_l") || end.endsWith("_l") ? POSE_COLORS.left : start.endsWith("_r") || end.endsWith("_r") ? POSE_COLORS.right : POSE_COLORS.center;
        ctx.lineWidth = 3.5;
        ctx.beginPath();
        ctx.moveTo(p0[0], p0[1]);
        ctx.lineTo(p1[0], p1[1]);
        ctx.stroke();
      }

      for (const [name, point] of Object.entries(projection.screen)) {
        const isSelected = name === selectedJoint;
        ctx.fillStyle = POSE_COLORS.shadow;
        ctx.beginPath();
        ctx.arc(point[0], point[1], isSelected ? 8 : 6.5, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = name.endsWith("_l") ? POSE_COLORS.left : name.endsWith("_r") ? POSE_COLORS.right : POSE_COLORS.center;
        ctx.beginPath();
        ctx.arc(point[0], point[1], isSelected ? 7 : 5, 0, Math.PI * 2);
        ctx.fill();
        if (isSelected) {
          ctx.strokeStyle = "#ffffff";
          ctx.lineWidth = 2;
          ctx.beginPath();
          ctx.arc(point[0], point[1], 11, 0, Math.PI * 2);
          ctx.stroke();
        }
      }
    }

    const gizmoHandles = getGizmoHandles();
    for (const handle of gizmoHandles) {
      const highlighted = activeGizmoHandle === handle.id;
      ctx.save();
      ctx.strokeStyle = handle.color;
      ctx.fillStyle = handle.color;
      ctx.lineWidth = highlighted ? 3 : 2;
      if (handle.mode === "move") {
        ctx.beginPath();
        ctx.moveTo(handle.start[0], handle.start[1]);
        ctx.lineTo(handle.end[0], handle.end[1]);
        ctx.stroke();
        ctx.beginPath();
        ctx.arc(handle.end[0], handle.end[1], highlighted ? 7 : 6, 0, Math.PI * 2);
        ctx.fill();
      } else if (handle.mode === "rotate") {
        ctx.beginPath();
        handle.ringPoints.forEach((point, index) => {
          if (index === 0) ctx.moveTo(point[0], point[1]);
          else ctx.lineTo(point[0], point[1]);
        });
        ctx.stroke();
      }
      ctx.font = "700 10px sans-serif";
      ctx.textBaseline = "middle";
      const labelPoint = handle.mode === "move" ? handle.end : handle.ringPoints[Math.floor(handle.ringPoints.length * 0.125)];
      ctx.fillText(handle.label, labelPoint[0] + 10, labelPoint[1]);
      ctx.restore();
    }
    updateOverlayStatus();
  }

  function applyViewportNavigation(dx, dy, mode) {
    if (mode === "rotate") {
      data.view.yaw = clamp((Number(data.view.yaw) || 0) + dx * 0.28, -180, 180, 28);
      data.view.pitch = clamp((Number(data.view.pitch) || 0) + dy * 0.18, -85, 85, 8);
      syncCameraFromView();
      writeSettings(node, widget, data);
      if (viewportMode !== "3d") {
        renderFallbackPreview(viewport, data, renderLayer);
      }
      refreshViewportOverlay();
      return;
    }
    if (mode === "pan") {
      const zoom = Math.max(0.4, Number(data.view.zoom) || 1);
      data.view.pan_x = clamp((Number(data.view.pan_x) || 0) - dx * (0.004 / zoom), -4, 4, 0);
      data.view.pan_y = clamp((Number(data.view.pan_y) || 0) + dy * (0.004 / zoom), -4, 4, 0);
      syncCameraFromView();
      writeSettings(node, widget, data);
      if (viewportMode !== "3d") {
        renderFallbackPreview(viewport, data, renderLayer);
      }
      refreshViewportOverlay();
    }
  }

  function applyGizmoDelta(handle, previousPoint, currentPoint) {
    if (!selectedJoint || !handle || !previousPoint || !currentPoint) return;
    if (handle.mode === "move") {
      const axis = [handle.end[0] - handle.start[0], handle.end[1] - handle.start[1]];
      const axisLength = Math.hypot(axis[0], axis[1]) || 1;
      const unit = [axis[0] / axisLength, axis[1] / axisLength];
      const mouseDelta = [currentPoint[0] - previousPoint[0], currentPoint[1] - previousPoint[1]];
      const amount = mouseDelta[0] * unit[0] + mouseDelta[1] * unit[1];
      const worldAmount = amount * ((Number(handle.worldLength) || 0.24) / axisLength);
      applyJointAxisDelta(data, selectedJoint, "move", handle.axis, worldAmount);
      return;
    }
    if (handle.mode === "rotate") {
      const center = handle.center;
      const prevVector = [previousPoint[0] - center[0], previousPoint[1] - center[1]];
      const currVector = [currentPoint[0] - center[0], currentPoint[1] - center[1]];
      const prevLength = Math.hypot(prevVector[0], prevVector[1]) || 1;
      const currLength = Math.hypot(currVector[0], currVector[1]) || 1;
      const dot = (prevVector[0] * currVector[0] + prevVector[1] * currVector[1]) / (prevLength * currLength);
      const det = prevVector[0] * currVector[1] - prevVector[1] * currVector[0];
      const clampedDot = Math.max(-1, Math.min(1, dot));
      const angle = Math.atan2(det, clampedDot) * (180 / Math.PI);
      applyJointAxisDelta(data, selectedJoint, "rotate", handle.axis, angle);
    }
  }

  function commit() {
    if (muteCommit) return;
    if (poseNameWidget) poseNameWidget.value = data.pose_name;
    if (posePresetWidget) posePresetWidget.value = "from_settings";
    if (mirrorModeWidget) mirrorModeWidget.value = "from_settings";
    if (captureWWidget) captureWWidget.value = Math.round(Number(data.capture_w || 1024));
    if (captureHWidget) captureHWidget.value = Math.round(Number(data.capture_h || 1024));
    if (characterStateWidget) characterStateWidget.value = data.character_state_json || "";
    if (fitModeWidget) fitModeWidget.value = "off";
    if (fitStrengthWidget) fitStrengthWidget.value = Number(data.image_fit?.strength ?? 1);
    if (Array.isArray(node.__mkrPoseLockedSize) && Array.isArray(node.size)) {
      const [lockedW, lockedH] = node.__mkrPoseLockedSize;
      if (Math.abs((Number(node.size[0]) || 0) - lockedW) > 0.5 || Math.abs((Number(node.size[1]) || 0) - lockedH) > 0.5) {
        node.size = [lockedW, lockedH];
      }
    }
    writeSettings(node, widget, data);
    if (Array.isArray(node.__mkrPoseSerialWidgets)) {
      node.widgets_values = node.__mkrPoseSerialWidgets.map((entry) => entry?.value);
    }
    syncSkeleton();
    if (viewportMode !== "3d") {
      renderFallbackPreview(viewport, data, renderLayer);
    }
    refreshViewportOverlay();
    if (referencePoseImage) {
      drawImageFitComparison();
    }
  }

  const layout = document.createElement("div");
  layout.className = "mkr-pose-layout";
  if (externalStudio) {
    layout.classList.add("mkr-pose-layout--studio");
  }
  const leftRail = document.createElement("div");
  leftRail.className = "mkr-pose-left";
  const centerRail = document.createElement("div");
  centerRail.className = "mkr-pose-center";
  const rightRail = document.createElement("div");
  rightRail.className = "mkr-pose-right";
  layout.appendChild(leftRail);
  layout.appendChild(centerRail);
  layout.appendChild(rightRail);
  panel.appendChild(layout);

  const leftTabbar = document.createElement("div");
  leftTabbar.className = "mkr-pose-tabbar";
  leftRail.appendChild(leftTabbar);

  const selectionCard = document.createElement("div");
  selectionCard.className = "mkr-pose-selection-card";
  const selectionKicker = document.createElement("div");
  selectionKicker.className = "mkr-pose-selection-kicker";
  selectionKicker.textContent = "Selected Part";
  const selectionTitle = document.createElement("div");
  selectionTitle.className = "mkr-pose-selection-title";
  const selectionNote = document.createElement("div");
  selectionNote.className = "mkr-pose-selection-note";
  selectionCard.appendChild(selectionKicker);
  selectionCard.appendChild(selectionTitle);
  selectionCard.appendChild(selectionNote);
  leftRail.appendChild(selectionCard);

  const leftPanelHost = document.createElement("div");
  leftPanelHost.style.minHeight = "0";
  if (externalStudio) {
    leftPanelHost.classList.add("mkr-pose-left-panelhost");
  }
  leftRail.appendChild(leftPanelHost);

  const viewportSection = createSection({ title: "Pose Canvas", note: "Orbit + block", delayMs: 20 });
  const viewport = createViewport("drag to orbit");
  renderLayer = document.createElement("div");
  renderLayer.className = "mkr-pose-render-layer";
  viewport.appendChild(renderLayer);
  overlayCanvas = document.createElement("canvas");
  overlayCanvas.className = "mkr-pose-overlay-canvas";
  viewport.appendChild(overlayCanvas);
  viewportSection.section.classList.add("mkr-pose-viewport-shell");
  if (externalStudio) {
    viewportSection.section.classList.add("mkr-pose-stage-section");
  }
  viewportSection.body.appendChild(viewport);
  centerRail.appendChild(viewportSection.section);

  if (externalStudio) {
    const toolDock = document.createElement("div");
    toolDock.className = "mkr-pose-tool-dock";
    const tools = [
      ["cursor", "Cursor"],
      ["move", "Move"],
      ["rotate", "Rotate"],
      ["orbit", "Orbit"],
    ];
    for (const [toolKey, label] of tools) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "mkr-pose-tool-btn";
      button.textContent = label;
      button.dataset.active = toolKey === activeTool ? "true" : "false";
      button.addEventListener("click", () => setActiveTool(toolKey));
      toolButtons.set(toolKey, button);
      toolDock.appendChild(button);
    }
    overlayStatus = document.createElement("div");
    overlayStatus.className = "mkr-pose-tool-status";
    toolDock.appendChild(overlayStatus);
    layout.appendChild(toolDock);
  }

  const metaSection = createSection({ title: "Pose", note: "Preset + naming", delayMs: 40 });
  const poseNameControl = createTextControl({
    label: "Pose Name",
    value: data.pose_name,
    placeholder: "Hero turnaround",
    onChange: (value) => {
      data.pose_name = value;
      commit();
    },
  });
  const presetControl = createSelectControl({
    label: "Preset",
    value: data.pose_preset,
    options: PRESET_OPTIONS.map((value) => ({ value, label: presetLabel(value) })),
    onChange: (next) => {
      muteCommit = true;
      applyPreset(data, next);
      data.pose_name = presetLabel(next);
      poseNameControl.input.value = data.pose_name;
      syncControlsFromData();
      muteCommit = false;
      commit();
    },
  });
  metaSection.body.appendChild(poseNameControl.element);
  metaSection.body.appendChild(presetControl.element);

  const savedPresetSection = createSection({ title: "Preset Library", note: "Save + reload your own poses", delayMs: 50 });
  const savedPresetNameControl = createTextControl({
    label: "Save As",
    value: data.pose_name || "Custom Pose",
    placeholder: "Custom Pose",
    onChange: () => {},
  });
  const savedPresetSelect = createSelectControl({
    label: "Saved",
    value: "",
    options: [{ value: "", label: "Select saved pose" }],
    onChange: (next) => {
      if (!next || !userPresets[next]) return;
      applyExternalPresetPayload(userPresets[next], next);
      poseNameControl.input.value = data.pose_name;
      presetControl.select.value = data.pose_preset;
      fitModeControl.select.value = data.image_fit?.fit_mode || "fit_from_image_structured";
      viewModeControl.select.value = data.display?.view_mode || "bones_only";
      silhouetteSourceControl.select.value = data.display?.silhouette_source || "procedural";
      silhouetteControl.select.value = data.display?.silhouette_model || "female";
      customAssetControl.input.value = data.display?.custom_asset_url || customAssetControl.input.value;
      customAssetControl.element.style.display = data.display?.silhouette_source === "custom_asset" ? "" : "none";
      syncControlsFromData();
      commit();
      savedPresetSelect.select.value = "";
    },
  });
  function refreshSavedPresetSelect() {
    const current = savedPresetSelect.select.value;
    savedPresetSelect.select.innerHTML = "";
    const defaultOption = document.createElement("option");
    defaultOption.value = "";
    defaultOption.textContent = "Select saved pose";
    savedPresetSelect.select.appendChild(defaultOption);
    for (const name of Object.keys(userPresets).sort((a, b) => a.localeCompare(b))) {
      const opt = document.createElement("option");
      opt.value = name;
      opt.textContent = name;
      savedPresetSelect.select.appendChild(opt);
    }
    savedPresetSelect.select.value = Object.prototype.hasOwnProperty.call(userPresets, current) ? current : "";
  }
  const savedPresetActions = createButtonRow([
    {
      label: "Save Current",
      tone: "accent",
      onClick: () => {
        const name = String(savedPresetNameControl.input.value || data.pose_name || "Custom Pose").trim() || "Custom Pose";
        const presetImageFit = sanitizeImageFitSettings({
          ...data.image_fit,
          reference_image_data_url: "",
          reference_image_name: "",
        });
        userPresets[name] = JSON.parse(JSON.stringify({
          pose_name: data.pose_name,
          pose_preset: data.pose_preset,
          mirror_mode: data.mirror_mode,
          view: data.view,
          display: data.display,
          image_fit: presetImageFit,
          controls: data.controls,
        }));
        saveUserPresets(userPresets);
        refreshSavedPresetSelect();
        savedPresetSelect.select.value = name;
      },
    },
    {
      label: "Delete Saved",
      tone: "ghost",
      onClick: () => {
        const name = String(savedPresetSelect.select.value || savedPresetNameControl.input.value || "").trim();
        if (!name || !userPresets[name]) return;
        delete userPresets[name];
        saveUserPresets(userPresets);
        refreshSavedPresetSelect();
      },
    },
  ]);
  refreshSavedPresetSelect();
  savedPresetSection.body.appendChild(savedPresetNameControl.element);
  savedPresetSection.body.appendChild(savedPresetSelect.element);
  savedPresetSection.body.appendChild(savedPresetActions);

  const imageFitSection = createSection({ title: "Reference Image", note: "Load an image and fit the pose locally", delayMs: 53 });
  const imageFitWrap = document.createElement("div");
  imageFitWrap.className = "mkr-pose-charbox";
  const imageFitCanvas = document.createElement("canvas");
  imageFitCanvas.width = 240;
  imageFitCanvas.height = 160;
  imageFitCanvas.style.width = "100%";
  imageFitCanvas.style.height = "160px";
  imageFitCanvas.style.objectFit = "contain";
  imageFitCanvas.style.background = "rgba(10, 14, 20, 0.92)";
  imageFitCanvas.style.borderRadius = "8px";
  const imageFitNote = document.createElement("div");
  imageFitNote.className = "mkr-section-note";
  imageFitNote.style.marginTop = "6px";
  imageFitNote.textContent = "No reference image loaded.";
  imageFitWrap.appendChild(imageFitCanvas);
  imageFitWrap.appendChild(imageFitNote);
  const imageCompareCanvas = document.createElement("canvas");
  imageCompareCanvas.width = 256;
  imageCompareCanvas.height = 128;
  imageCompareCanvas.style.width = "100%";
  imageCompareCanvas.style.height = "128px";
  imageCompareCanvas.style.marginTop = "8px";
  imageCompareCanvas.style.background = "rgba(10, 14, 20, 0.92)";
  imageCompareCanvas.style.borderRadius = "8px";
  imageFitWrap.appendChild(imageCompareCanvas);
  const imageInput = document.createElement("input");
  imageInput.type = "file";
  imageInput.accept = "image/*";
  imageInput.style.display = "none";
  function syncImageFitWidgets() {
    if (backing.pose_from_image_mode) backing.pose_from_image_mode.value = data.image_fit?.fit_mode || "off";
    if (backing.pose_image_strength) backing.pose_image_strength.value = data.image_fit?.strength ?? 1;
  }
  async function loadReferencePoseImageFromDataUrl(dataUrl, label = "") {
    const text = String(dataUrl || "").trim();
    if (!text) {
      referencePoseImage = null;
      lastImageFitScore = null;
      imageFitNote.textContent = "No reference image loaded.";
      drawReferencePreview();
      drawImageFitComparison();
      return;
    }
    const img = new Image();
    await new Promise((resolve, reject) => {
      img.onload = resolve;
      img.onerror = reject;
      img.src = text;
    });
    referencePoseImage = img;
    lastImageFitScore = null;
    imageFitNote.textContent = `${label || data.image_fit?.reference_image_name || "Reference image"} • ${img.naturalWidth}×${img.naturalHeight}`;
    drawReferencePreview();
    drawImageFitComparison();
  }
  function adoptReferenceImageSize() {
    if (!referencePoseImage) return;
    data.capture_w = clamp(referencePoseImage.naturalWidth, 64, 8192, 1024);
    data.capture_h = clamp(referencePoseImage.naturalHeight, 64, 8192, 1024);
    if (typeof captureWControl !== "undefined" && captureWControl?.setValue) captureWControl.setValue(data.capture_w);
    if (typeof captureHControl !== "undefined" && captureHControl?.setValue) captureHControl.setValue(data.capture_h);
    commit();
  }
  function getReferencePreviewRect() {
    if (!referencePoseImage) return null;
    const aspect = referencePoseImage.naturalWidth / Math.max(1, referencePoseImage.naturalHeight);
    let drawW = imageFitCanvas.width;
    let drawH = drawW / Math.max(0.001, aspect);
    if (drawH > imageFitCanvas.height) {
      drawH = imageFitCanvas.height;
      drawW = drawH * aspect;
    }
    return {
      x: (imageFitCanvas.width - drawW) * 0.5,
      y: (imageFitCanvas.height - drawH) * 0.5,
      w: drawW,
      h: drawH,
    };
  }
  function drawReferencePreview() {
    const ctx = imageFitCanvas.getContext("2d");
    if (!ctx) return;
    ctx.clearRect(0, 0, imageFitCanvas.width, imageFitCanvas.height);
    ctx.fillStyle = "#0b1118";
    ctx.fillRect(0, 0, imageFitCanvas.width, imageFitCanvas.height);
    if (!referencePoseImage) return;
    const rect = getReferencePreviewRect();
    if (!rect) return;
    ctx.drawImage(referencePoseImage, rect.x, rect.y, rect.w, rect.h);
    ctx.lineWidth = 1.5;
    ctx.font = "700 10px sans-serif";
    ctx.textBaseline = "bottom";
    for (const [key, anchor] of Object.entries(data.image_fit?.anchors || {})) {
      const x = rect.x + rect.w * clamp(anchor.x, 0, 1, 0.5);
      const y = rect.y + rect.h * clamp(anchor.y, 0, 1, 0.5);
      const selected = key === data.image_fit?.selected_anchor;
      ctx.fillStyle = "rgba(8, 12, 16, 0.96)";
      ctx.beginPath();
      ctx.arc(x, y, selected ? 7 : 6, 0, Math.PI * 2);
      ctx.fill();
      ctx.fillStyle = selected ? "#f3a03f" : "#d6f976";
      ctx.beginPath();
      ctx.arc(x, y, selected ? 5 : 4, 0, Math.PI * 2);
      ctx.fill();
      ctx.fillText(key.replace(/_/g, " "), x + 8, y - 6);
    }
  }
  function drawImageFitComparison() {
    const ctx = imageCompareCanvas.getContext("2d");
    if (!ctx) return;
    ctx.clearRect(0, 0, imageCompareCanvas.width, imageCompareCanvas.height);
    ctx.fillStyle = "#0b1118";
    ctx.fillRect(0, 0, imageCompareCanvas.width, imageCompareCanvas.height);

    const leftX = 8;
    const topY = 22;
    const panelW = 112;
    const panelH = 96;
    const gap = 16;
    const rightX = leftX + panelW + gap;

    ctx.fillStyle = "#dbe4ec";
    ctx.font = "600 11px sans-serif";
    ctx.fillText("Reference", leftX, 12);
    ctx.fillText("Current Fit", rightX, 12);

    ctx.fillStyle = "#10161e";
    ctx.fillRect(leftX, topY, panelW, panelH);
    ctx.fillRect(rightX, topY, panelW, panelH);

    if (referencePoseImage) {
      const mask = extractReferenceMaskFromImage(referencePoseImage, 96);
      const refCanvas = document.createElement("canvas");
      refCanvas.width = 96;
      refCanvas.height = 96;
      const refCtx = refCanvas.getContext("2d");
      if (refCtx) {
        const imageData = refCtx.createImageData(96, 96);
        for (let i = 0; i < mask.length; i += 1) {
          const on = mask[i] > 0 ? 255 : 0;
          imageData.data[i * 4] = on;
          imageData.data[i * 4 + 1] = on;
          imageData.data[i * 4 + 2] = on;
          imageData.data[i * 4 + 3] = 255;
        }
        refCtx.putImageData(imageData, 0, 0);
        ctx.drawImage(refCanvas, leftX + 8, topY, panelH, panelH);
      }
    }

    const poseMask = renderPoseMaskForFit(data, 96, 96);
    const poseCanvas = document.createElement("canvas");
    poseCanvas.width = 96;
    poseCanvas.height = 96;
    const poseCtx = poseCanvas.getContext("2d");
    if (poseCtx) {
      const imageData = poseCtx.createImageData(96, 96);
      for (let i = 0; i < poseMask.length; i += 1) {
        const on = poseMask[i] > 0 ? 255 : 0;
        imageData.data[i * 4] = 120;
        imageData.data[i * 4 + 1] = 188;
        imageData.data[i * 4 + 2] = 255;
        imageData.data[i * 4 + 3] = on;
      }
      poseCtx.putImageData(imageData, 0, 0);
      ctx.drawImage(poseCanvas, rightX + 8, topY, panelH, panelH);
    }

    if (lastImageFitScore != null) {
      ctx.fillStyle = "#9fb3c5";
      ctx.font = "600 10px sans-serif";
      ctx.fillText(`Fit ${(lastImageFitScore * 100).toFixed(1)}%`, rightX, topY + panelH + 16);
    }
    const anchorCount = Object.keys(data.image_fit?.anchors || {}).length;
    if (anchorCount) {
      ctx.fillStyle = "#d6f976";
      ctx.font = "600 10px sans-serif";
      ctx.fillText(`${anchorCount} anchors`, leftX, topY + panelH + 16);
    }
  }
  imageFitCanvas.addEventListener("click", (event) => {
    if (!referencePoseImage) return;
    const rect = getReferencePreviewRect();
    if (!rect) return;
    const bounds = imageFitCanvas.getBoundingClientRect();
    const x = ((event.clientX - bounds.left) / Math.max(1, bounds.width)) * imageFitCanvas.width;
    const y = ((event.clientY - bounds.top) / Math.max(1, bounds.height)) * imageFitCanvas.height;
    if (x < rect.x || x > rect.x + rect.w || y < rect.y || y > rect.y + rect.h) return;
    const anchorKey = data.image_fit?.selected_anchor || "head";
    data.image_fit.anchors[anchorKey] = {
      x: clamp((x - rect.x) / Math.max(1e-6, rect.w), 0, 1, 0.5),
      y: clamp((y - rect.y) / Math.max(1e-6, rect.h), 0, 1, 0.5),
    };
    commit();
  });
  imageInput.addEventListener("change", () => {
    const file = imageInput.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      const result = String(reader.result || "");
      data.image_fit.reference_image_data_url = result;
      data.image_fit.reference_image_name = file.name || "Reference image";
      syncImageFitWidgets();
      commit();
      loadReferencePoseImageFromDataUrl(result, file.name || "Reference image")
        .then(() => adoptReferenceImageSize())
        .catch((error) => {
          console.warn("Pose Studio reference image load failed:", error);
          referencePoseImage = null;
          lastImageFitScore = null;
          imageFitNote.textContent = "Reference image failed to load.";
          drawReferencePreview();
          drawImageFitComparison();
        });
    };
    reader.readAsDataURL(file);
  });
  const fitLockSection = document.createElement("div");
  fitLockSection.className = "mkr-stack";
  fitLockSection.style.marginTop = "8px";
  const fitModeControl = createSelectControl({
    label: "Fit Mode",
    value: data.image_fit?.fit_mode || "fit_from_image_structured",
    options: [
      { value: "fit_from_image", label: "Silhouette" },
      { value: "fit_from_image_structured", label: "Structured" },
    ],
    onChange: (next) => {
      data.image_fit.fit_mode = ["fit_from_image", "fit_from_image_structured"].includes(String(next))
        ? String(next)
        : "fit_from_image_structured";
      syncImageFitWidgets();
      commit();
    },
  });
  const fitStrengthControl = createSliderControl({
    label: "Fit Strength",
    min: 0,
    max: 1,
    step: 0.05,
    value: data.image_fit?.strength ?? 1,
    decimals: 2,
    onChange: (next) => {
      data.image_fit.strength = clamp(next, 0, 1, 1);
      syncImageFitWidgets();
      commit();
    },
  });
  const anchorSelect = createSelectControl({
    label: "Anchor Joint",
    value: data.image_fit?.selected_anchor || "head",
    options: IMAGE_FIT_ANCHOR_OPTIONS.map(([value, label]) => ({ value, label })),
    onChange: (next) => {
      data.image_fit.selected_anchor = IMAGE_FIT_ANCHOR_SET.has(String(next)) ? String(next) : "head";
      drawReferencePreview();
    },
  });
  const anchorActions = createButtonRow([
    {
      label: "Clear Selected",
      tone: "ghost",
      onClick: () => {
        delete data.image_fit.anchors[data.image_fit.selected_anchor || "head"];
        commit();
      },
    },
    {
      label: "Clear All Anchors",
      tone: "ghost",
      onClick: () => {
        data.image_fit.anchors = {};
        commit();
      },
    },
  ]);
  const anchorNote = document.createElement("div");
  anchorNote.className = "mkr-section-note";
  anchorNote.textContent = "Choose a joint, then click the image to place anchors.";
  fitLockSection.appendChild(anchorSelect.element);
  fitLockSection.appendChild(fitModeControl.element);
  fitLockSection.appendChild(fitStrengthControl.element);
  fitLockSection.appendChild(anchorActions);
  fitLockSection.appendChild(anchorNote);
  IMAGE_FIT_GROUP_LABELS.forEach(([key, label]) => {
    const toggle = createToggleControl({
      label: `Use ${label}`,
      checked: data.image_fit?.enabled_groups?.[key] !== false,
      onChange: (checked) => {
        data.image_fit.enabled_groups[key] = !!checked;
        commit();
      },
    });
    fitLockSection.appendChild(toggle.element);
  });
  [
    ["torso", "Lock Torso"],
    ["head", "Lock Head"],
    ["arms", "Lock Arms"],
    ["legs", "Lock Legs"],
  ].forEach(([key, label]) => {
    const toggle = createToggleControl({
      label,
      checked: fitLocks[key],
      onChange: (checked) => {
        fitLocks[key] = !!checked;
        drawImageFitComparison();
      },
    });
    fitLockSection.appendChild(toggle.element);
  });
  const imageFitActions = createButtonRow([
    {
      label: "Load Image",
      tone: "accent",
      onClick: () => imageInput.click(),
    },
    {
      label: "Fit From Image",
      tone: "ghost",
      onClick: () => {
        if (!referencePoseImage) return;
        adoptReferenceImageSize();
        const activeFitMode = data.image_fit?.fit_mode || "fit_from_image_structured";
        const activeFitStrength = clamp(data.image_fit?.strength, 0, 1, 1);
        const targetMask = extractReferenceMaskFromImage(referencePoseImage, 128);
        const targetFrameHint = maskFrameHint(targetMask, 128, 128);
        const autoAnchors = extractPoseReferenceAnchors(targetMask, 128, 128);
        const manualAnchors = filteredAnchorsForPoseData(data);
        const baseAnchors = { ...autoAnchors, ...manualAnchors };
        const fitTargets = [
          { orientation: "direct", mask: targetMask },
          { orientation: "mirrored", mask: flipMaskHorizontal(targetMask, 128, 128) },
        ];
        let bestScore = -1;
        let bestSettings = JSON.parse(JSON.stringify(exportPoseState()));
        let bestPreset = data.pose_preset || "neutral";
        let bestOrientation = "direct";
        for (const fitTarget of fitTargets) {
          const orientedAnchors = fitTarget.orientation === "mirrored"
            ? mirrorAnchorsHorizontal(baseAnchors)
            : baseAnchors;
          for (const presetKey of PRESET_OPTIONS) {
            const trial = JSON.parse(JSON.stringify(exportPoseState()));
            applyPreset(trial, presetKey);
            let coarse = runCoarseFitPass(fitTarget.mask, trial, 128, 128, orientedAnchors, activeFitMode);
            let score = coarse.score;
            Object.assign(trial, coarse.pose);
            for (const step of [28, 14, 7]) {
              let improved = true;
              while (improved) {
                improved = false;
                for (const [key, spec] of Object.entries(CONTROL_SPECS)) {
                  if (isFitControlLocked(key)) continue;
                  const current = Number(trial.controls[key] || spec.default);
                  let localBestScore = score;
                  let localBestValue = current;
                  for (const candidate of [current - step, current + step]) {
                    const bounded = clamp(candidate, spec.min, spec.max, spec.default);
                    if (Math.abs(bounded - current) < 1e-6) continue;
                    const probe = JSON.parse(JSON.stringify(trial));
                    probe.controls[key] = bounded;
                    const probeScore = fitObjectiveScore(
                      renderPoseMaskForFit(probe, 128, 128),
                      fitTarget.mask,
                      probe,
                      128,
                      128,
                      orientedAnchors,
                      activeFitMode,
                    );
                    if (probeScore > localBestScore) {
                      localBestScore = probeScore;
                      localBestValue = bounded;
                    }
                  }
                  if (localBestValue !== current) {
                    trial.controls[key] = localBestValue;
                    score = localBestScore;
                    improved = true;
                  }
                }
              }
            }
            if (score > bestScore) {
              bestScore = score;
              bestSettings = trial;
              bestPreset = presetKey;
              bestOrientation = fitTarget.orientation;
            }
          }
          for (const seed of FIT_EXTRA_SEEDS) {
            const trial = JSON.parse(JSON.stringify(exportPoseState()));
            trial.pose_preset = seed.name;
            applySeedControls(trial, seed.controls);
            let coarse = runCoarseFitPass(fitTarget.mask, trial, 128, 128, orientedAnchors, activeFitMode);
            let score = coarse.score;
            Object.assign(trial, coarse.pose);
            for (const step of [28, 14, 7]) {
              let improved = true;
              while (improved) {
                improved = false;
                for (const [key, spec] of Object.entries(CONTROL_SPECS)) {
                  if (isFitControlLocked(key)) continue;
                  const current = Number(trial.controls[key] || spec.default);
                  let localBestScore = score;
                  let localBestValue = current;
                  for (const candidate of [current - step, current + step]) {
                    const bounded = clamp(candidate, spec.min, spec.max, spec.default);
                    if (Math.abs(bounded - current) < 1e-6) continue;
                    const probe = JSON.parse(JSON.stringify(trial));
                    probe.controls[key] = bounded;
                    const probeScore = fitObjectiveScore(
                      renderPoseMaskForFit(probe, 128, 128),
                      fitTarget.mask,
                      probe,
                      128,
                      128,
                      orientedAnchors,
                      activeFitMode,
                    );
                    if (probeScore > localBestScore) {
                      localBestScore = probeScore;
                      localBestValue = bounded;
                    }
                  }
                  if (localBestValue !== current) {
                    trial.controls[key] = localBestValue;
                    score = localBestScore;
                    improved = true;
                  }
                }
              }
            }
            if (score > bestScore) {
              bestScore = score;
              bestSettings = trial;
              bestPreset = PRESET_OPTIONS.includes(seed.preset) ? seed.preset : "neutral";
              bestOrientation = fitTarget.orientation;
            }
          }
        }
        if (bestOrientation === "mirrored") {
          swapPoseSides(bestSettings);
        }
        if (activeFitStrength < 0.999) {
          const sourcePose = exportPoseState();
          for (const [key, spec] of Object.entries(CONTROL_SPECS)) {
            const baseValue = Number(sourcePose.controls?.[key] ?? spec.default);
            const fitValue = Number(bestSettings.controls?.[key] ?? baseValue);
            bestSettings.controls[key] = clamp(
              baseValue + (fitValue - baseValue) * activeFitStrength,
              spec.min,
              spec.max,
              spec.default,
            );
          }
        }
        bestSettings.view = { ...FIT_VIEW };
        bestSettings.image_fit = sanitizeImageFitSettings({
          ...(bestSettings.image_fit || {}),
          ...(data.image_fit || {}),
          fit_mode: activeFitMode,
          strength: activeFitStrength,
          frame_hint: targetFrameHint,
        });
        if (referencePoseImage) {
          bestSettings.capture_w = clamp(referencePoseImage.naturalWidth, 64, 8192, 1024);
          bestSettings.capture_h = clamp(referencePoseImage.naturalHeight, 64, 8192, 1024);
        }
        applyExternalPresetPayload(bestSettings, "Image Fit");
        data.pose_preset = bestPreset;
        data.pose_name = "Image Fit";
        lastImageFitScore = bestScore;
        poseNameControl.input.value = data.pose_name;
        presetControl.select.value = data.pose_preset;
        syncControlsFromData();
        commit();
        const anchorCount = Object.keys(baseAnchors).length;
        const autoAnchorCount = Math.max(0, anchorCount - Object.keys(manualAnchors).length);
        const modeLabel = activeFitMode === "fit_from_image_structured" ? "structured" : "silhouette";
        imageFitNote.textContent = `${imageFitNote.textContent.split(" • ")[0]} • ${modeLabel} • fit ${(bestScore * 100).toFixed(1)}% • ${bestOrientation}${anchorCount ? ` • ${anchorCount} anchors` : ""}${autoAnchorCount ? ` (${autoAnchorCount} auto)` : ""}`;
        drawImageFitComparison();
      },
    },
    {
      label: "Clear",
      tone: "ghost",
      onClick: () => {
        referencePoseImage = null;
        lastImageFitScore = null;
        imageInput.value = "";
        data.image_fit.reference_image_data_url = "";
        data.image_fit.reference_image_name = "";
        syncImageFitWidgets();
        commit();
        imageFitNote.textContent = "No reference image loaded.";
        drawReferencePreview();
        drawImageFitComparison();
      },
    },
  ]);
  drawReferencePreview();
  drawImageFitComparison();
  syncImageFitWidgets();
  if (data.image_fit?.reference_image_data_url) {
    loadReferencePoseImageFromDataUrl(data.image_fit.reference_image_data_url, data.image_fit.reference_image_name)
      .catch((error) => {
        console.warn("Pose Studio saved reference image load failed:", error);
      });
  }
  imageFitSection.body.appendChild(imageInput);
  imageFitSection.body.appendChild(imageFitWrap);
  imageFitSection.body.appendChild(fitLockSection);
  imageFitSection.body.appendChild(imageFitActions);

  const jsonSection = createSection({ title: "Pose JSON", note: "Paste, import, or copy full pose state", delayMs: 55 });
  const jsonBoxWrap = document.createElement("div");
  jsonBoxWrap.className = "mkr-pose-charbox";
  const jsonArea = document.createElement("textarea");
  jsonArea.value = JSON.stringify(exportPoseState(), null, 2);
  jsonArea.spellcheck = false;
  jsonBoxWrap.appendChild(jsonArea);
  const jsonActions = createButtonRow([
    {
      label: "Sync From Pose",
      tone: "accent",
      onClick: () => {
        jsonArea.value = JSON.stringify(exportPoseState(), null, 2);
      },
    },
    {
      label: "Apply JSON",
      tone: "ghost",
      onClick: () => {
        try {
          const parsed = JSON.parse(String(jsonArea.value || "{}"));
          applyExternalPresetPayload(parsed, parsed?.pose_name || "Imported Pose");
          poseNameControl.input.value = data.pose_name;
          presetControl.select.value = data.pose_preset;
          savedPresetNameControl.input.value = data.pose_name || "Custom Pose";
          fitModeControl.select.value = data.image_fit?.fit_mode || "fit_from_image_structured";
          viewModeControl.select.value = data.display?.view_mode || "bones_only";
          silhouetteSourceControl.select.value = data.display?.silhouette_source || "procedural";
          silhouetteControl.select.value = data.display?.silhouette_model || "female";
          customAssetControl.input.value = data.display?.custom_asset_url || customAssetControl.input.value;
          customAssetControl.element.style.display = data.display?.silhouette_source === "custom_asset" ? "" : "none";
          syncControlsFromData();
          commit();
          jsonArea.value = JSON.stringify(exportPoseState(), null, 2);
        } catch (error) {
          console.warn("Pose Studio JSON import failed:", error);
        }
      },
    },
    {
      label: "Copy JSON",
      tone: "ghost",
      onClick: async () => {
        const text = JSON.stringify(exportPoseState(), null, 2);
        jsonArea.value = text;
        try {
          await navigator.clipboard.writeText(text);
        } catch {
        }
      },
    },
  ]);
  jsonSection.body.appendChild(jsonBoxWrap);
  jsonSection.body.appendChild(jsonActions);

  const rightScroll = externalStudio ? document.createElement("div") : rightRail;
  if (externalStudio) {
    rightScroll.className = "mkr-pose-right-scroll";
    rightRail.appendChild(rightScroll);
  }
  rightScroll.appendChild(metaSection.section);
  rightScroll.appendChild(savedPresetSection.section);
  rightScroll.appendChild(imageFitSection.section);
  rightScroll.appendChild(jsonSection.section);

  const outputSection = createSection({ title: "Export", note: "Guide size", delayMs: 60 });
  const captureWControl = createNumberControl({
    label: "Width",
    value: data.capture_w,
    min: 384,
    max: 2048,
    step: 64,
    onChange: (next) => {
      data.capture_w = clamp(next, 384, 2048, 1024);
      commit();
    },
  });
  const captureHControl = createNumberControl({
    label: "Height",
    value: data.capture_h,
    min: 384,
    max: 2048,
    step: 64,
    onChange: (next) => {
      data.capture_h = clamp(next, 384, 2048, 1024);
      commit();
    },
  });
  outputSection.body.appendChild(captureWControl.element);
  outputSection.body.appendChild(captureHControl.element);
  rightScroll.appendChild(outputSection.section);

  const displaySection = createSection({ title: "Display", note: "Viewport mesh + mode", delayMs: 70 });
  const viewModeControl = createSelectControl({
    label: "View Mode",
    value: data.display?.view_mode || "bones_only",
    options: [
      { value: "bones_only", label: "Bones Only" },
      { value: "bones_mesh", label: "Bones + Mesh" },
      { value: "depth_mesh", label: "Depth Mesh" },
    ],
    onChange: (next) => {
      data.display = sanitizeDisplaySettings({ ...(data.display || {}), view_mode: next });
      commit();
    },
  });
  const silhouetteSourceControl = createSelectControl({
    label: "Mesh Source",
    value: data.display?.silhouette_source || "procedural",
    options: [
      { value: "procedural", label: "Procedural" },
      { value: "custom_asset", label: "Custom Asset" },
    ],
    onChange: (next) => {
      data.display = sanitizeDisplaySettings({ ...(data.display || {}), silhouette_source: next });
      customAssetControl.element.style.display = data.display.silhouette_source === "custom_asset" ? "" : "none";
      commit();
    },
  });
  const silhouetteControl = createSelectControl({
    label: "Silhouette",
    value: data.display?.silhouette_model || "female",
    options: [
      { value: "female", label: "Female" },
      { value: "male", label: "Male" },
    ],
    onChange: (next) => {
      data.display = sanitizeDisplaySettings({ ...(data.display || {}), silhouette_model: next });
      commit();
    },
  });
  const customAssetControl = createTextControl({
    label: "Asset URL",
    value: data.display?.custom_asset_url || "/extensions/MKRShift_Nodes/assets/pose_studio/custom_silhouette.glb",
    placeholder: "/extensions/MKRShift_Nodes/assets/pose_studio/custom_silhouette.glb",
    onChange: (next) => {
      data.display = sanitizeDisplaySettings({ ...(data.display || {}), custom_asset_url: next });
      commit();
    },
  });
  customAssetControl.element.style.display = (data.display?.silhouette_source || "procedural") === "custom_asset" ? "" : "none";
  displaySection.body.appendChild(viewModeControl.element);
  displaySection.body.appendChild(silhouetteSourceControl.element);
  displaySection.body.appendChild(silhouetteControl.element);
  displaySection.body.appendChild(customAssetControl.element);
  rightScroll.appendChild(displaySection.section);

  const torsoGroup = document.createElement("div");
  torsoGroup.className = "mkr-pose-panel-group";
  torsoGroup.dataset.group = "torso";
  const torsoSection = createSection({ title: "Mesh Parameters", note: "Torso + head", delayMs: 80 });
  const controlHandles = new Map();
  ["root_yaw", "root_pitch", "root_roll", "spine_bend", "spine_twist", "head_yaw", "head_pitch", "head_roll"].forEach((key) => {
    const spec = CONTROL_SPECS[key];
    const slider = createSliderControl({
      label: spec.label,
      min: spec.min,
      max: spec.max,
      step: spec.step,
      value: data.controls[key],
      decimals: 0,
      onChange: (next) => {
        data.controls[key] = next;
        commit();
      },
    });
    slider.element.dataset.poseKey = key;
    slider.baseLabel = spec.label;
    controlHandles.set(key, slider);
    torsoSection.body.appendChild(slider.element);
  });
  torsoGroup.appendChild(torsoSection.section);

  const armsGroup = document.createElement("div");
  armsGroup.className = "mkr-pose-panel-group";
  armsGroup.dataset.group = "arms";
  const armsSection = createSection({ title: "Upper Body", note: "Arm posing", delayMs: 100 });
  const leftArmChip = createGroupChip("Left Arm");
  armsSection.body.appendChild(leftArmChip);
  ["arm_raise_l", "arm_forward_l", "arm_twist_l", "elbow_bend_l", "wrist_twist_l"].forEach((key) => {
    const spec = CONTROL_SPECS[key];
    const slider = createSliderControl({
      label: spec.label,
      min: spec.min,
      max: spec.max,
      step: spec.step,
      value: data.controls[key],
      decimals: 0,
      onChange: (next) => {
        data.controls[key] = next;
        commit();
      },
    });
    slider.element.dataset.poseKey = key;
    slider.baseLabel = spec.label;
    controlHandles.set(key, slider);
    armsSection.body.appendChild(slider.element);
  });
  const rightArmChip = createGroupChip("Right Arm");
  armsSection.body.appendChild(rightArmChip);
  ["arm_raise_r", "arm_forward_r", "arm_twist_r", "elbow_bend_r", "wrist_twist_r"].forEach((key) => {
    const spec = CONTROL_SPECS[key];
    const slider = createSliderControl({
      label: spec.label,
      min: spec.min,
      max: spec.max,
      step: spec.step,
      value: data.controls[key],
      decimals: 0,
      onChange: (next) => {
        data.controls[key] = next;
        commit();
      },
    });
    slider.element.dataset.poseKey = key;
    slider.baseLabel = spec.label;
    controlHandles.set(key, slider);
    armsSection.body.appendChild(slider.element);
  });
  armsGroup.appendChild(armsSection.section);

  const legsGroup = document.createElement("div");
  legsGroup.className = "mkr-pose-panel-group";
  legsGroup.dataset.group = "legs";
  const legsSection = createSection({ title: "Lower Body", note: "Stride + balance", delayMs: 120 });
  const leftLegChip = createGroupChip("Left Leg");
  legsSection.body.appendChild(leftLegChip);
  ["hip_lift_l", "hip_side_l", "knee_bend_l", "foot_point_l"].forEach((key) => {
    const spec = CONTROL_SPECS[key];
    const slider = createSliderControl({
      label: spec.label,
      min: spec.min,
      max: spec.max,
      step: spec.step,
      value: data.controls[key],
      decimals: 0,
      onChange: (next) => {
        data.controls[key] = next;
        commit();
      },
    });
    slider.element.dataset.poseKey = key;
    slider.baseLabel = spec.label;
    controlHandles.set(key, slider);
    legsSection.body.appendChild(slider.element);
  });
  const rightLegChip = createGroupChip("Right Leg");
  legsSection.body.appendChild(rightLegChip);
  ["hip_lift_r", "hip_side_r", "knee_bend_r", "foot_point_r"].forEach((key) => {
    const spec = CONTROL_SPECS[key];
    const slider = createSliderControl({
      label: spec.label,
      min: spec.min,
      max: spec.max,
      step: spec.step,
      value: data.controls[key],
      decimals: 0,
      onChange: (next) => {
        data.controls[key] = next;
        commit();
      },
    });
    slider.element.dataset.poseKey = key;
    slider.baseLabel = spec.label;
    controlHandles.set(key, slider);
    legsSection.body.appendChild(slider.element);
  });
  legsGroup.appendChild(legsSection.section);

  leftPanelHost.appendChild(torsoGroup);
  leftPanelHost.appendChild(armsGroup);
  leftPanelHost.appendChild(legsGroup);

  const leftGroups = { torso: torsoGroup, arms_l: armsGroup, arms_r: armsGroup, legs_l: legsGroup, legs_r: legsGroup };
  const leftTabs = {};
  function setActiveLeftGroup(nextGroup) {
    torsoGroup.dataset.active = nextGroup === "torso" ? "true" : "false";
    armsGroup.dataset.active = nextGroup === "arms_l" || nextGroup === "arms_r" ? "true" : "false";
    legsGroup.dataset.active = nextGroup === "legs_l" || nextGroup === "legs_r" ? "true" : "false";
    for (const [key, button] of Object.entries(leftTabs)) {
      button.dataset.active = key === nextGroup ? "true" : "false";
    }
  }

  function updateSelectionPanel() {
    const groupKey = getJointControlGroup(selectedJoint);
    const labelHints = getJointAxisControlLabels(selectedJoint);
    setActiveLeftGroup(groupKey);
    const visibleKeys = new Set(groupKey === "torso" ? JOINT_CONTROL_GROUPS.torso : JOINT_CONTROL_GROUPS[groupKey] || []);
    for (const [key, handle] of controlHandles.entries()) {
      handle.element.style.display = visibleKeys.has(key) ? "" : "none";
      if (typeof handle.setLabel === "function") {
        handle.setLabel(labelHints[key] || handle.baseLabel || CONTROL_SPECS[key]?.label || key);
      }
    }
    leftArmChip.style.display = groupKey === "arms_l" ? "" : "none";
    rightArmChip.style.display = groupKey === "arms_r" ? "" : "none";
    leftLegChip.style.display = groupKey === "legs_l" ? "" : "none";
    rightLegChip.style.display = groupKey === "legs_r" ? "" : "none";
    if (!selectedJoint) {
      selectionTitle.textContent = "Body / Neutral";
      selectionNote.textContent = "Pick a joint to focus the relevant controls.";
      return;
    }
    selectionTitle.textContent = jointLabel(selectedJoint);
    selectionNote.textContent =
      groupKey === "torso"
        ? "World X/Y/Z hints are shown on the active torso controls."
        : groupKey.startsWith("arms")
          ? "The visible controls now show which sliders are acting as X, Y, and Z."
          : "The visible controls now show which sliders are acting as X, Y, and Z.";
  }

  [
    ["torso", "Torso"],
    ["arms_l", "Arm"],
    ["legs_l", "Leg"],
  ].forEach(([key, label]) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "mkr-pose-tab";
    button.textContent = label;
    button.addEventListener("click", () => setActiveLeftGroup(key));
    leftTabs[key] = button;
    leftTabbar.appendChild(button);
  });
  updateSelectionPanel();

  const actionSection = createSection({ title: "Studio Actions", note: "Reset + mirror", delayMs: 140 });
  const actionGrid = createButtonRow([
    {
      label: "Neutral",
      tone: "accent",
      onClick: () => {
        muteCommit = true;
        Object.assign(data, defaultSettings());
        data.capture_w = clamp(captureWWidget?.value, 384, 2048, 1024);
        data.capture_h = clamp(captureHWidget?.value, 384, 2048, 1024);
        data.character_state_json = String(characterStateWidget?.value || "");
        syncControlsFromData();
        captureWControl.setValue(data.capture_w);
        captureHControl.setValue(data.capture_h);
        presetControl.select.value = data.pose_preset;
        poseNameControl.input.value = data.pose_name;
        muteCommit = false;
        syncCameraFromView();
        commit();
      },
    },
    {
      label: "Mirror L→R",
      onClick: () => {
        muteCommit = true;
        mirrorControls(data, "left_to_right");
        syncControlsFromData();
        muteCommit = false;
        commit();
      },
    },
    {
      label: "Mirror R→L",
      onClick: () => {
        muteCommit = true;
        mirrorControls(data, "right_to_left");
        syncControlsFromData();
        muteCommit = false;
        commit();
      },
    },
    {
      label: "Copy JSON",
      onClick: async () => {
        try {
          await navigator.clipboard.writeText(JSON.stringify(data, null, 2));
        } catch {
        }
      },
    },
  ]);
  actionGrid.classList.add("mkr-pose-action-grid");
  actionSection.body.appendChild(actionGrid);
  if (externalStudio) {
    const actionDock = document.createElement("div");
    actionDock.className = "mkr-pose-action-dock";
    actionDock.appendChild(actionSection.section);
    rightRail.appendChild(actionDock);
  } else {
    centerRail.appendChild(actionSection.section);
  }

  const characterSection = createSection({ title: "Character", note: "Optional state payload", delayMs: 160 });
  const charBox = document.createElement("div");
  charBox.className = "mkr-pose-charbox";
  const charInput = document.createElement("textarea");
  charInput.placeholder = "Optional character_state_json";
  charInput.value = data.character_state_json || "";
  charInput.addEventListener("change", () => {
    data.character_state_json = charInput.value;
    commit();
  });
  charBox.appendChild(charInput);
  characterSection.body.appendChild(charBox);
  rightScroll.appendChild(characterSection.section);

  function syncControlsFromData() {
    for (const [key, handle] of controlHandles.entries()) {
      handle.setValue(data.controls[key]);
    }
  }

  function clearViewportNavigation(event = null) {
    viewportNavState = null;
    try {
      if (event && viewport.hasPointerCapture?.(event.pointerId)) {
        viewport.releasePointerCapture(event.pointerId);
      }
    } catch {
    }
  }

  const handleViewportPointerDown = (event) => {
    const navMode =
      event.button === 1
        ? (event.shiftKey ? "pan" : "rotate")
        : event.button === 2
          ? "pan"
          : "";
    if (navMode) {
      viewportNavState = {
        mode: navMode,
        x: event.clientX,
        y: event.clientY,
        pointerId: event.pointerId,
      };
      viewport.setPointerCapture?.(event.pointerId);
      event.preventDefault();
      event.stopPropagation();
      return;
    }
    if (event.button !== 0) return;
    const rect = viewport.getBoundingClientRect();
    const localX = event.clientX - rect.left;
    const localY = event.clientY - rect.top;
    const gizmoHandle = pickGizmoHandle(localX, localY);
    if (gizmoHandle) {
      activeGizmoHandle = gizmoHandle.id;
      dragState = {
        kind: "gizmo",
        x: localX,
        y: localY,
        joint: selectedJoint,
        handle: gizmoHandle,
      };
      viewport.setPointerCapture?.(event.pointerId);
      refreshViewportOverlay();
      event.preventDefault();
      event.stopPropagation();
      return;
    }
    const hitJoint = pickJointAt(localX, localY);
    if (!hitJoint) {
      selectedJoint = "";
      dragState = null;
      activeGizmoHandle = "";
      updateSelectionPanel();
      updateOverlayStatus();
      refreshViewportOverlay();
      event.preventDefault();
      event.stopPropagation();
      return;
    }
    selectedJoint = hitJoint;
    activeGizmoHandle = "";
    updateSelectionPanel();
    updateOverlayStatus();
    refreshViewportOverlay();
    event.preventDefault();
    event.stopPropagation();
  };

  const handleViewportPointerMove = (event) => {
    if (viewportNavState) {
      const dx = event.clientX - viewportNavState.x;
      const dy = event.clientY - viewportNavState.y;
      viewportNavState.x = event.clientX;
      viewportNavState.y = event.clientY;
      applyViewportNavigation(dx, dy, viewportNavState.mode);
      event.preventDefault();
      event.stopPropagation();
      return;
    }
    if (!dragState || dragState.joint !== selectedJoint) return;
    const rect = viewport.getBoundingClientRect();
    const localX = event.clientX - rect.left;
    const localY = event.clientY - rect.top;
    const dx = localX - dragState.x;
    const dy = localY - dragState.y;
    const previousPoint = [dragState.x, dragState.y];
    const currentPoint = [localX, localY];
    dragState.x = localX;
    dragState.y = localY;
    if (dragState.kind === "gizmo") {
      applyGizmoDelta(dragState.handle, previousPoint, currentPoint);
      activeGizmoHandle = dragState.handle?.id || "";
    } else {
      applyJointToolDelta(data, selectedJoint, activeTool, dx, dy);
    }
    syncControlsFromData();
    commit();
    event.preventDefault();
    event.stopPropagation();
  };

  const handleViewportWheel = (event) => {
    data.view.zoom = clamp((Number(data.view.zoom) || 1) * (event.deltaY > 0 ? 0.92 : 1.087), 0.4, 2.4, 1);
    syncCameraFromView();
    writeSettings(node, widget, data);
    if (viewportMode !== "3d") {
      renderFallbackPreview(viewport, data, renderLayer);
    }
    refreshViewportOverlay();
    event.preventDefault();
    event.stopPropagation();
  };

  viewport.addEventListener("pointerdown", handleViewportPointerDown);
  viewport.addEventListener("pointermove", handleViewportPointerMove);
  viewport.addEventListener("wheel", handleViewportWheel, { passive: false });

  const endDrag = (event) => {
    clearViewportNavigation(event);
    dragState = null;
    activeGizmoHandle = "";
    const cursor = activeTool === "cursor" ? "default" : activeTool === "rotate" ? "alias" : activeTool === "orbit" ? "grab" : "crosshair";
    if (overlayCanvas) overlayCanvas.style.cursor = cursor;
    viewport.style.cursor = cursor;
    refreshViewportOverlay();
  };
  viewport.addEventListener("pointerup", endDrag);
  viewport.addEventListener("pointercancel", endDrag);
  viewport.addEventListener("pointerleave", endDrag);
  viewport.addEventListener("contextmenu", (event) => {
    event.preventDefault();
  });

  function syncCameraFromView() {
    if (!camera || !controls || !THREE) return;
    cameraSyncMute = true;
    const yaw = (data.view.yaw * Math.PI) / 180;
    const pitch = (data.view.pitch * Math.PI) / 180;
    const distance = 4.6 / Math.max(0.4, data.view.zoom);
    const target = new THREE.Vector3(Number(data.view.pan_x) || 0, 1.0 + (Number(data.view.pan_y) || 0), 0);
    const pos = new THREE.Vector3(
      distance * Math.sin(yaw) * Math.cos(pitch),
      1.0 + distance * Math.sin(pitch),
      distance * Math.cos(yaw) * Math.cos(pitch)
    ).add(target);
    camera.position.copy(pos);
    controls.target.copy(target);
    controls.update();
    cameraSyncMute = false;
    refreshViewportOverlay();
  }

  function syncSkeleton() {
    if (!rigRoot || !THREE) return;
    const points = computePosePoints(data);
    for (const [name, mesh] of jointMeshes.entries()) {
      const point = points[name];
      if (!point) continue;
      mesh.position.set(point[0], point[1], point[2]);
    }
    for (const entry of boneMeshes) {
      const p0 = points[entry.start];
      const p1 = points[entry.end];
      if (!p0 || !p1) continue;
      entry.line.geometry.setFromPoints([new THREE.Vector3(...p0), new THREE.Vector3(...p1)]);
    }
    if (silhouetteRig) {
      const display = sanitizeDisplaySettings(data.display);
      data.display = display;
      if (display.silhouette_source !== "custom_asset" && silhouetteRig.customPartsApplied) {
        restoreDefaultSilhouetteGeometry(silhouetteRig);
      } else if (display.silhouette_source === "custom_asset" && display.custom_asset_url && silhouetteRig.customAssetUrl !== display.custom_asset_url) {
        applyCustomSilhouetteAsset(silhouetteRig, THREE, display.custom_asset_url)
          .then(() => {
            renderer?.render(scene, camera);
            refreshViewportOverlay();
          })
          .catch((error) => {
            console.warn("Pose Studio custom silhouette load failed:", error);
          });
      }
      setPoseSilhouetteVariant(silhouetteRig, THREE, data.display?.silhouette_model || "female");
      updatePoseSilhouette(silhouetteRig, THREE, points);
      applyPoseDisplayMode(silhouetteRig, display.view_mode || "bones_only");
      const bonesVisible = (display.view_mode || "bones_only") !== "depth_mesh";
      for (const mesh of jointMeshes.values()) mesh.visible = bonesVisible;
      for (const entry of boneMeshes) entry.line.visible = bonesVisible;
    }
    renderer?.render(scene, camera);
    refreshViewportOverlay();
  }

  async function initThree() {
    const mods = await loadThree();
    const three = mods.THREE;
    scene = new three.Scene();
    scene.fog = new three.Fog(0x141830, 2.5, 11.0);

    camera = new three.PerspectiveCamera(42, 1, 0.01, 100);
    renderer = new three.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(window.devicePixelRatio || 1);
    renderer.setSize(viewport.clientWidth, viewport.clientHeight);
    if (renderLayer) {
      renderLayer.innerHTML = "";
      renderLayer.appendChild(renderer.domElement);
    }
    renderLayer?.addEventListener("pointerdown", handleViewportPointerDown);
    renderLayer?.addEventListener("pointermove", handleViewportPointerMove);
    renderLayer?.addEventListener("wheel", handleViewportWheel, { passive: false });
    renderer.domElement.addEventListener("pointerdown", handleViewportPointerDown);
    renderer.domElement.addEventListener("pointermove", handleViewportPointerMove);
    renderer.domElement.addEventListener("wheel", handleViewportWheel, { passive: false });
    const note = document.createElement("div");
    note.className = "mkr-viewport-note";
    note.textContent = "wheel zoom • right pan";
    viewport.appendChild(note);
    viewportMode = "3d";

    controls = new mods.OrbitControls(camera, renderer.domElement);
    controls.enabled = false;
    controls.enablePan = true;
    controls.enableZoom = true;
    controls.enableDamping = true;
    controls.minDistance = 2.0;
    controls.maxDistance = 8.0;
    controls.target.set(0, 1.0, 0);
    renderer.domElement.addEventListener("contextmenu", (event) => event.preventDefault());
    controls.update();

    controls.addEventListener("change", () => {
      if (cameraSyncMute) return;
      const offset = camera.position.clone().sub(controls.target);
      const distance = Math.max(0.001, offset.length());
      muteCommit = true;
      data.view.yaw = (Math.atan2(offset.x, offset.z) * 180) / Math.PI;
      data.view.pitch = (Math.asin(offset.y / distance) * 180) / Math.PI;
      data.view.zoom = clamp(4.6 / distance, 0.4, 2.4, 1);
      data.view.pan_x = clamp(Number(controls.target.x) || 0, -4, 4, 0);
      data.view.pan_y = clamp((Number(controls.target.y) || 1) - 1.0, -4, 4, 0);
      muteCommit = false;
      writeSettings(node, widget, data);
      refreshViewportOverlay();
    });

    scene.add(new three.AmbientLight(0xdce8f2, 0.78));
    const keyLight = new three.DirectionalLight(0xfbe8be, 1.05);
    keyLight.position.set(1.8, 3.2, 2.4);
    scene.add(keyLight);
    const rimLight = new three.DirectionalLight(0x89c6ff, 0.28);
    rimLight.position.set(-2.1, 2.2, -1.7);
    scene.add(rimLight);

    const floor = new three.Mesh(
      new three.CircleGeometry(3.3, 48),
      new three.MeshStandardMaterial({ color: 0x1a2030, roughness: 0.96, metalness: 0.02 })
    );
    floor.rotation.x = -Math.PI / 2;
    floor.position.y = -0.02;
    scene.add(floor);
    scene.add(new three.GridHelper(7, 28, 0x4a5b76, 0x263346));

    rigRoot = new three.Group();
    scene.add(rigRoot);
    silhouetteRig = createPoseSilhouette(three, data.display?.silhouette_model || "female");
    rigRoot.add(silhouetteRig.group);
    applyPoseDisplayMode(silhouetteRig, data.display?.view_mode || "bones_only");

    for (const name of Object.keys(computePosePoints(defaultSettings()))) {
      const baseRadius = jointDisplayRadius(name);
      const mesh = new three.Mesh(
        new three.SphereGeometry(Math.max(0.022, baseRadius * 0.0085), 16, 12),
        new three.MeshStandardMaterial({
          color: name.endsWith("_l") ? 0xb0f0d4 : name.endsWith("_r") ? 0x78bcff : 0xe1ecf1,
          roughness: 0.28,
          metalness: 0.04,
        })
      );
      jointMeshes.set(name, mesh);
      rigRoot.add(mesh);
    }

    for (const [start, end] of POSE_BONES) {
      const line = new three.Line(
        new three.BufferGeometry().setFromPoints([new three.Vector3(), new three.Vector3()]),
        new three.LineBasicMaterial({
          color: start.endsWith("_l") || end.endsWith("_l") ? 0xb0f0d4 : start.endsWith("_r") || end.endsWith("_r") ? 0x78bcff : 0xe1ecf1,
        })
      );
      boneMeshes.push({ start, end, line });
      rigRoot.add(line);
    }

    const resize = () => {
      if (disposed) return;
      const width = Math.max(120, viewport.clientWidth);
      const height = Math.max(120, viewport.clientHeight);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
      renderer.setSize(width, height);
    };
    resizeHandler = resize;
    window.addEventListener("resize", resizeHandler);
    if (typeof ResizeObserver !== "undefined") {
      resizeObserver = new ResizeObserver(() => resize());
      resizeObserver.observe(viewport);
    }
    resize();

    const loop = () => {
      if (disposed) return;
      rafId = requestAnimationFrame(loop);
      controls?.update();
      renderer?.render(scene, camera);
      refreshViewportOverlay();
    };
    loop();

    syncCameraFromView();
    syncSkeleton();
    setActiveTool(activeTool);
  }

  initThree().catch((error) => {
    console.warn("Pose Studio preview init failed:", error);
    viewportMode = "fallback";
    renderFallbackPreview(viewport, data, renderLayer);
    setActiveTool(activeTool);
  });

  renderFallbackPreview(viewport, data, renderLayer);
  commit();
  setActiveTool(activeTool);
  panel.__mkrPoseDispose = () => {
    disposed = true;
    if (rafId) {
      cancelAnimationFrame(rafId);
      rafId = 0;
    }
    if (resizeObserver) {
      resizeObserver.disconnect();
      resizeObserver = null;
    }
    if (resizeHandler) {
      window.removeEventListener("resize", resizeHandler);
      resizeHandler = null;
    }
    renderer?.dispose?.();
    controls?.dispose?.();
    renderLayer?.replaceChildren();
  };
  return panel;
}

function makeLauncher(node) {
  ensurePoseStudioStyles();
  const root = document.createElement("div");
  root.className = "mkr-pose-launcher";
  root.addEventListener("pointerdown", (event) => {
    event.stopPropagation();
  });
  root.addEventListener("mousedown", (event) => {
    event.stopPropagation();
  });
  root.addEventListener("click", (event) => {
    event.stopPropagation();
  });

  const head = document.createElement("div");
  head.className = "mkr-pose-launcher-head";
  const titleWrap = document.createElement("div");
  const kicker = document.createElement("div");
  kicker.className = "mkr-pose-launcher-kicker";
  kicker.textContent = "MKR Shift 3D";
  const title = document.createElement("div");
  title.className = "mkr-pose-launcher-title";
  title.textContent = "Pose Studio";
  titleWrap.appendChild(kicker);
  titleWrap.appendChild(title);
  const meta = document.createElement("div");
  meta.className = "mkr-pose-launcher-meta";
  head.appendChild(titleWrap);
  head.appendChild(meta);

  const summary = document.createElement("div");
  summary.className = "mkr-pose-launcher-summary";

  function makePill(labelText) {
    const pill = document.createElement("div");
    pill.className = "mkr-pose-launcher-pill";
    const label = document.createElement("div");
    label.className = "mkr-pose-launcher-pill-label";
    label.textContent = labelText;
    const value = document.createElement("div");
    value.className = "mkr-pose-launcher-pill-value";
    pill.appendChild(label);
    pill.appendChild(value);
    summary.appendChild(pill);
    return value;
  }

  const poseValue = makePill("Pose");
  const presetValue = makePill("Preset");
  const viewValue = makePill("View");

  const actions = document.createElement("div");
  actions.className = "mkr-pose-launcher-actions";
  const openButton = document.createElement("button");
  openButton.type = "button";
  openButton.className = "mkr-pose-launcher-btn";
  openButton.textContent = "Open Studio";
  const copyButton = document.createElement("button");
  copyButton.type = "button";
  copyButton.className = "mkr-pose-launcher-btn";
  copyButton.dataset.tone = "ghost";
  copyButton.textContent = "Copy JSON";
  actions.appendChild(openButton);
  actions.appendChild(copyButton);

  root.appendChild(head);
  root.appendChild(summary);
  root.appendChild(actions);

  const sync = () => {
    const { data } = ensureSettings(node);
    meta.textContent = `${Math.round(Number(node.size?.[0] || DEFAULT_NODE_WIDTH))}w • external studio`;
    poseValue.textContent = String(data.pose_name || "Neutral");
    presetValue.textContent = presetLabel(String(data.pose_preset || "neutral"));
    viewValue.textContent = `Y ${Math.round(Number(data.view?.yaw || 0))} / P ${Math.round(Number(data.view?.pitch || 0))}`;
  };

  const triggerOpenStudio = (event) => {
    event?.preventDefault?.();
    event?.stopPropagation?.();
    openPoseStudioModal(node);
  };
  openButton.addEventListener("pointerdown", triggerOpenStudio);
  openButton.addEventListener("click", triggerOpenStudio);
  copyButton.onclick = async () => {
    try {
      const { data } = ensureSettings(node);
      await navigator.clipboard.writeText(JSON.stringify(data, null, 2));
    } catch {
    }
  };

  root.__mkrSync = sync;
  sync();
  return root;
}

function openPoseStudioModal(node) {
  const existing = studioOverlays.get(node);
  if (existing?.backdrop?.isConnected) {
    existing.backdrop.style.display = "flex";
    return;
  }
  destroyStudioOverlay(node);
  const backdrop = document.createElement("div");
  backdrop.className = "mkr-pose-modal-backdrop";

  const shell = document.createElement("div");
  shell.className = "mkr-pose-modal-shell";
  backdrop.appendChild(shell);

  const head = document.createElement("div");
  head.className = "mkr-pose-modal-head";
  const headInfo = document.createElement("div");
  const title = document.createElement("div");
  title.className = "mkr-pose-modal-title";
  title.textContent = "Pose Studio";
  const subtitle = document.createElement("div");
  subtitle.className = "mkr-pose-modal-subtitle";
  subtitle.textContent = "External workspace for blocking poses without node layout constraints.";
  headInfo.appendChild(title);
  headInfo.appendChild(subtitle);
  const actions = document.createElement("div");
  actions.className = "mkr-pose-modal-actions";
  const syncButton = document.createElement("button");
  syncButton.type = "button";
  syncButton.className = "mkr-pose-modal-btn";
  syncButton.dataset.tone = "ghost";
  syncButton.textContent = "Sync";
  const closeButton = document.createElement("button");
  closeButton.type = "button";
  closeButton.className = "mkr-pose-modal-btn";
  closeButton.dataset.tone = "ghost";
  closeButton.textContent = "Close";
  actions.appendChild(syncButton);
  actions.appendChild(closeButton);
  head.appendChild(headInfo);
  head.appendChild(actions);

  const body = document.createElement("div");
  body.className = "mkr-pose-modal-body";
  const boot = document.createElement("div");
  boot.style.cssText = [
    "display:flex",
    "align-items:center",
    "justify-content:center",
    "height:100%",
    "color:#dbe4ec",
    "font:600 14px sans-serif",
    "background:linear-gradient(180deg, #181d38 0%, #131728 100%)",
  ].join(";");
  boot.textContent = "Opening Pose Studio...";
  body.appendChild(boot);
  shell.appendChild(head);
  shell.appendChild(body);

  const onKeyDown = (event) => {
    if (event.key === "Escape") {
      destroyStudioOverlay(node);
    }
  };
  document.addEventListener("keydown", onKeyDown, true);
  backdrop.addEventListener("mousedown", (event) => {
    if (event.target === backdrop) {
      destroyStudioOverlay(node);
    }
  });
  syncButton.onclick = () => {
    node.setDirtyCanvas?.(true, true);
    node.__mkrPoseLauncherRoot?.__mkrSync?.();
  };
  closeButton.onclick = () => destroyStudioOverlay(node);
  document.body.appendChild(backdrop);
  studioOverlays.set(node, { backdrop, panel: null, onKeyDown });

  requestAnimationFrame(() => {
    try {
      if (!backdrop.isConnected) return;
      const panel = makePanel(node, { externalStudio: true });
      body.replaceChildren(panel);
      const state = studioOverlays.get(node);
      if (state) {
        state.panel = panel;
      }
    } catch (error) {
      console.error("[MKRShift] Failed to open Pose Studio", error);
      const errorBox = document.createElement("div");
      errorBox.style.cssText = [
        "margin:20px",
        "padding:16px",
        "border-radius:14px",
        "border:1px solid rgba(217,87,59,0.4)",
        "background:rgba(255,95,67,0.12)",
        "color:#ffd7d1",
        "font:600 13px/1.45 sans-serif",
        "white-space:pre-wrap",
      ].join(";");
      const message = error instanceof Error
        ? `${error.name}: ${error.message}\n${String(error.stack || "").split("\n").slice(0, 4).join("\n")}`
        : String(error);
      errorBox.textContent = `Pose Studio failed to initialize.\n\n${message}`;
      body.replaceChildren(errorBox);
    }
  });
}

app.registerExtension({
  name: EXT,

  async nodeCreated(node) {
    if (node.comfyClass !== "MKRPoseStudio") return;

    if (!Array.isArray(node.size) || node.size.length < 2) {
      node.size = [DEFAULT_NODE_WIDTH, DEFAULT_NODE_HEIGHT];
    }
    node.size = [DEFAULT_NODE_WIDTH, DEFAULT_NODE_HEIGHT];
    node.__mkrPoseLockedSize = [node.size[0], node.size[1]];

    removeLegacyPoseInputs(node);
    removeLegacyPoseWidgets(node);
    normalizePoseWidgetTopology(node);

    const panel = makeLauncher(node);
    node.__mkrPoseLauncherRoot = panel;
    let domWidget = null;
    if (node.addDOMWidget) {
      domWidget = node.addDOMWidget("mkr_pose_studio_panel", "DOM", panel);
    } else {
      domWidget = node.addCustomWidget({
        name: "mkr_pose_studio_panel",
        type: "dom",
        draw: function () {},
        getHeight: function () {
          return LAUNCHER_WIDGET_HEIGHT;
        },
        getWidth: function () {
          return DEFAULT_NODE_WIDTH;
        },
        element: panel,
      });
    }

    [
      getWidget(node, "settings_json"),
      getWidget(node, "pose_name"),
      getWidget(node, "pose_preset"),
      getWidget(node, "mirror_mode"),
      getWidget(node, "capture_w"),
      getWidget(node, "capture_h"),
      getWidget(node, "character_state_json"),
      getWidget(node, "pose_from_image_mode"),
      getWidget(node, "pose_image_strength"),
    ].forEach(hideWidget);

    domWidget.computeSize = () => [DEFAULT_NODE_WIDTH - 18, LAUNCHER_WIDGET_HEIGHT];
    domWidget.computeLayoutSize = () => ({ minHeight: LAUNCHER_WIDGET_HEIGHT, maxHeight: LAUNCHER_WIDGET_HEIGHT, minWidth: 0 });
    if (domWidget.element?.style) {
      domWidget.element.style.width = `${DEFAULT_NODE_WIDTH - 18}px`;
      domWidget.element.style.height = `${LAUNCHER_WIDGET_HEIGHT}px`;
      domWidget.element.style.maxWidth = "100%";
      domWidget.element.style.overflow = "hidden";
      domWidget.element.style.boxSizing = "border-box";
    }
    trySetWidgetY(domWidget, 6);
    node.__mkrPoseMinSize = [DEFAULT_NODE_WIDTH, DEFAULT_NODE_HEIGHT];

    const originalResize = node.onResize;
    node.onResize = function onResizePoseStudio() {
      if (typeof originalResize === "function") originalResize.apply(this, arguments);
      const minSize = Array.isArray(this.__mkrPoseMinSize) ? this.__mkrPoseMinSize : [DEFAULT_NODE_WIDTH, DEFAULT_NODE_HEIGHT];
      this.__mkrPoseLockedSize = [minSize[0], minSize[1]];
      this.size = [this.__mkrPoseLockedSize[0], this.__mkrPoseLockedSize[1]];
      this.__mkrPoseLauncherRoot?.__mkrSync?.();
      this.setDirtyCanvas?.(true, true);
    };

    const originalExecuted = node.onExecuted;
    node.onExecuted = function onExecutedPoseStudio(message) {
      if (typeof originalExecuted === "function") originalExecuted.apply(this, arguments);
      if (Array.isArray(this.__mkrPoseLockedSize)) {
        this.size = [this.__mkrPoseLockedSize[0], this.__mkrPoseLockedSize[1]];
      }
      this.__mkrPoseLauncherRoot?.__mkrSync?.();
    };

    const originalRemoved = node.onRemoved;
    node.onRemoved = function onRemovedPoseStudio() {
      destroyStudioOverlay(this);
      if (typeof originalRemoved === "function") originalRemoved.apply(this, arguments);
    };

    const originalDblClick = node.onDblClick;
    node.onDblClick = function onDblClickPoseStudio(event, pos, graphCanvas) {
      openPoseStudioModal(this);
      if (typeof originalDblClick === "function") {
        return originalDblClick.apply(this, arguments);
      }
      return true;
    };

    node.setDirtyCanvas(true, true);
  },

  async afterConfigureGraph() {
    const nodes = app.graph?._nodes || [];
    for (const node of nodes) {
      if (node?.comfyClass !== "MKRPoseStudio") continue;
      removeLegacyPoseInputs(node);
      removeLegacyPoseWidgets(node);
      normalizePoseWidgetTopology(node);
      node.__mkrPoseLauncherRoot?.__mkrSync?.();
      node.setDirtyCanvas?.(true, true);
    }
  },
});
