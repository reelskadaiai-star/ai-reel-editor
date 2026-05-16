"""
Content-type classifier using open-source CLIP (open_clip).
Classifies into: real_estate, food, product, dance, travel,
cinematic, vlog, interview, comedy, unknown.
"""
from __future__ import annotations
import cv2
import torch
import numpy as np
from PIL import Image
from loguru import logger

try:
    import open_clip
    CLIP_AVAILABLE = True
except ImportError:
    CLIP_AVAILABLE = False
    logger.warning("open_clip not installed — falling back to heuristic classifier")


LABELS = [
    "real estate interior room house apartment property",
    "food cooking restaurant meal dish cuisine",
    "product showcase item gadget merchandise",
    "dance choreography performance music video",
    "travel landscape nature outdoor adventure",
    "cinematic film dramatic cinematic shot",
    "vlog personal talking head daily life",
    "interview conversation talking people",
    "comedy funny joke humour sketch",
]

LABEL_KEYS = [
    "real_estate", "food", "product", "dance", "travel",
    "cinematic", "vlog", "interview", "comedy",
]


class ContentClassifier:
    def __init__(self, model_name: str = "ViT-B-32", pretrained: str = "openai"):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self._model = None
        self._preprocess = None
        self._tokenizer = None

        if CLIP_AVAILABLE:
            try:
                self._model, _, self._preprocess = open_clip.create_model_and_transforms(
                    model_name, pretrained=pretrained, device=self.device
                )
                self._tokenizer = open_clip.get_tokenizer(model_name)
                self._model.eval()
                logger.info(f"[CLIP] Loaded {model_name} on {self.device}")
            except Exception as e:
                logger.warning(f"[CLIP] Load failed: {e} — using heuristic")

    def classify(
        self, video_path: str, scenes: list[dict], sample_frames: int = 12
    ) -> tuple[str, float, list[str]]:
        """
        Returns (content_type, confidence, dominant_colors).
        Samples `sample_frames` key frames and takes majority vote.
        """
        frames = self._sample_frames(video_path, scenes, sample_frames)
        dominant_colors = self._extract_colors(frames[:4])

        if self._model is not None:
            label, confidence = self._clip_classify(frames)
        else:
            label, confidence = self._heuristic_classify(frames)

        logger.info(f"[Classifier] → {label} ({confidence:.2f})")
        return label, confidence, dominant_colors

    # ── CLIP ──────────────────────────────────────────────────────────
    def _clip_classify(self, frames: list[np.ndarray]) -> tuple[str, float]:
        text_tokens = self._tokenizer(LABELS).to(self.device)

        votes = np.zeros(len(LABELS))
        with torch.no_grad():
            text_feats = self._model.encode_text(text_tokens)
            text_feats /= text_feats.norm(dim=-1, keepdim=True)

            for frame in frames:
                img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                img_t = self._preprocess(img).unsqueeze(0).to(self.device)
                img_feats = self._model.encode_image(img_t)
                img_feats /= img_feats.norm(dim=-1, keepdim=True)

                sims = (img_feats @ text_feats.T).squeeze(0).cpu().numpy()
                votes += sims

        idx = int(np.argmax(votes))
        confidence = float(votes[idx] / len(frames))
        return LABEL_KEYS[idx], max(0.0, min(1.0, (confidence + 0.3) / 0.6))

    # ── Heuristic fallback ─────────────────────────────────────────────
    def _heuristic_classify(self, frames: list[np.ndarray]) -> tuple[str, float]:
        """Very rough heuristic: brightness + saturation patterns."""
        brightnesses = [cv2.cvtColor(f, cv2.COLOR_BGR2GRAY).mean() for f in frames]
        avg_bright = np.mean(brightnesses)

        hsv_frames = [cv2.cvtColor(f, cv2.COLOR_BGR2HSV) for f in frames]
        avg_sat = np.mean([f[:, :, 1].mean() for f in hsv_frames])

        if avg_bright > 160 and avg_sat < 60:
            return "real_estate", 0.55
        if avg_sat > 120:
            return "food", 0.50
        return "unknown", 0.30

    # ── Helpers ───────────────────────────────────────────────────────
    def _sample_frames(self, video_path: str, scenes: list[dict], n: int) -> list[np.ndarray]:
        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total = cap.get(cv2.CAP_PROP_FRAME_COUNT)
        frames = []

        # Sample from middle of each top-N scene
        top_scenes = sorted(scenes, key=lambda s: s.get("motion_score", 0), reverse=True)[:n]
        for scene in top_scenes:
            mid = (scene["start"] + scene["end"]) / 2
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(mid * fps))
            ret, frame = cap.read()
            if ret:
                frames.append(frame)

        # Fill remainder with uniform sampling
        if len(frames) < n:
            step = int(total / (n - len(frames) + 1))
            for i in range(1, n - len(frames) + 1):
                cap.set(cv2.CAP_PROP_POS_FRAMES, i * step)
                ret, f = cap.read()
                if ret:
                    frames.append(f)

        cap.release()
        return frames[:n]

    def _extract_colors(self, frames: list[np.ndarray]) -> list[str]:
        """Return top-5 dominant hex colors via k-means."""
        if not frames:
            return []
        try:
            pixels = np.vstack([
                cv2.resize(f, (50, 50)).reshape(-1, 3) for f in frames
            ]).astype(np.float32)
            _, labels, centers = cv2.kmeans(
                pixels, 5, None,
                (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 10, 1.0),
                3, cv2.KMEANS_RANDOM_CENTERS
            )
            colors = []
            for c in centers:
                b, g, r = int(c[0]), int(c[1]), int(c[2])
                colors.append(f"#{r:02x}{g:02x}{b:02x}")
            return colors
        except Exception:
            return []
