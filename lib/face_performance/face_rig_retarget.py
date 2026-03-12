from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FaceRigRetargetConfig:
    """Configuration for neutral rig selection and facial-motion retargeting."""

    landmark_order: tuple[str, ...] = (
        "left_eye",
        "right_eye",
        "nose",
        "mouth_left",
        "mouth_right",
        "upper_lip",
        "lower_lip",
        "jaw",
    )
    canonical_landmarks: dict[str, tuple[float, float]] = field(
        default_factory=lambda: {
            "left_eye": (0.38, 0.36),
            "right_eye": (0.62, 0.36),
            "nose": (0.50, 0.48),
            "mouth_left": (0.43, 0.62),
            "mouth_right": (0.57, 0.62),
            "upper_lip": (0.50, 0.60),
            "lower_lip": (0.50, 0.64),
            "jaw": (0.50, 0.78),
        }
    )

    jaw_open_scale: float = 0.11
    lip_open_scale: float = 0.06
    lip_wide_scale: float = 0.05
    blink_scale: float = 0.02

    default_intensity: float = 1.0
    max_intensity: float = 2.0
    control_smoothing_alpha: float = 0.25


class FaceRigRetarget:
    """Apply facial motion deltas on top of a neutral identity rig."""

    _REQUIRED_EXPRESSIVE_POINTS = (
        "left_eye",
        "right_eye",
        "mouth_left",
        "mouth_right",
        "upper_lip",
        "lower_lip",
        "jaw",
    )

    def __init__(self, config: FaceRigRetargetConfig | None = None):
        self.config = config or FaceRigRetargetConfig()

    def build_neutral_rig(
        self,
        reference_landmarks: dict[str, tuple[float, float]] | None = None,
        image_size: tuple[int, int] | None = None,
    ) -> dict[str, Any]:
        normalized_reference = self._normalize_reference_landmarks(reference_landmarks, image_size)
        base = dict(self.config.canonical_landmarks)
        base.update(normalized_reference)

        points = {name: tuple(base[name]) for name in self.config.landmark_order if name in base}
        mode = "reference" if reference_landmarks else "canonical"

        expressive_count = sum(1 for key in self._REQUIRED_EXPRESSIVE_POINTS if key in normalized_reference)
        expressive_completeness = expressive_count / len(self._REQUIRED_EXPRESSIVE_POINTS)

        missing_required = [key for key in self._REQUIRED_EXPRESSIVE_POINTS if key not in normalized_reference]

        return {
            "identity_mode": mode,
            "landmarks": points,
            "landmark_order": list(self.config.landmark_order),
            "expressive_completeness": expressive_completeness,
            "source_space": "pixel" if image_size is not None else "normalized",
            "missing_reference_points": missing_required if mode == "reference" else [],
        }

    def apply_deltas(
        self,
        neutral_rig: dict[str, Any],
        motion_frames: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        base_landmarks = dict(self.config.canonical_landmarks)
        base_landmarks.update(neutral_rig.get("landmarks", {}))

        order = [name for name in neutral_rig.get("landmark_order", self.config.landmark_order) if name in base_landmarks]
        identity_mode = str(neutral_rig.get("identity_mode", "canonical"))

        if not motion_frames or not order:
            return []

        out: list[dict[str, Any]] = []
        prev_controls = {"jaw_open": 0.0, "lip_open": 0.0, "lip_wide": 0.0, "blink": 0.0}

        for i, frame in enumerate(motion_frames):
            intensity = self._clamp(float(frame.get("intensity", self.config.default_intensity)), 0.0, self.config.max_intensity)
            alpha = self._clamp(float(frame.get("smoothing", self.config.control_smoothing_alpha)), 0.0, 0.95)
            raw_controls = {
                "jaw_open": self._clamp(float(frame.get("jaw_open", 0.0)), 0.0, 1.0),
                "lip_open": self._clamp(float(frame.get("lip_open", 0.0)), 0.0, 1.0),
                "lip_wide": self._clamp(float(frame.get("lip_wide", 0.0)), -1.0, 1.0),
                "blink": 0.5 * self._clamp(float(frame.get("blink_l", 0.0)), 0.0, 1.0)
                + 0.5 * self._clamp(float(frame.get("blink_r", 0.0)), 0.0, 1.0),
            }

            controls = {
                key: self._low_pass(prev_controls[key], value, alpha)
                for key, value in raw_controls.items()
            }
            prev_controls = controls

            posed = {name: [*base_landmarks[name]] for name in order}

            self._adjust_point_y(posed, "jaw", controls["jaw_open"] * self.config.jaw_open_scale * intensity)
            self._adjust_point_y(posed, "upper_lip", -controls["lip_open"] * self.config.lip_open_scale * 0.5 * intensity)
            self._adjust_point_y(posed, "lower_lip", controls["lip_open"] * self.config.lip_open_scale * intensity)
            self._adjust_point_x(posed, "mouth_left", -controls["lip_wide"] * self.config.lip_wide_scale * intensity)
            self._adjust_point_x(posed, "mouth_right", controls["lip_wide"] * self.config.lip_wide_scale * intensity)
            self._adjust_point_y(posed, "left_eye", controls["blink"] * self.config.blink_scale * intensity)
            self._adjust_point_y(posed, "right_eye", controls["blink"] * self.config.blink_scale * intensity)

            clamped_landmarks = {
                name: (self._clamp(point[0], 0.0, 1.0), self._clamp(point[1], 0.0, 1.0))
                for name, point in posed.items()
            }

            frame_index = int(frame.get("frame_index", i))
            out.append(
                {
                    "frame_index": frame_index,
                    "identity_mode": identity_mode,
                    "landmarks": clamped_landmarks,
                    "landmarks_2d": [[clamped_landmarks[name][0], clamped_landmarks[name][1]] for name in order],
                    "motion": {
                        **controls,
                        "intensity": intensity,
                        "smoothing": alpha,
                    },
                }
            )

        return out

    @staticmethod
    def _adjust_point_x(points: dict[str, list[float]], key: str, delta: float) -> None:
        if key in points:
            points[key][0] += delta

    @staticmethod
    def _adjust_point_y(points: dict[str, list[float]], key: str, delta: float) -> None:
        if key in points:
            points[key][1] += delta

    @staticmethod
    def _clamp(value: float, low: float, high: float) -> float:
        return max(low, min(high, value))

    @staticmethod
    def _low_pass(previous: float, target: float, alpha: float) -> float:
        return previous + (1.0 - alpha) * (target - previous)

    @staticmethod
    def _normalize_reference_landmarks(
        reference_landmarks: dict[str, tuple[float, float]] | None,
        image_size: tuple[int, int] | None,
    ) -> dict[str, tuple[float, float]]:
        if not reference_landmarks:
            return {}

        if image_size is None:
            return {
                key: (
                    FaceRigRetarget._clamp(float(value[0]), 0.0, 1.0),
                    FaceRigRetarget._clamp(float(value[1]), 0.0, 1.0),
                )
                for key, value in reference_landmarks.items()
            }

        width, height = image_size
        width = max(int(width), 1)
        height = max(int(height), 1)
        return {
            key: (
                FaceRigRetarget._clamp(float(value[0]) / width, 0.0, 1.0),
                FaceRigRetarget._clamp(float(value[1]) / height, 0.0, 1.0),
            )
            for key, value in reference_landmarks.items()
        }
