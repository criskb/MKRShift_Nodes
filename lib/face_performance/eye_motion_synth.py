from __future__ import annotations

from dataclasses import dataclass
import random
from typing import Any


@dataclass
class EyeMotionSynthConfig:
    """Configuration for EyeMotionSynth probabilistic state machine."""

    target_fps: int = 60
    mean_blink_interval_s: float = 4.2
    blink_interval_jitter_s: float = 1.6
    blink_duration_s: float = 0.16
    blink_peak_hold_s: float = 0.03
    articulation_suppression_threshold: float = 0.65
    articulation_suppression_factor: float = 0.2
    phrase_boundary_boost: float = 2.5
    pause_boundary_threshold: float = 0.25
    prosody_valley_threshold: float = -0.35
    micro_saccade_interval_s: tuple[float, float] = (0.08, 0.28)
    micro_saccade_sigma: float = 0.02
    gaze_drift_sigma: float = 0.004
    gaze_clamp: tuple[float, float] = (-1.0, 1.0)
    include_squint: bool = False

    expression_smoothing_alpha: float = 0.28
    expression_confidence_smoothing_alpha: float = 0.2
    eyelid_open_default: float = 0.92
    brow_inner_up_range: tuple[float, float] = (0.0, 1.0)
    brow_outer_up_range: tuple[float, float] = (0.0, 1.0)
    eyelid_open_range: tuple[float, float] = (0.0, 1.0)
    cheek_raise_range: tuple[float, float] = (0.0, 1.0)
    nasolabial_tension_range: tuple[float, float] = (0.0, 1.0)
    expr_confidence_range: tuple[float, float] = (0.0, 1.0)


