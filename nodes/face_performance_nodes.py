from __future__ import annotations

from dataclasses import asdict
import json
from json import JSONDecodeError
from typing import Any

from ..categories import PERFORMANCE_ANALYSIS, PERFORMANCE_FACE, PERFORMANCE_POSE
from ..lib.face_performance import (
    ClipMetrics,
    CombinePoseData,
    CombinePoseDataConfig,
    EyeMotionSynth,
    EyeMotionSynthConfig,
    FaceRigRetarget,
    FaceRigRetargetConfig,
    LipRefineFace,
    LipRefineFaceConfig,
    NodeEvaluationUtility,
    RegressionThresholds,
)


def _safe_json_load(raw: str, default: Any) -> Any:
    try:
        return json.loads(raw or "")
    except JSONDecodeError:
        return default


def _json_dict(raw: str) -> dict[str, Any]:
    value = _safe_json_load(raw, {})
    return value if isinstance(value, dict) else {}


def _json_frames(raw: str) -> list[dict[str, Any]]:
    value = _safe_json_load(raw, [])
    if not isinstance(value, list):
        return []
    return [frame for frame in value if isinstance(frame, dict)]


def _json_text(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=True)


def _bool_value(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"1", "true", "yes", "on"}:
            return True
        if text in {"0", "false", "no", "off", ""}:
            return False
    return default


