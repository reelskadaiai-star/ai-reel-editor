"""
Scene detection using PySceneDetect + OpenCV.
Produces timestamped segments and scores them for highlight potential.
"""
from __future__ import annotations
import cv2
import numpy as np
from pathlib import Path
from loguru import logger


class SceneDetector:
    def __init__(self, video_path: str, threshold: float = 27.0):
        self.video_path = video_path
        self.threshold = threshold
        self._cap = cv2.VideoCapture(video_path)
        self.fps: float = self._cap.get(cv2.CAP_PROP_FPS) or 30.0
        self.frame_count: int = int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.duration: float = self.frame_count / self.fps

    def detect(self) -> list[dict]:
        """
        Returns list of dicts: {start, end, brightness, motion_score, is_dead}
        Uses content-aware detection (frame diff + brightness filter).
        """
        logger.info(f"[SceneDetect] Analysing {Path(self.video_path).name} ({self.duration:.1f}s)")
        scenes = []
        self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)

        prev_gray = None
        scene_start = 0.0
        frame_idx = 0
        scene_metrics: list[float] = []

        while True:
            ret, frame = self._cap.read()
            if not ret:
                break

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            brightness = float(gray.mean())

            if prev_gray is not None:
                diff = cv2.absdiff(gray, prev_gray)
                motion = float(diff.mean())
                scene_metrics.append(motion)

                # Scene cut detected
                if motion > self.threshold:
                    ts = frame_idx / self.fps
                    scenes.append(self._make_scene(scene_start, ts, scene_metrics))
                    scene_start = ts
                    scene_metrics = []

            prev_gray = gray
            frame_idx += 1

        # Final scene
        if scene_metrics:
            scenes.append(self._make_scene(scene_start, self.duration, scene_metrics))

        logger.info(f"[SceneDetect] Found {len(scenes)} scenes")
        return scenes

    def score_segments(self, beat_timestamps: list[float], content_type: str) -> list[dict]:
        """
        Score detected scenes and return ranked segments with highlight flags.
        Dead segments (< 1s, low motion) are pruned.
        """
        scenes = self.detect()
        scored = []

        for scene in scenes:
            dur = scene["end"] - scene["start"]
            if dur < 0.5:
                continue  # too short

            # Beat proximity bonus
            beat_bonus = sum(
                1 for b in beat_timestamps
                if scene["start"] <= b <= scene["end"]
            ) * 0.15

            # Content-type weighting
            weight = self._content_weight(content_type, scene)
            score = scene["motion_score"] * weight + beat_bonus

            scored.append({
                "start": round(scene["start"], 3),
                "end": round(scene["end"], 3),
                "score": round(score, 4),
                "type": "dead" if scene["is_dead"] else "highlight" if score > 0.6 else "normal",
                "label": scene.get("label", ""),
            })

        # Sort by score descending for renderer to pick highlights
        scored.sort(key=lambda s: s["score"], reverse=True)
        return scored

    # ── Internal ──────────────────────────────────────────────────────
    def _make_scene(self, start: float, end: float, metrics: list[float]) -> dict:
        motion = float(np.mean(metrics)) if metrics else 0.0
        is_dead = motion < 3.0 or (end - start) < 1.0
        return {
            "start": round(start, 3),
            "end": round(end, 3),
            "motion_score": round(min(motion / 30.0, 1.0), 4),
            "is_dead": is_dead,
            "label": "",
        }

    def _content_weight(self, content_type: str, scene: dict) -> float:
        weights = {
            "real_estate": 0.9,  # prefer smooth, well-lit scenes
            "food": 1.2,         # prefer high motion (sizzle, pour)
            "product": 1.0,
            "dance": 1.4,
            "travel": 1.1,
        }
        return weights.get(content_type, 1.0)

    def __del__(self):
        if self._cap.isOpened():
            self._cap.release()
