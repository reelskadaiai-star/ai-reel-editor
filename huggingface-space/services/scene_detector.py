"""
Premium Scene Detector v3.
Scores clips on sharpness, faces, motion quality, brightness, stability.
Philosophy: keep everything useful — only bin truly unusable frames
(near-black, completely blown-out, extreme camera shake).
"""
from __future__ import annotations
import cv2
import numpy as np
from pathlib import Path
from loguru import logger

# Haar cascade bundled with every OpenCV build
_FACE_CASCADE = cv2.CascadeClassifier(
    cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
)


class SceneDetector:
    def __init__(self, video_path: str, threshold: float = 22.0):
        self.video_path = video_path
        self.threshold = threshold
        self._cap = cv2.VideoCapture(video_path)
        self.fps: float = max(self._cap.get(cv2.CAP_PROP_FPS) or 30.0, 1.0)
        self.frame_count: int = int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.duration: float = self.frame_count / self.fps

    # ── Public API ────────────────────────────────────────────────────────
    def detect(self) -> list[dict]:
        """
        Detect scene boundaries.
        Returns list of raw scene dicts with quality metrics.
        """
        logger.info(
            f"[SceneDetect] {Path(self.video_path).name} "
            f"({self.duration:.1f}s @ {self.fps:.0f}fps)"
        )
        self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)

        # Sample ~5 frames/second for efficiency
        sample_every = max(1, int(self.fps / 5))

        scenes: list[dict] = []
        scene_start = 0.0
        scene_samples: list[tuple] = []   # (timestamp, bgr_small, gray_small)
        prev_gray = None
        frame_idx = 0

        while True:
            ret, frame = self._cap.read()
            if not ret:
                break

            if frame_idx % sample_every == 0:
                ts = frame_idx / self.fps
                small = cv2.resize(frame, (320, 180))
                gray  = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)

                if prev_gray is not None:
                    diff   = cv2.absdiff(gray, prev_gray)
                    motion = float(diff.mean())

                    if motion > self.threshold and scene_samples:
                        scenes.append(self._analyse_scene(scene_start, ts, scene_samples))
                        scene_start   = ts
                        scene_samples = []

                scene_samples.append((ts, small, gray))
                prev_gray = gray

            frame_idx += 1

        # Last scene
        if scene_samples:
            scenes.append(self._analyse_scene(scene_start, self.duration, scene_samples))

        # Drop truly micro-scenes (< 0.4 s)
        scenes = [s for s in scenes if (s["end"] - s["start"]) >= 0.4]
        logger.info(f"[SceneDetect] {len(scenes)} scenes found")
        return scenes

    def score_segments(
        self, beat_timestamps: list[float], content_type: str
    ) -> list[dict]:
        """Score scenes and return renderer-ready segment list."""
        scenes = self.detect()
        scored: list[dict] = []

        for scene in scenes:
            dur = scene["end"] - scene["start"]
            if dur < 0.4:
                continue

            score    = self._compute_score(scene, beat_timestamps, content_type)
            is_dead  = scene.get("is_unusable", False)

            if is_dead:
                seg_type = "dead"
            elif score >= 0.60:
                seg_type = "highlight"
            elif score >= 0.30:
                seg_type = "normal"
            else:
                # Low score but not "unusable" — keep as normal so renderer can use it
                seg_type = "normal"

            scored.append({
                "start": round(scene["start"], 3),
                "end":   round(scene["end"],   3),
                "score": round(score, 4),
                "type":  seg_type,
                "label": scene.get("label", ""),
            })

        scored.sort(key=lambda s: s["score"], reverse=True)
        logger.info(
            f"[SceneDetect] scores — highlights: {sum(1 for s in scored if s['type']=='highlight')}, "
            f"normal: {sum(1 for s in scored if s['type']=='normal')}, "
            f"dead: {sum(1 for s in scored if s['type']=='dead')}"
        )
        return scored

    # ── Internal analysis ─────────────────────────────────────────────────
    def _analyse_scene(
        self, start: float, end: float, samples: list[tuple]
    ) -> dict:
        """Compute quality metrics for one detected scene."""
        if not samples:
            return {
                "start": start, "end": end,
                "sharpness": 0, "brightness": 0, "motion": 0,
                "face_score": 0, "has_face": False,
                "is_unusable": True, "label": "empty",
            }

        sharpness_list: list[float] = []
        brightness_list: list[float] = []
        motion_list: list[float] = []
        face_scores: list[float] = []
        prev_gray = None

        for (ts, bgr, gray) in samples:
            # Sharpness (Laplacian variance — higher = sharper)
            lap = float(cv2.Laplacian(gray, cv2.CV_64F).var())
            sharpness_list.append(lap)

            # Brightness
            brightness_list.append(float(gray.mean()))

            # Optical-flow motion (inter-frame)
            if prev_gray is not None:
                try:
                    flow = cv2.calcOpticalFlowFarneback(
                        prev_gray, gray, None,
                        pyr_scale=0.5, levels=2, winsize=8,
                        iterations=2, poly_n=5, poly_sigma=1.1, flags=0,
                    )
                    mag = np.sqrt(flow[..., 0] ** 2 + flow[..., 1] ** 2)
                    motion_list.append(float(mag.mean()))
                except Exception:
                    pass
            prev_gray = gray

            # Face detection (fast on 320×180 frame)
            faces = _FACE_CASCADE.detectMultiScale(
                gray, scaleFactor=1.1, minNeighbors=3, minSize=(15, 15)
            )
            face_scores.append(min(len(faces) * 0.5, 1.0))

        avg_sharpness  = float(np.mean(sharpness_list))  if sharpness_list  else 0.0
        avg_brightness = float(np.mean(brightness_list)) if brightness_list else 0.0
        avg_motion     = float(np.mean(motion_list))     if motion_list     else 0.0
        max_face       = max(face_scores, default=0.0)
        has_face       = max_face > 0

        # ── Unusable detection (very conservative) ─────────────────────
        is_unusable = (
            avg_brightness < 12 or
            avg_brightness > 248 or
            (avg_motion > 30 and avg_sharpness < 15)
        )

        # ── Semantic label ─────────────────────────────────────────────
        # Multi-label: describes scene category and shot type
        labels = []

        # Shot type
        if has_face:
            labels.append("face")
            if max_face >= 0.8:
                labels.append("close_up")
        if avg_motion > 8.0:
            labels.append("action")
        elif avg_motion < 1.5:
            labels.append("static")

        # Brightness character
        if avg_brightness > 180:
            labels.append("bright")
        elif avg_brightness < 40:
            labels.append("dark")

        # Quality markers
        if avg_sharpness < 30:
            labels.append("blurry")
        elif avg_sharpness > 200:
            labels.append("sharp")

        # Colour character (use last sampled frame)
        if samples:
            _, last_bgr, _ = samples[-1]
            mean_bgr = last_bgr.mean(axis=(0, 1))  # [B, G, R]
            b_ch, g_ch, r_ch = float(mean_bgr[0]), float(mean_bgr[1]), float(mean_bgr[2])
            total = b_ch + g_ch + r_ch + 1e-6
            if g_ch / total > 0.38:
                labels.append("green_dominant")   # nature / plants
            if r_ch / total > 0.36:
                labels.append("warm_tones")        # food / sunset / skin
            if b_ch / total > 0.38:
                labels.append("cool_tones")        # sky / water / night

            # Skin-tone heuristic (talking head / portrait)
            skin_pixels = np.sum(
                (last_bgr[:, :, 2] > 80) &   # R > 80
                (last_bgr[:, :, 1] > 40) &   # G > 40
                (last_bgr[:, :, 0] < 140) &  # B < 140
                (last_bgr[:, :, 2] > last_bgr[:, :, 2].mean())
            )
            total_pixels = last_bgr.shape[0] * last_bgr.shape[1]
            if skin_pixels / total_pixels > 0.20:
                labels.append("skin_dominant")     # portrait / talking head

        # Landscape heuristic: wide aspect, no face, low motion
        if not has_face and avg_motion < 5.0 and avg_sharpness > 50:
            labels.append("landscape")

        label = ",".join(labels) if labels else "normal"

        return {
            "start":       round(start, 3),
            "end":         round(end, 3),
            "sharpness":   round(avg_sharpness, 1),
            "brightness":  round(avg_brightness, 1),
            "motion":      round(avg_motion, 2),
            "face_score":  round(max_face, 3),
            "has_face":    has_face,
            "is_unusable": is_unusable,
            "label":       label,
        }

    def _compute_score(
        self, scene: dict, beats: list[float], content_type: str
    ) -> float:
        """Return a 0–1 quality score."""
        score = 0.0

        # 1. Sharpness (0–1, normalised at 200 — most sharp real footage is 50–300)
        sharpness_norm = min(scene["sharpness"] / 200.0, 1.0)
        score += sharpness_norm * 0.25

        # 2. Brightness quality (peak at 110–140, penalty at extremes)
        b = scene["brightness"]
        if 35 <= b <= 220:
            brightness_score = 1.0 - abs(b - 128) / 200.0
        else:
            brightness_score = 0.05
        score += brightness_score * 0.15

        # 3. Face / subject presence
        score += scene.get("face_score", 0.0) * 0.30

        # 4. Motion — content-type aware
        m = min(scene.get("motion", 0.0) / 15.0, 1.0)  # normalise at 15
        if content_type in ("dance", "fitness", "sports", "comedy"):
            # High motion desired
            score += m * 0.20
        elif content_type in ("education", "interview", "vlog", "nature"):
            # Stable is fine — don't penalise low motion
            score += 0.15  # flat bonus so all talking-head scenes keep decent score
        else:
            score += min(m, 0.5) * 0.15 + 0.05

        # 5. Beat proximity (cuts near a beat feel energetic)
        mid = (scene["start"] + scene["end"]) / 2
        if any(abs(b - mid) < 0.6 for b in beats):
            score += 0.10

        # 6. Duration sweet-spot (2–8 s)
        dur = scene["end"] - scene["start"]
        if 2.0 <= dur <= 8.0:
            score += 0.10
        elif dur >= 1.0:
            score += 0.05

        # 7. Unusable hard penalty
        if scene.get("is_unusable", False):
            score *= 0.05

        return round(min(score, 1.0), 4)

    # ── Deprecated shim (called by old code paths) ─────────────────────
    def _content_weight(self, content_type: str, scene: dict) -> float:
        return 1.0

    def _make_scene(self, start: float, end: float, metrics: list) -> dict:
        motion = float(np.mean(metrics)) if metrics else 0.0
        return {
            "start": round(start, 3), "end": round(end, 3),
            "motion_score": round(min(motion / 30.0, 1.0), 4),
            "is_dead": motion < 1.5 and (end - start) < 1.0,
            "label": "",
        }

    def __del__(self):
        try:
            if self._cap.isOpened():
                self._cap.release()
        except Exception:
            pass