def _float_value(value: Any, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _int_value(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _coerce_like(value: Any, template: Any) -> Any:
    if isinstance(template, bool):
        return _bool_value(value, template)
    if isinstance(template, int) and not isinstance(template, bool):
        return _int_value(value, template)
    if isinstance(template, float):
        return _float_value(value, template)
    if isinstance(template, str):
        return str(value)
    if isinstance(template, tuple):
        if not isinstance(value, (list, tuple)):
            return template
        if not template:
            return tuple(value)
        sample = template[0]
        return tuple(_coerce_like(item, sample) for item in value)
    if isinstance(template, dict):
        if not isinstance(value, dict):
            return template
        if not template:
            return dict(value)
        sample_key, sample_value = next(iter(template.items()))
        out: dict[Any, Any] = {}
        for raw_key, raw_value in value.items():
            key = str(raw_key) if isinstance(sample_key, str) else raw_key
            out[key] = _coerce_like(raw_value, sample_value)
        return out
    return value


def _apply_settings(config: Any, settings_json: str) -> Any:
    settings = _json_dict(settings_json)
    for key, value in settings.items():
        if not hasattr(config, key):
            continue
        current = getattr(config, key)
        setattr(config, key, _coerce_like(value, current))
    return config


def _two_float_tuple(value: Any, default: tuple[float, float]) -> tuple[float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return default
    return (_float_value(value[0], default[0]), _float_value(value[1], default[1]))


def _normalize_landmarks(payload: Any) -> dict[str, tuple[float, float]]:
    if not isinstance(payload, dict):
        return {}

    out: dict[str, tuple[float, float]] = {}
    for key, value in payload.items():
        if not isinstance(key, str):
            continue
        if isinstance(value, (list, tuple)) and len(value) == 2:
            try:
                out[key] = (float(value[0]), float(value[1]))
            except (TypeError, ValueError):
                continue
    return out


def _validate_json_shape(raw: str, expected: type[list[Any]] | type[dict[str, Any]], label: str) -> bool | str:
    fallback = "[]" if expected is list else "{}"
    try:
        payload = json.loads(raw or fallback)
    except JSONDecodeError:
        return f"{label} must be valid JSON"
    if not isinstance(payload, expected):
        kind = "array" if expected is list else "object"
        return f"{label} must decode to a JSON {kind}"
    return True


def _build_eye_motion_config(
    target_fps: int,
    mean_blink_interval_s: float,
    blink_interval_jitter_s: float,
    include_squint: bool,
    settings_json: str,
) -> EyeMotionSynthConfig:
    config = EyeMotionSynthConfig(
        target_fps=max(1, int(target_fps)),
        mean_blink_interval_s=max(0.5, float(mean_blink_interval_s)),
        blink_interval_jitter_s=max(0.0, float(blink_interval_jitter_s)),
        include_squint=bool(include_squint),
    )
    _apply_settings(config, settings_json)
    config.target_fps = max(1, _int_value(config.target_fps, 60))
    config.mean_blink_interval_s = max(0.5, _float_value(config.mean_blink_interval_s, 4.2))
    config.blink_interval_jitter_s = max(0.0, _float_value(config.blink_interval_jitter_s, 1.6))
    config.blink_duration_s = max(0.02, _float_value(config.blink_duration_s, 0.16))
    config.blink_peak_hold_s = max(0.0, _float_value(config.blink_peak_hold_s, 0.03))
    config.micro_saccade_interval_s = _two_float_tuple(config.micro_saccade_interval_s, (0.08, 0.28))
    config.gaze_clamp = _two_float_tuple(config.gaze_clamp, (-1.0, 1.0))
    config.brow_inner_up_range = _two_float_tuple(config.brow_inner_up_range, (0.0, 1.0))
    config.brow_outer_up_range = _two_float_tuple(config.brow_outer_up_range, (0.0, 1.0))
    config.eyelid_open_range = _two_float_tuple(config.eyelid_open_range, (0.0, 1.0))
    config.cheek_raise_range = _two_float_tuple(config.cheek_raise_range, (0.0, 1.0))
    config.nasolabial_tension_range = _two_float_tuple(config.nasolabial_tension_range, (0.0, 1.0))
    config.expr_confidence_range = _two_float_tuple(config.expr_confidence_range, (0.0, 1.0))
    config.include_squint = _bool_value(config.include_squint, include_squint)
    return config


def _build_lip_refine_config(mode: str, settings_json: str) -> LipRefineFaceConfig:
    config = LipRefineFaceConfig(default_mode="realtime" if mode == "realtime" else "quality")
    _apply_settings(config, settings_json)
    config.default_mode = "realtime" if str(config.default_mode).strip().lower() == "realtime" else "quality"
    config.mask_feather_px_realtime = max(0.0, _float_value(config.mask_feather_px_realtime, 5.0))
    config.mask_feather_px_quality = max(0.0, _float_value(config.mask_feather_px_quality, 10.0))
    return config


def _build_face_rig_config(settings_json: str) -> FaceRigRetargetConfig:
    config = FaceRigRetargetConfig()
    _apply_settings(config, settings_json)
    config.landmark_order = tuple(str(item) for item in config.landmark_order) if config.landmark_order else FaceRigRetargetConfig().landmark_order
    config.canonical_landmarks = _normalize_landmarks(config.canonical_landmarks) or FaceRigRetargetConfig().canonical_landmarks
    config.jaw_open_scale = max(0.0, _float_value(config.jaw_open_scale, 0.11))
    config.lip_open_scale = max(0.0, _float_value(config.lip_open_scale, 0.06))
    config.lip_wide_scale = max(0.0, _float_value(config.lip_wide_scale, 0.05))
    config.blink_scale = max(0.0, _float_value(config.blink_scale, 0.02))
    config.default_intensity = max(0.0, _float_value(config.default_intensity, 1.0))
    config.max_intensity = max(config.default_intensity, _float_value(config.max_intensity, 2.0))
    config.control_smoothing_alpha = min(0.95, max(0.0, _float_value(config.control_smoothing_alpha, 0.25)))
    return config


def _build_pose_merge_config(max_delta_per_frame: float, divergence_threshold: float, settings_json: str) -> CombinePoseDataConfig:
    config = CombinePoseDataConfig(
        max_delta_per_frame=max(0.0, float(max_delta_per_frame)),
        divergence_threshold=max(0.0, float(divergence_threshold)),
    )
    _apply_settings(config, settings_json)
    config.max_delta_per_frame = max(0.0, _float_value(config.max_delta_per_frame, max_delta_per_frame))
    config.divergence_threshold = max(0.0, _float_value(config.divergence_threshold, divergence_threshold))
    config.head_low_pass_alpha = min(1.0, max(0.0, _float_value(config.head_low_pass_alpha, 0.25)))
    config.lips_alpha_min = min(1.0, max(0.0, _float_value(config.lips_alpha_min, 0.18)))
    config.lips_alpha_max = min(1.0, max(config.lips_alpha_min, _float_value(config.lips_alpha_max, 0.72)))
    config.lips_adaptive_scale = max(0.0, _float_value(config.lips_adaptive_scale, 2.0))
    config.eyes_base_alpha = min(1.0, max(0.0, _float_value(config.eyes_base_alpha, 0.2)))
    config.eyes_event_alpha = min(1.0, max(0.0, _float_value(config.eyes_event_alpha, 0.85)))
    config.eyes_event_threshold = max(0.0, _float_value(config.eyes_event_threshold, 0.18))
    config.head_offset_bounds = {str(key): abs(_float_value(value, 0.25)) for key, value in dict(config.head_offset_bounds).items()}
    return config


def _build_thresholds(thresholds_json: str) -> RegressionThresholds:
    thresholds = RegressionThresholds()
    _apply_settings(thresholds, thresholds_json)
    thresholds.max_abs_lip_audio_sync_lag_frames = max(0, _int_value(thresholds.max_abs_lip_audio_sync_lag_frames, 4))
    thresholds.min_lip_audio_sync_correlation = min(1.0, max(0.0, _float_value(thresholds.min_lip_audio_sync_correlation, 0.45)))
    thresholds.max_landmark_velocity_outliers = max(0, _int_value(thresholds.max_landmark_velocity_outliers, 18))
    thresholds.max_landmark_acceleration_outliers = max(0, _int_value(thresholds.max_landmark_acceleration_outliers, 24))
    thresholds.max_pose_jitter_score = max(0.0, _float_value(thresholds.max_pose_jitter_score, 0.055))
    blink_range = _two_float_tuple(thresholds.blink_rate_per_minute_range, (6.0, 45.0))
    thresholds.blink_rate_per_minute_range = (min(blink_range), max(blink_range))
    return thresholds


class MKRFacePerformanceEyeMotion:
    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        return {
            "required": {
                "audio_frames_json": ("STRING", {"default": "[]", "multiline": True}),
                "seed": ("INT", {"default": 7, "min": -1, "max": 2147483647}),
                "target_fps": ("INT", {"default": 60, "min": 1, "max": 240}),
                "mean_blink_interval_s": ("FLOAT", {"default": 4.2, "min": 0.5, "max": 30.0, "step": 0.05}),
                "blink_interval_jitter_s": ("FLOAT", {"default": 1.6, "min": 0.0, "max": 10.0, "step": 0.05}),
                "include_squint": ("BOOLEAN", {"default": False}),
                "settings_json": ("STRING", {"default": "{}", "multiline": True}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("eye_frames_json", "summary")
    FUNCTION = "run"
    CATEGORY = PERFORMANCE_FACE

    @classmethod
    def VALIDATE_INPUTS(
        cls,
        audio_frames_json: str,
        seed: int,
        target_fps: int,
        mean_blink_interval_s: float,
        blink_interval_jitter_s: float,
        include_squint: bool,
        settings_json: str,
    ) -> bool | str:
        return _validate_json_shape(audio_frames_json, list, "audio_frames_json")

    def run(
        self,
        audio_frames_json: str,
        seed: int = 7,
        target_fps: int = 60,
        mean_blink_interval_s: float = 4.2,
        blink_interval_jitter_s: float = 1.6,
        include_squint: bool = False,
        settings_json: str = "{}",
    ) -> tuple[str, str]:
        audio_frames = _json_frames(audio_frames_json)
        config = _build_eye_motion_config(
            target_fps=target_fps,
            mean_blink_interval_s=mean_blink_interval_s,
            blink_interval_jitter_s=blink_interval_jitter_s,
            include_squint=include_squint,
            settings_json=settings_json,
        )
        motion = EyeMotionSynth(config=config, seed=None if int(seed) < 0 else int(seed)).synthesize(audio_frames)
        summary = f"Face performance eye motion: {len(motion)} frames at {config.target_fps} fps, squint={'on' if config.include_squint else 'off'}"
        return (_json_text(motion), summary)


class MKRFacePerformanceLipRefine:
    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        return {
            "required": {
                "base_frames_json": ("STRING", {"default": "[]", "multiline": True}),
                "audio_frames_json": ("STRING", {"default": "[]", "multiline": True}),
                "mode": (["quality", "realtime"],),
                "settings_json": ("STRING", {"default": "{}", "multiline": True}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("refined_frames_json", "summary")
    FUNCTION = "run"
    CATEGORY = PERFORMANCE_FACE

    @classmethod
    def VALIDATE_INPUTS(cls, base_frames_json: str, audio_frames_json: str, mode: str, settings_json: str) -> bool | str:
        base_check = _validate_json_shape(base_frames_json, list, "base_frames_json")
        if base_check is not True:
            return base_check
        return _validate_json_shape(audio_frames_json, list, "audio_frames_json")

    def run(
        self,
        base_frames_json: str,
        audio_frames_json: str,
        mode: str = "quality",
        settings_json: str = "{}",
    ) -> tuple[str, str]:
        base_frames = _json_frames(base_frames_json)
        audio_frames = _json_frames(audio_frames_json)
        config = _build_lip_refine_config(mode=mode, settings_json=settings_json)
        refined = LipRefineFace(config=config).refine(base_frames, audio_frames, mode=config.default_mode)
        summary = f"Face performance lip refine: {len(refined)} frames in {config.default_mode} mode"
        return (_json_text(refined), summary)


class MKRFacePerformanceRigBuildNeutral:
    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        return {
            "required": {
                "reference_landmarks_json": ("STRING", {"default": "{}", "multiline": True}),
                "image_width": ("INT", {"default": 0, "min": 0, "max": 16384}),
                "image_height": ("INT", {"default": 0, "min": 0, "max": 16384}),
                "settings_json": ("STRING", {"default": "{}", "multiline": True}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("neutral_rig_json", "summary")
    FUNCTION = "build"
    CATEGORY = PERFORMANCE_POSE

    @classmethod
    def VALIDATE_INPUTS(
        cls,
        reference_landmarks_json: str,
        image_width: int,
        image_height: int,
        settings_json: str,
    ) -> bool | str:
        if image_width < 0 or image_height < 0:
            return "image_width and image_height must be non-negative"
        return _validate_json_shape(reference_landmarks_json, dict, "reference_landmarks_json")

    def build(
        self,
        reference_landmarks_json: str,
        image_width: int = 0,
        image_height: int = 0,
        settings_json: str = "{}",
    ) -> tuple[str, str]:
        reference = _normalize_landmarks(_json_dict(reference_landmarks_json))
        image_size = (image_width, image_height) if image_width > 0 and image_height > 0 else None
        rig = FaceRigRetarget(config=_build_face_rig_config(settings_json)).build_neutral_rig(
            reference_landmarks=reference,
            image_size=image_size,
        )
        summary = (
            f"Face performance neutral rig: {rig['identity_mode']} mode, "
            f"{len(rig.get('landmarks', {}))} landmarks, completeness={rig.get('expressive_completeness', 0.0):.2f}"
        )
        return (_json_text(rig), summary)


class MKRFacePerformanceRigApplyDeltas:
    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        return {
            "required": {
                "neutral_rig_json": ("STRING", {"default": "{}", "multiline": True}),
                "motion_frames_json": ("STRING", {"default": "[]", "multiline": True}),
                "settings_json": ("STRING", {"default": "{}", "multiline": True}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("retargeted_frames_json", "summary")
    FUNCTION = "retarget"
    CATEGORY = PERFORMANCE_POSE

    @classmethod
    def VALIDATE_INPUTS(cls, neutral_rig_json: str, motion_frames_json: str, settings_json: str) -> bool | str:
        neutral_check = _validate_json_shape(neutral_rig_json, dict, "neutral_rig_json")
        if neutral_check is not True:
            return neutral_check
        return _validate_json_shape(motion_frames_json, list, "motion_frames_json")

    def retarget(
        self,
        neutral_rig_json: str,
        motion_frames_json: str,
        settings_json: str = "{}",
    ) -> tuple[str, str]:
        neutral_rig = _json_dict(neutral_rig_json)
        motion_frames = _json_frames(motion_frames_json)
        frames = FaceRigRetarget(config=_build_face_rig_config(settings_json)).apply_deltas(
            neutral_rig=neutral_rig,
            motion_frames=motion_frames,
        )
        identity_mode = neutral_rig.get("identity_mode", "canonical")
        summary = f"Face performance rig retarget: {len(frames)} frames in {identity_mode} identity mode"
        return (_json_text(frames), summary)


class MKRFacePerformancePoseMerge:
    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        return {
            "required": {
                "body_frames_json": ("STRING", {"default": "[]", "multiline": True}),
                "face_frames_json": ("STRING", {"default": "[]", "multiline": True}),
                "facial_frames_json": ("STRING", {"default": "[]", "multiline": True}),
                "max_delta_per_frame": ("FLOAT", {"default": 0.22, "min": 0.0, "max": 2.0, "step": 0.01}),
                "divergence_threshold": ("FLOAT", {"default": 0.4, "min": 0.0, "max": 4.0, "step": 0.01}),
                "settings_json": ("STRING", {"default": "{}", "multiline": True}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("pose_frames_json", "diagnostics_json", "summary")
    FUNCTION = "run"
    CATEGORY = PERFORMANCE_POSE

    @classmethod
    def VALIDATE_INPUTS(
        cls,
        body_frames_json: str,
        face_frames_json: str,
        facial_frames_json: str,
        max_delta_per_frame: float,
        divergence_threshold: float,
        settings_json: str,
    ) -> bool | str:
        for label, raw in (
            ("body_frames_json", body_frames_json),
            ("face_frames_json", face_frames_json),
            ("facial_frames_json", facial_frames_json),
        ):
            result = _validate_json_shape(raw, list, label)
            if result is not True:
                return result
        return True

    def run(
        self,
        body_frames_json: str,
        face_frames_json: str,
        facial_frames_json: str,
        max_delta_per_frame: float = 0.22,
        divergence_threshold: float = 0.4,
        settings_json: str = "{}",
    ) -> tuple[str, str, str]:
        combiner = CombinePoseData(
            config=_build_pose_merge_config(
                max_delta_per_frame=max_delta_per_frame,
                divergence_threshold=divergence_threshold,
                settings_json=settings_json,
            )
        )
        pose_frames = combiner.combine(
            body_frames=_json_frames(body_frames_json),
            face_frames=_json_frames(face_frames_json),
            facial_frames=_json_frames(facial_frames_json),
        )
        diagnostics = combiner.last_diagnostics
        summary = f"Face performance pose merge: {len(pose_frames)} frames with {len(diagnostics)} diagnostics"
        return (_json_text(pose_frames), _json_text(diagnostics), summary)


class MKRFacePerformanceEvaluate:
    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        return {
            "required": {
                "clip_id": ("STRING", {"default": "clip_alpha", "multiline": False}),
                "audio_frames_json": ("STRING", {"default": "[]", "multiline": True}),
                "refined_frames_json": ("STRING", {"default": "[]", "multiline": True}),
                "eye_frames_json": ("STRING", {"default": "[]", "multiline": True}),
                "pose_frames_json": ("STRING", {"default": "[]", "multiline": True}),
                "fps": ("INT", {"default": 60, "min": 1, "max": 240}),
                "thresholds_json": ("STRING", {"default": "{}", "multiline": True}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING", "INT", "FLOAT", "FLOAT", "STRING")
    RETURN_NAMES = ("metrics_json", "failures_json", "lag_frames", "blink_rate_per_minute", "pose_jitter_score", "summary")
    FUNCTION = "run"
    CATEGORY = PERFORMANCE_ANALYSIS

    @classmethod
    def VALIDATE_INPUTS(
        cls,
        clip_id: str,
        audio_frames_json: str,
        refined_frames_json: str,
        eye_frames_json: str,
        pose_frames_json: str,
        fps: int,
        thresholds_json: str,
    ) -> bool | str:
        for label, raw in (
            ("audio_frames_json", audio_frames_json),
            ("refined_frames_json", refined_frames_json),
            ("eye_frames_json", eye_frames_json),
            ("pose_frames_json", pose_frames_json),
        ):
            result = _validate_json_shape(raw, list, label)
            if result is not True:
                return result
        return _validate_json_shape(thresholds_json, dict, "thresholds_json")

    def run(
        self,
        clip_id: str,
        audio_frames_json: str,
        refined_frames_json: str,
        eye_frames_json: str,
        pose_frames_json: str,
        fps: int = 60,
        thresholds_json: str = "{}",
    ) -> tuple[str, str, int, float, float, str]:
        metrics: ClipMetrics = NodeEvaluationUtility(fps=max(1, int(fps))).evaluate_clip(
            clip_id=str(clip_id or "clip"),
            audio_frames=_json_frames(audio_frames_json),
            refined_frames=_json_frames(refined_frames_json),
            eye_frames=_json_frames(eye_frames_json),
            pose_frames=_json_frames(pose_frames_json),
        )
        thresholds = _build_thresholds(thresholds_json)
        failures = NodeEvaluationUtility.check_thresholds([metrics], thresholds)
        summary = (
            f"Face performance evaluation: lag={metrics.lip_audio_sync_lag_frames}f, "
            f"blink_rate={metrics.blink_rate_per_minute:.2f}/min, "
            f"pose_jitter={metrics.pose_jitter_score:.4f}, failures={len(failures)}"
        )
        return (
            _json_text(asdict(metrics)),
            _json_text(failures),
            int(metrics.lip_audio_sync_lag_frames),
            float(metrics.blink_rate_per_minute),
            float(metrics.pose_jitter_score),
            summary,
        )


# Backward-compatible Python aliases for the initial Supersync naming.
MKRSuperSyncEyeMotionSynth = MKRFacePerformanceEyeMotion
MKRSuperSyncLipRefineFace = MKRFacePerformanceLipRefine
MKRSuperSyncFaceRigBuildNeutral = MKRFacePerformanceRigBuildNeutral
MKRSuperSyncFaceRigApplyDeltas = MKRFacePerformanceRigApplyDeltas
MKRSuperSyncCombinePoseData = MKRFacePerformancePoseMerge
MKRSuperSyncEvaluateClip = MKRFacePerformanceEvaluate
