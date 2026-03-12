from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
from statistics import fmean
from typing import Any


@dataclass
class ClipMetrics:
    clip_id: str
    lip_audio_sync_lag_frames: int
    lip_audio_sync_lag_seconds: float
    lip_audio_sync_correlation: float
    blink_rate_per_minute: float
    blink_duration_histogram_seconds: dict[str, int]
    blink_count: int
    landmark_velocity_outliers: int
    landmark_acceleration_outliers: int
    pose_jitter_score: float


@dataclass
class RegressionThresholds:
    max_abs_lip_audio_sync_lag_frames: int = 4
    min_lip_audio_sync_correlation: float = 0.45
    blink_rate_per_minute_range: tuple[float, float] = (6.0, 45.0)
    max_landmark_velocity_outliers: int = 18
    max_landmark_acceleration_outliers: int = 24
    max_pose_jitter_score: float = 0.055


class NodeEvaluationUtility:
    def __init__(self, fps: int = 60):
        self.fps = fps

    def evaluate_clip(
        self,
        clip_id: str,
        audio_frames: list[dict[str, Any]],
        refined_frames: list[dict[str, Any]],
        eye_frames: list[dict[str, Any]],
        pose_frames: list[dict[str, Any]],
    ) -> ClipMetrics:
        articulation = [float(frame.get("articulation", 0.0)) for frame in audio_frames]
        jaw = [float(frame.get("refined_jaw_open", frame.get("jaw_open", 0.0))) for frame in refined_frames]

        lag_frames, best_corr = self._estimate_lag(articulation, jaw, max_lag_frames=12)

        blink_signal = [0.5 * (float(frame.get("blink_l", 0.0)) + float(frame.get("blink_r", 0.0))) for frame in eye_frames]
        blink_durations_s = self._blink_durations(blink_signal, threshold=0.6)
        clip_minutes = max(len(eye_frames) / self.fps / 60.0, 1e-6)
        blink_rate = len(blink_durations_s) / clip_minutes

        histogram_bins = [0.0, 0.08, 0.12, 0.16, 0.2, 0.3, 10.0]
        blink_hist: dict[str, int] = {}
        for low, high in zip(histogram_bins[:-1], histogram_bins[1:]):
            label = f"{low:.2f}-{high:.2f}"
            blink_hist[label] = sum(1 for duration in blink_durations_s if low <= duration < high)

        landmark_channels = ("gaze_yaw", "gaze_pitch", "pupil_x", "pupil_y", "roi_center_x", "roi_center_y")
        landmark_series = self._collect_landmark_series(eye_frames, refined_frames, landmark_channels)
        velocity_outliers, acceleration_outliers = self._motion_outliers(landmark_series)

        pose_channels = ("head_yaw", "head_pitch", "head_roll", "neck_yaw", "neck_pitch", "neck_roll")
        pose_jitter = self._pose_jitter(pose_frames, pose_channels)

        return ClipMetrics(
            clip_id=clip_id,
            lip_audio_sync_lag_frames=lag_frames,
            lip_audio_sync_lag_seconds=lag_frames / self.fps,
            lip_audio_sync_correlation=best_corr,
            blink_rate_per_minute=blink_rate,
            blink_duration_histogram_seconds=blink_hist,
            blink_count=len(blink_durations_s),
            landmark_velocity_outliers=velocity_outliers,
            landmark_acceleration_outliers=acceleration_outliers,
            pose_jitter_score=pose_jitter,
        )

    def write_artifacts(
        self,
        output_dir: str | Path,
        metrics: list[ClipMetrics],
        thresholds: RegressionThresholds,
    ) -> None:
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        payload = {
            "fps": self.fps,
            "thresholds": asdict(thresholds),
            "clips": [asdict(metric) for metric in metrics],
        }
        (out_dir / "node_metrics.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

        self._write_bar_svg(
            out_dir / "lip_audio_sync_lag.svg",
            "Lip/Audio Sync Lag (frames)",
            [metric.clip_id for metric in metrics],
            [float(metric.lip_audio_sync_lag_frames) for metric in metrics],
            y_zero_center=True,
        )
        self._write_bar_svg(
            out_dir / "pose_jitter.svg",
            "Pose Jitter Score",
            [metric.clip_id for metric in metrics],
            [metric.pose_jitter_score for metric in metrics],
        )

        histogram_totals: dict[str, int] = {}
        for metric in metrics:
            for key, count in metric.blink_duration_histogram_seconds.items():
                histogram_totals[key] = histogram_totals.get(key, 0) + count
        self._write_histogram_svg(out_dir / "blink_duration_histogram.svg", "Blink Duration Histogram (seconds)", histogram_totals)

    @staticmethod
    def check_thresholds(metrics: list[ClipMetrics], thresholds: RegressionThresholds) -> list[str]:
        failures: list[str] = []
        for clip in metrics:
            if abs(clip.lip_audio_sync_lag_frames) > thresholds.max_abs_lip_audio_sync_lag_frames:
                failures.append(f"{clip.clip_id}: lag_frames={clip.lip_audio_sync_lag_frames}")
            if clip.lip_audio_sync_correlation < thresholds.min_lip_audio_sync_correlation:
                failures.append(f"{clip.clip_id}: lip_audio_correlation={clip.lip_audio_sync_correlation:.3f}")
            if not (
                thresholds.blink_rate_per_minute_range[0]
                <= clip.blink_rate_per_minute
                <= thresholds.blink_rate_per_minute_range[1]
            ):
                failures.append(f"{clip.clip_id}: blink_rate_per_minute={clip.blink_rate_per_minute:.2f}")
            if clip.landmark_velocity_outliers > thresholds.max_landmark_velocity_outliers:
                failures.append(f"{clip.clip_id}: landmark_velocity_outliers={clip.landmark_velocity_outliers}")
            if clip.landmark_acceleration_outliers > thresholds.max_landmark_acceleration_outliers:
                failures.append(f"{clip.clip_id}: landmark_acceleration_outliers={clip.landmark_acceleration_outliers}")
            if clip.pose_jitter_score > thresholds.max_pose_jitter_score:
                failures.append(f"{clip.clip_id}: pose_jitter_score={clip.pose_jitter_score:.4f}")
        return failures

    @staticmethod
    def _estimate_lag(a: list[float], b: list[float], max_lag_frames: int) -> tuple[int, float]:
        n = min(len(a), len(b))
        if n < 3:
            return 0, 0.0

        a = a[:n]
        b = b[:n]

        def corr(x: list[float], y: list[float]) -> float:
            mean_x = fmean(x)
            mean_y = fmean(y)
            delta_x = [value - mean_x for value in x]
            delta_y = [value - mean_y for value in y]
            denom = math.sqrt(sum(value * value for value in delta_x) * sum(value * value for value in delta_y))
            if denom <= 1e-9:
                return 0.0
            return sum(left * right for left, right in zip(delta_x, delta_y)) / denom

        best_lag = 0
        best_corr = -2.0
        for lag in range(-max_lag_frames, max_lag_frames + 1):
            if lag < 0:
                x, y = a[-lag:], b[: n + lag]
            elif lag > 0:
                x, y = a[: n - lag], b[lag:]
            else:
                x, y = a, b
            if len(x) < 3:
                continue
            current = corr(x, y)
            if current > best_corr:
                best_corr = current
                best_lag = lag
        return best_lag, max(best_corr, 0.0)

    def _blink_durations(self, blink_signal: list[float], threshold: float) -> list[float]:
        out: list[float] = []
        active = False
        start = 0
        for index, value in enumerate(blink_signal):
            if not active and value >= threshold:
                active = True
                start = index
            elif active and value < threshold:
                out.append((index - start) / self.fps)
                active = False
        if active:
            out.append((len(blink_signal) - start) / self.fps)
        return out

    def _collect_landmark_series(
        self,
        eye_frames: list[dict[str, Any]],
        refined_frames: list[dict[str, Any]],
        channels: tuple[str, ...],
    ) -> dict[str, list[float]]:
        series = {channel: [] for channel in channels}
        count = max(len(eye_frames), len(refined_frames))
        for index in range(count):
            eye = eye_frames[index] if index < len(eye_frames) else {}
            refined = refined_frames[index] if index < len(refined_frames) else {}
            merged = {**eye, **refined}
            for channel in channels:
                if channel in merged:
                    series[channel].append(float(merged[channel]))
        return series

    @staticmethod
    def _motion_outliers(series: dict[str, list[float]]) -> tuple[int, int]:
        velocities: list[float] = []
        accelerations: list[float] = []
        for values in series.values():
            if len(values) < 3:
                continue
            velocity = [abs(values[index] - values[index - 1]) for index in range(1, len(values))]
            acceleration = [abs(velocity[index] - velocity[index - 1]) for index in range(1, len(velocity))]
            velocities.extend(velocity)
            accelerations.extend(acceleration)

        def count_outliers(values: list[float]) -> int:
            if len(values) < 3:
                return 0
            mean = fmean(values)
            variance = fmean([(value - mean) ** 2 for value in values])
            std = math.sqrt(variance)
            threshold = max(mean + 4.0 * std, 0.05)
            if values and max(values) < 0.05:
                threshold = 1.0
            return sum(1 for value in values if value > threshold)

        velocity_outliers = count_outliers(velocities)
        accel_thresholded = [value for value in accelerations if value >= 0.08]
        acceleration_outliers = count_outliers(accel_thresholded) if accel_thresholded else 0
        return velocity_outliers, acceleration_outliers

    @staticmethod
    def _pose_jitter(frames: list[dict[str, Any]], channels: tuple[str, ...]) -> float:
        deltas: list[float] = []
        for channel in channels:
            prev: float | None = None
            for frame in frames:
                if channel not in frame:
                    continue
                value = float(frame[channel])
                if prev is not None:
                    deltas.append(abs(value - prev))
                prev = value
        return fmean(deltas) if deltas else 0.0

    @staticmethod
    def _write_bar_svg(path: Path, title: str, labels: list[str], values: list[float], y_zero_center: bool = False) -> None:
        width = 640
        height = 320
        margin = 40
        plot_width = width - 2 * margin
        plot_height = height - 2 * margin
        count = max(1, len(values))
        bar_width = plot_width / count * 0.65

        if y_zero_center:
            max_abs = max(max(abs(value) for value in values), 1.0)
            y_min = -max_abs
            y_max = max_abs
        else:
            y_min = 0.0
            y_max = max(max(values), 1e-6)

        def map_y(value: float) -> float:
            return margin + (y_max - value) / (y_max - y_min) * plot_height

        lines = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">',
            f'<text x="{width/2}" y="22" text-anchor="middle" font-size="16">{title}</text>',
            f'<line x1="{margin}" y1="{margin}" x2="{margin}" y2="{height-margin}" stroke="#222"/>',
            f'<line x1="{margin}" y1="{height-margin}" x2="{width-margin}" y2="{height-margin}" stroke="#222"/>',
        ]

        zero_y = map_y(0.0)
        if y_zero_center:
            lines.append(
                f'<line x1="{margin}" y1="{zero_y:.1f}" x2="{width-margin}" y2="{zero_y:.1f}" stroke="#777" stroke-dasharray="3,3"/>'
            )

        for index, (label, value) in enumerate(zip(labels, values)):
            x = margin + (index + 0.5) * (plot_width / count)
            y = map_y(value)
            y0 = zero_y if y_zero_center else height - margin
            top = min(y, y0)
            bar_height = abs(y0 - y)
            lines.append(f'<rect x="{x - bar_width/2:.1f}" y="{top:.1f}" width="{bar_width:.1f}" height="{bar_height:.1f}" fill="#4b7bec"/>')
            lines.append(f'<text x="{x:.1f}" y="{height-12}" text-anchor="middle" font-size="10">{label}</text>')
            lines.append(f'<text x="{x:.1f}" y="{max(top-4, 28):.1f}" text-anchor="middle" font-size="10">{value:.3f}</text>')

        lines.append("</svg>")
        path.write_text("\n".join(lines), encoding="utf-8")

    @staticmethod
    def _write_histogram_svg(path: Path, title: str, bins: dict[str, int]) -> None:
        labels = list(bins.keys())
        values = [bins[key] for key in labels]
        NodeEvaluationUtility._write_bar_svg(path, title, labels, [float(value) for value in values])
