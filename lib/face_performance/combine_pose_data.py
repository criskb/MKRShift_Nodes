from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CombinePoseDataConfig:
    head_channels: tuple[str, ...] = ("head_yaw", "head_pitch", "head_roll", "neck_yaw", "neck_pitch", "neck_roll")
    lips_channels: tuple[str, ...] = (
        "jaw_open",
        "mouth_smile_l",
        "mouth_smile_r",
        "mouth_frown_l",
        "mouth_frown_r",
        "mouth_pucker",
        "mouth_funnel",
        "mouth_press_l",
        "mouth_press_r",
    )
    eyes_channels: tuple[str, ...] = (
        "blink_l",
        "blink_r",
        "eyelid_open_l",
        "eyelid_open_r",
        "look_up_l",
        "look_up_r",
        "look_down_l",
        "look_down_r",
    )
    brow_channels: tuple[str, ...] = ("brow_inner_up", "brow_outer_up_l", "brow_outer_up_r", "brow_down_l", "brow_down_r")

    body_confidence_key: str = "confidence"
    face_confidence_key: str = "confidence"
    facial_confidence_key: str = "expr_confidence"

    head_low_pass_alpha: float = 0.25
    lips_alpha_min: float = 0.18
    lips_alpha_max: float = 0.72
    lips_adaptive_scale: float = 2.0
    eyes_base_alpha: float = 0.2
    eyes_event_alpha: float = 0.85
    eyes_event_threshold: float = 0.18

    max_delta_per_frame: float = 0.22
    head_offset_bounds: dict[str, float] = field(
        default_factory=lambda: {
            "head_yaw": 0.35,
            "head_pitch": 0.28,
            "head_roll": 0.3,
            "neck_yaw": 0.24,
            "neck_pitch": 0.24,
            "neck_roll": 0.22,
        }
    )
    divergence_threshold: float = 0.4


class CombinePoseData:
    """Merge body/face/facial streams with confidence-aware channel priority and temporal stabilization."""

    def __init__(self, config: CombinePoseDataConfig | None = None):
        self.config = config or CombinePoseDataConfig()
        self.last_diagnostics: list[dict[str, Any]] = []

    def combine(
        self,
        body_frames: list[dict[str, Any]],
        face_frames: list[dict[str, Any]],
        facial_frames: list[dict[str, Any]],
    ) -> list[dict[str, float | int]]:
        frame_count = max(len(body_frames), len(face_frames), len(facial_frames))
        if frame_count == 0:
            self.last_diagnostics = []
            return []

        cfg = self.config
        diagnostics: list[dict[str, Any]] = []
        out: list[dict[str, float | int]] = []
        prev: dict[str, float] = {}

        for i in range(frame_count):
            body = body_frames[i] if i < len(body_frames) else {}
            face = face_frames[i] if i < len(face_frames) else {}
            facial = facial_frames[i] if i < len(facial_frames) else {}
            frame_index = int(body.get("frame_index", face.get("frame_index", facial.get("frame_index", i))))

            merged: dict[str, float | int] = {"frame_index": frame_index}

            for channel in cfg.head_channels:
                base_pose, base_conf = self._pick_value(body, face, channel, cfg.body_confidence_key, cfg.face_confidence_key)
                offset = self._extract_offset(face, channel)
                bounded_offset = self._clamp(offset, -cfg.head_offset_bounds.get(channel, 0.25), cfg.head_offset_bounds.get(channel, 0.25))
                target = base_pose + bounded_offset
                value = self._low_pass(prev.get(channel), target, cfg.head_low_pass_alpha)
                value = self._apply_max_delta(prev.get(channel), value, cfg.max_delta_per_frame)
                merged[channel] = value
                prev[channel] = value

                if abs(offset) > cfg.divergence_threshold:
                    diagnostics.append(
                        {
                            "frame_index": frame_index,
                            "channel": channel,
                            "type": "head_offset_divergence",
                            "offset": offset,
                        }
                    )
                face_abs = face.get(channel)
                if face_abs is not None and abs(float(face_abs) - float(base_pose)) > cfg.divergence_threshold and base_conf > 0.0:
                    diagnostics.append(
                        {
                            "frame_index": frame_index,
                            "channel": channel,
                            "type": "body_face_divergence",
                            "body": float(base_pose),
                            "face": float(face_abs),
                        }
                    )

            for channel in cfg.lips_channels:
                raw, conf = self._pick_value(facial, face, channel, cfg.facial_confidence_key, cfg.face_confidence_key)
                delta = abs(raw - prev.get(channel, raw))
                adaptive_alpha = self._clamp(cfg.lips_alpha_min + conf * cfg.lips_adaptive_scale * delta, cfg.lips_alpha_min, cfg.lips_alpha_max)
                value = self._low_pass(prev.get(channel), raw, adaptive_alpha)
                value = self._apply_max_delta(prev.get(channel), value, cfg.max_delta_per_frame)
                merged[channel] = value
                prev[channel] = value

            for channel in (*cfg.eyes_channels, *cfg.brow_channels):
                raw, _ = self._pick_value(facial, face, channel, cfg.facial_confidence_key, cfg.face_confidence_key)
                prior = prev.get(channel)
                step = abs(raw - prior) if prior is not None else 0.0
                alpha = cfg.eyes_event_alpha if step >= cfg.eyes_event_threshold else cfg.eyes_base_alpha
                value = self._low_pass(prior, raw, alpha)
                value = self._apply_max_delta(prior, value, cfg.max_delta_per_frame)
                merged[channel] = value
                prev[channel] = value

            out.append(merged)

        self.last_diagnostics = diagnostics
        return out

    def _pick_value(
        self,
        primary: dict[str, Any],
        fallback: dict[str, Any],
        channel: str,
        primary_conf_key: str,
        fallback_conf_key: str,
    ) -> tuple[float, float]:
        p_val = primary.get(channel)
        f_val = fallback.get(channel)
        p_conf = float(primary.get(f"{channel}_confidence", primary.get(primary_conf_key, 0.0)))
        f_conf = float(fallback.get(f"{channel}_confidence", fallback.get(fallback_conf_key, 0.0)))

        if p_val is not None and (f_val is None or p_conf >= f_conf):
            return float(p_val), self._clamp(p_conf, 0.0, 1.0)
        if f_val is not None:
            return float(f_val), self._clamp(f_conf, 0.0, 1.0)
        return 0.0, 0.0

    @staticmethod
    def _extract_offset(face_frame: dict[str, Any], channel: str) -> float:
        for key in (f"{channel}_offset", f"offset_{channel}"):
            if key in face_frame:
                return float(face_frame[key])
        return 0.0

    @staticmethod
    def _low_pass(previous: float | None, target: float, alpha: float) -> float:
        if previous is None:
            return target
        return previous + alpha * (target - previous)

    @staticmethod
    def _apply_max_delta(previous: float | None, value: float, max_delta: float) -> float:
        if previous is None:
            return value
        return previous + max(-max_delta, min(max_delta, value - previous))

    @staticmethod
    def _clamp(value: float, low: float, high: float) -> float:
        return max(low, min(high, value))
