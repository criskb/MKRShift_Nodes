from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


RefineMode = Literal["realtime", "quality"]


@dataclass
class LipRefineFaceConfig:
    """Configuration for ROI face refinement and compositing."""

    default_mode: RefineMode = "quality"

    roi_center_smoothing_realtime: float = 0.58
    roi_center_smoothing_quality: float = 0.32
    roi_size_smoothing_realtime: float = 0.65
    roi_size_smoothing_quality: float = 0.35

    lip_contact_strength_realtime: float = 0.48
    lip_contact_strength_quality: float = 0.72
    teeth_visibility_smoothing_realtime: float = 0.55
    teeth_visibility_smoothing_quality: float = 0.28

    blink_edge_smoothing_realtime: float = 0.42
    blink_edge_smoothing_quality: float = 0.24
    pupil_smoothing_realtime: float = 0.46
    pupil_smoothing_quality: float = 0.22

    mask_feather_px_realtime: float = 5.0
    mask_feather_px_quality: float = 10.0
    color_match_smoothing_realtime: float = 0.5
    color_match_smoothing_quality: float = 0.3


class LipRefineFace:
    """Refine a stabilized face ROI from base frames and audio-driven cues."""

    def __init__(self, config: LipRefineFaceConfig | None = None):
        self.config = config or LipRefineFaceConfig()

    def refine(
        self,
        base_frames: list[dict[str, Any]],
        audio_frames: list[dict[str, Any]],
        mode: RefineMode | None = None,
    ) -> list[dict[str, float | int | str]]:
        if not base_frames:
            return []

        active_mode = mode or self.config.default_mode
        cfg = self.config

        roi_center_alpha = self._mode_value(active_mode, cfg.roi_center_smoothing_realtime, cfg.roi_center_smoothing_quality)
        roi_size_alpha = self._mode_value(active_mode, cfg.roi_size_smoothing_realtime, cfg.roi_size_smoothing_quality)
        lip_contact_strength = self._mode_value(active_mode, cfg.lip_contact_strength_realtime, cfg.lip_contact_strength_quality)
        teeth_alpha = self._mode_value(active_mode, cfg.teeth_visibility_smoothing_realtime, cfg.teeth_visibility_smoothing_quality)
        blink_alpha = self._mode_value(active_mode, cfg.blink_edge_smoothing_realtime, cfg.blink_edge_smoothing_quality)
        pupil_alpha = self._mode_value(active_mode, cfg.pupil_smoothing_realtime, cfg.pupil_smoothing_quality)
        mask_feather = self._mode_value(active_mode, cfg.mask_feather_px_realtime, cfg.mask_feather_px_quality)
        color_alpha = self._mode_value(active_mode, cfg.color_match_smoothing_realtime, cfg.color_match_smoothing_quality)

        prev_center_x = 0.5
        prev_center_y = 0.45
        prev_size = 0.44
        prev_teeth_visibility = 0.0
        prev_eyelid_edge = 0.0
        prev_pupil_x = 0.0
        prev_pupil_y = 0.0
        prev_gain = 1.0

        out: list[dict[str, float | int | str]] = []
        for i, base in enumerate(base_frames):
            audio = audio_frames[i] if i < len(audio_frames) else {}
            frame_index = int(base.get("frame_index", audio.get("frame_index", i)))

            jaw_open = self._clamp(float(base.get("jaw_open", 0.0)), 0.0, 1.0)
            blink_l = self._clamp(float(base.get("blink_l", 0.0)), 0.0, 1.0)
            blink_r = self._clamp(float(base.get("blink_r", 0.0)), 0.0, 1.0)
            gaze_yaw = self._clamp(float(base.get("gaze_yaw", 0.0)), -1.0, 1.0)
            gaze_pitch = self._clamp(float(base.get("gaze_pitch", 0.0)), -1.0, 1.0)

            articulation = self._clamp(float(audio.get("articulation", 0.0)), 0.0, 1.0)
            energy = self._clamp(float(audio.get("energy", 0.0)), 0.0, 1.0)
            plosive = self._clamp(float(audio.get("plosive", 0.0)), 0.0, 1.0)

            target_center_x = self._clamp(0.5 + 0.03 * gaze_yaw, 0.35, 0.65)
            target_center_y = self._clamp(0.45 + 0.02 * gaze_pitch - 0.02 * jaw_open, 0.3, 0.65)
            target_size = self._clamp(0.42 + 0.15 * jaw_open + 0.05 * energy, 0.35, 0.72)

            prev_center_x = self._smooth(prev_center_x, target_center_x, roi_center_alpha)
            prev_center_y = self._smooth(prev_center_y, target_center_y, roi_center_alpha)
            prev_size = self._smooth(prev_size, target_size, roi_size_alpha)

            closure_boost = lip_contact_strength * (1.0 - articulation) * (0.4 + 0.6 * plosive)
            refined_jaw = self._clamp(jaw_open * (1.0 - 0.55 * closure_boost), 0.0, 1.0)
            mouth_press = self._clamp(float(base.get("mouth_press", base.get("mouth_press_l", 0.0))), 0.0, 1.0)
            refined_contact = self._clamp(mouth_press + closure_boost, 0.0, 1.0)

            target_teeth_visibility = self._clamp(refined_jaw * (1.0 - refined_contact), 0.0, 1.0)
            prev_teeth_visibility = self._smooth(prev_teeth_visibility, target_teeth_visibility, teeth_alpha)

            blink_mean = 0.5 * (blink_l + blink_r)
            target_eyelid_edge = self._clamp(0.25 + 0.75 * blink_mean, 0.0, 1.0)
            prev_eyelid_edge = self._smooth(prev_eyelid_edge, target_eyelid_edge, blink_alpha)

            target_pupil_x = self._clamp(0.8 * gaze_yaw, -1.0, 1.0)
            target_pupil_y = self._clamp(0.8 * gaze_pitch, -1.0, 1.0)
            prev_pupil_x = self._smooth(prev_pupil_x, target_pupil_x, pupil_alpha)
            prev_pupil_y = self._smooth(prev_pupil_y, target_pupil_y, pupil_alpha)

            target_gain = self._clamp(1.0 + 0.08 * (energy - 0.5), 0.9, 1.1)
            prev_gain = self._smooth(prev_gain, target_gain, color_alpha)

            out.append(
                {
                    "frame_index": frame_index,
                    "mode": active_mode,
                    "realtime_mode": 1 if active_mode == "realtime" else 0,
                    "quality_mode": 1 if active_mode == "quality" else 0,
                    "roi_center_x": prev_center_x,
                    "roi_center_y": prev_center_y,
                    "roi_size": prev_size,
                    "refined_jaw_open": refined_jaw,
                    "lip_contact": refined_contact,
                    "teeth_visibility": prev_teeth_visibility,
                    "eyelid_edge_fidelity": prev_eyelid_edge,
                    "pupil_x": prev_pupil_x,
                    "pupil_y": prev_pupil_y,
                    "composite_mask_feather_px": mask_feather,
                    "composite_color_gain": prev_gain,
                }
            )

        return out

    @staticmethod
    def _mode_value(mode: RefineMode, realtime_value: float, quality_value: float) -> float:
        return realtime_value if mode == "realtime" else quality_value

    @staticmethod
    def _smooth(previous: float, target: float, alpha: float) -> float:
        return previous + alpha * (target - previous)

    @staticmethod
    def _clamp(value: float, low: float, high: float) -> float:
        return max(low, min(high, value))