class EyeMotionSynth:
    """Synthesize blink, gaze, and expression motion from an audio feature stream."""

    def __init__(self, config: EyeMotionSynthConfig | None = None, seed: int | None = None):
        self.config = config or EyeMotionSynthConfig()
        self._rng = random.Random(seed)

    def synthesize(self, audio2face_frames: list[dict[str, Any]]) -> list[dict[str, float | int]]:
        if not audio2face_frames:
            return []

        cfg = self.config
        blink_close_frames = max(1, int(round((cfg.blink_duration_s - cfg.blink_peak_hold_s) * 0.5 * cfg.target_fps)))
        blink_hold_frames = max(0, int(round(cfg.blink_peak_hold_s * cfg.target_fps)))
        blink_open_frames = blink_close_frames

        gaze_yaw = 0.0
        gaze_pitch = 0.0
        microsaccade_countdown = self._sample_microsaccade_countdown()

        next_blink_in_frames = self._sample_next_blink_interval()
        blink_phase = "idle"
        phase_frame = 0

        brow_inner_up = 0.0
        brow_outer_up_l = 0.0
        brow_outer_up_r = 0.0
        eyelid_open_l = cfg.eyelid_open_default
        eyelid_open_r = cfg.eyelid_open_default
        cheek_raise_l = 0.0
        cheek_raise_r = 0.0
        nasolabial_tension = 0.0
        expr_confidence = 0.0

        output: list[dict[str, float | int]] = []

        for i, src in enumerate(audio2face_frames):
            frame_index = int(src.get("frame_index", i))
            articulation = float(src.get("articulation", 0.0))
            pause = float(src.get("pause", 0.0))
            prosody_valley = float(src.get("prosody_valley", 0.0))
            energy = float(src.get("energy", 0.0))
            pitch_slope = float(src.get("pitch_slope", 0.0))
            smile = float(src.get("smile", 0.0))

            inferred_boundary = 1.0 if (pause >= cfg.pause_boundary_threshold or prosody_valley <= cfg.prosody_valley_threshold) else 0.0
            phrase_boundary = float(src.get("phrase_boundary", inferred_boundary))

            if blink_phase == "idle":
                next_blink_in_frames -= 1
                if next_blink_in_frames <= 0:
                    trigger_prob = self._blink_trigger_probability(
                        articulation=articulation,
                        pause=pause,
                        prosody_valley=prosody_valley,
                    )
                    if self._rng.random() < trigger_prob:
                        blink_phase = "closing"
                        phase_frame = 0
                    else:
                        next_blink_in_frames = max(1, int(0.2 * cfg.target_fps))

            blink_value = 0.0
            if blink_phase == "closing":
                phase_frame += 1
                blink_value = min(1.0, phase_frame / blink_close_frames)
                if phase_frame >= blink_close_frames:
                    blink_phase = "hold" if blink_hold_frames > 0 else "opening"
                    phase_frame = 0
                    blink_value = 1.0
            elif blink_phase == "hold":
                phase_frame += 1
                blink_value = 1.0
                if phase_frame >= blink_hold_frames:
                    blink_phase = "opening"
                    phase_frame = 0
            elif blink_phase == "opening":
                phase_frame += 1
                blink_value = max(0.0, 1.0 - (phase_frame / blink_open_frames))
                if phase_frame >= blink_open_frames:
                    blink_phase = "idle"
                    phase_frame = 0
                    blink_value = 0.0
                    next_blink_in_frames = self._sample_next_blink_interval()

            microsaccade_countdown -= 1
            if microsaccade_countdown <= 0:
                gaze_yaw += self._rng.gauss(0.0, cfg.micro_saccade_sigma)
                gaze_pitch += self._rng.gauss(0.0, cfg.micro_saccade_sigma)
                microsaccade_countdown = self._sample_microsaccade_countdown()
            else:
                gaze_yaw += self._rng.gauss(0.0, cfg.gaze_drift_sigma)
                gaze_pitch += self._rng.gauss(0.0, cfg.gaze_drift_sigma)

            gaze_yaw = max(cfg.gaze_clamp[0], min(cfg.gaze_clamp[1], gaze_yaw))
            gaze_pitch = max(cfg.gaze_clamp[0], min(cfg.gaze_clamp[1], gaze_pitch))

            energy = self._clamp(energy, (0.0, 1.0))
            pitch_slope = self._clamp(pitch_slope, (-1.0, 1.0))
            phrase_boundary = self._clamp(phrase_boundary, (0.0, 1.0))
            smile = self._clamp(smile, (0.0, 1.0))

            rising_pitch = max(0.0, pitch_slope)
            falling_pitch = max(0.0, -pitch_slope)

            brow_inner_target = 0.18 + 0.38 * energy + 0.26 * phrase_boundary + 0.18 * rising_pitch
            brow_outer_l_target = 0.12 + 0.28 * energy + 0.2 * phrase_boundary + 0.2 * rising_pitch
            brow_outer_r_target = 0.12 + 0.26 * energy + 0.22 * phrase_boundary + 0.2 * rising_pitch

            blink_open = 1.0 - blink_value
            eyelid_target = cfg.eyelid_open_default + 0.08 * energy - 0.14 * smile - 0.12 * phrase_boundary - 0.05 * falling_pitch
            eyelid_l_target = eyelid_target * blink_open
            eyelid_r_target = (eyelid_target - 0.01 * phrase_boundary) * blink_open

            cheek_l_target = 0.08 + 0.36 * smile + 0.24 * energy + 0.06 * phrase_boundary
            cheek_r_target = 0.08 + 0.34 * smile + 0.24 * energy + 0.08 * phrase_boundary

            nasolabial_target = 0.06 + 0.42 * smile + 0.22 * energy + 0.14 * phrase_boundary
            confidence_target = 0.15 + 0.45 * energy + 0.2 * abs(pitch_slope) + 0.2 * phrase_boundary

            alpha = cfg.expression_smoothing_alpha
            brow_inner_up = self._smooth(brow_inner_up, self._clamp(brow_inner_target, cfg.brow_inner_up_range), alpha)
            brow_outer_up_l = self._smooth(brow_outer_up_l, self._clamp(brow_outer_l_target, cfg.brow_outer_up_range), alpha)
            brow_outer_up_r = self._smooth(brow_outer_up_r, self._clamp(brow_outer_r_target, cfg.brow_outer_up_range), alpha)
            eyelid_open_l = self._smooth(eyelid_open_l, self._clamp(eyelid_l_target, cfg.eyelid_open_range), alpha)
            eyelid_open_r = self._smooth(eyelid_open_r, self._clamp(eyelid_r_target, cfg.eyelid_open_range), alpha)
            cheek_raise_l = self._smooth(cheek_raise_l, self._clamp(cheek_l_target, cfg.cheek_raise_range), alpha)
            cheek_raise_r = self._smooth(cheek_raise_r, self._clamp(cheek_r_target, cfg.cheek_raise_range), alpha)
            nasolabial_tension = self._smooth(
                nasolabial_tension,
                self._clamp(nasolabial_target, cfg.nasolabial_tension_range),
                alpha,
            )
            expr_confidence = self._smooth(
                expr_confidence,
                self._clamp(confidence_target, cfg.expr_confidence_range),
                cfg.expression_confidence_smoothing_alpha,
            )

            out: dict[str, float | int] = {
                "frame_index": frame_index,
                "blink_l": blink_value,
                "blink_r": blink_value,
                "gaze_yaw": gaze_yaw,
                "gaze_pitch": gaze_pitch,
                "brow_inner_up": brow_inner_up,
                "brow_outer_up_l": brow_outer_up_l,
                "brow_outer_up_r": brow_outer_up_r,
                "eyelid_open_l": eyelid_open_l,
                "eyelid_open_r": eyelid_open_r,
                "cheek_raise_l": cheek_raise_l,
                "cheek_raise_r": cheek_raise_r,
                "nasolabial_tension": nasolabial_tension,
                "expr_confidence": expr_confidence,
            }
            if cfg.include_squint:
                squint = min(1.0, max(0.0, 0.08 + 0.2 * blink_value + 0.12 * max(0.0, articulation - 0.5)))
                out["squint"] = squint

            output.append(out)

        return output

    def _sample_next_blink_interval(self) -> int:
        cfg = self.config
        base = cfg.mean_blink_interval_s + self._rng.uniform(-cfg.blink_interval_jitter_s, cfg.blink_interval_jitter_s)
        base = max(0.5, base)
        return int(round(base * cfg.target_fps))

    def _sample_microsaccade_countdown(self) -> int:
        low, high = self.config.micro_saccade_interval_s
        return max(1, int(round(self._rng.uniform(low, high) * self.config.target_fps)))

    def _blink_trigger_probability(self, articulation: float, pause: float, prosody_valley: float) -> float:
        cfg = self.config
        prob = 1.0

        if articulation >= cfg.articulation_suppression_threshold:
            prob *= cfg.articulation_suppression_factor

        at_phrase_boundary = pause >= cfg.pause_boundary_threshold or prosody_valley <= cfg.prosody_valley_threshold
        if at_phrase_boundary:
            prob *= cfg.phrase_boundary_boost

        return min(1.0, max(0.0, prob))

    @staticmethod
    def _smooth(previous: float, target: float, alpha: float) -> float:
        return previous + alpha * (target - previous)

    @staticmethod
    def _clamp(value: float, bounds: tuple[float, float]) -> float:
        return max(bounds[0], min(bounds[1], value))
