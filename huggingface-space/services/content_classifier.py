"""
Content-type classifier using open-source CLIP (open_clip).
Classifies into: real_estate, food, product, dance, travel,
nature, fitness, education, lifestyle, cinematic, vlog, interview, comedy, unknown.
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


# Each label is a rich descriptive sentence that CLIP can match against frames.
# Order must stay in sync with LABEL_KEYS below.
LABELS = [
    "real estate interior room house apartment luxury property bedroom living room kitchen",
    "food cooking restaurant meal dish cuisine recipe ingredients chef kitchen",
    "product showcase unboxing gadget merchandise item close-up product review",
    "dance choreography performance hip hop ballet movement music video",
    "travel tourism city landmark sightseeing destination street architecture",
    "plants flowers gardening nature garden botanical leaves greenery flora herbs succulent",
    "fitness gym workout exercise training weightlifting running sports athlete",
    # Broader education label — covers explainer, info, tutorial, YouTube creators, any language
    "person explaining informational educational tutorial knowledge sharing tips advice facts presenter",
    "lifestyle morning routine aesthetic daily vlog self-care wellness",
    "cinematic dramatic moody artistic film photography sunset portrait",
    # Vlog: casual personal storytelling
    "vlog person talking casually to camera personal daily life storytelling selfie informal",
    "interview conversation discussion podcast two people talking sitting",
    # Comedy: specific visual comedy markers — exaggerated expressions, props, sketch
    "comedian comedy sketch prank funny reaction exaggerated facial expression humour joke meme",
]

LABEL_KEYS = [
    "real_estate", "food", "product", "dance", "travel",
    "nature", "fitness", "education", "lifestyle",
    "cinematic", "vlog", "interview", "comedy",
]

assert len(LABELS) == len(LABEL_KEYS), "LABELS and LABEL_KEYS must have the same length"


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
        self, video_path: str, scenes: list[dict], sample_frames: int = 16
    ) -> tuple[str, float, list[str]]:
        """
        Returns (content_type, confidence, dominant_colors).
        Samples `sample_frames` key frames and takes majority vote.
        """
        frames = self._sample_frames(video_path, scenes, sample_frames)
        dominant_colors = self._extract_colors(frames[:6])

        if self._model is not None:
            label, confidence = self._clip_classify(frames)
        else:
            label, confidence = self._heuristic_classify(frames, dominant_colors)

        # ── Post-classification sanity: talking-head override ─────────
        # If CLIP chose "comedy" but the video looks like a talking-head
        # (person dominating the frame, low motion, indoor) → prefer "education".
        # This corrects misclassification of informational/educational creators
        # (Tamil, Hindi, regional-language YouTubers, etc.) who have expressive
        # delivery but are NOT doing comedy sketches.
        if label == "comedy" and confidence < 0.75:
            skin = self._skin_ratio(frames[:10])
            logger.info(f"[Classifier] comedy with low conf — skin_ratio={skin:.2f}")
            if skin > 0.12:   # person dominates frame → reclassify
                label = "education"
                confidence = max(confidence, 0.52)
                logger.info("[Classifier] Reclassified comedy → education (talking-head heuristic)")

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
    def _heuristic_classify(
        self, frames: list[np.ndarray], dominant_colors: list[str]
    ) -> tuple[str, float]:
        """
        Rough heuristic based on colour statistics when CLIP is unavailable.
        Green-dominant → nature; bright+low-sat → real_estate; high-sat → food;
        high skin-ratio → education (talking-head presenter).
        """
        if not frames:
            return "unknown", 0.3

        hsv_frames = [cv2.cvtColor(f, cv2.COLOR_BGR2HSV) for f in frames]
        avg_sat   = float(np.mean([f[:, :, 1].mean() for f in hsv_frames]))
        avg_val   = float(np.mean([f[:, :, 2].mean() for f in hsv_frames]))
        # Hue 35-85 (degrees/2 in OpenCV) = yellow-green to green
        green_ratio = float(np.mean([
            np.mean((f[:, :, 0] >= 35) & (f[:, :, 0] <= 85))
            for f in hsv_frames
        ]))
        skin_ratio = self._skin_ratio(frames[:8])

        logger.info(
            f"[Heuristic] sat={avg_sat:.0f} val={avg_val:.0f} "
            f"green={green_ratio:.2f} skin={skin_ratio:.2f}"
        )

        if green_ratio > 0.25:                          # dominant green → nature/plants
            return "nature", 0.60
        if avg_val > 160 and avg_sat < 60:              # bright, desaturated → real estate
            return "real_estate", 0.55
        if avg_sat > 110:                               # vivid colours → food
            return "food", 0.50
        if skin_ratio > 0.12:                           # person dominates → informational/education
            return "education", 0.52
        return "unknown", 0.30

    # ── Skin-tone ratio ────────────────────────────────────────────────
    def _skin_ratio(self, frames: list[np.ndarray]) -> float:
        """
        Estimate the fraction of pixels that are skin-tone.
        Uses HSV ranges that cover a broad range of skin tones (light to dark).
        A ratio > 0.10–0.15 strongly suggests a person occupies most of the frame.
        """
        if not frames:
            return 0.0
        ratios = []
        for frame in frames:
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            h, s, v = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
            # Broad skin-tone window: hue 0-25 (red-orange), sat 30-170, val 50-255
            mask = (
                ((h <= 25) | (h >= 165)) &   # red-orange-pink hues (wraps at 180)
                (s >= 30) & (s <= 170) &
                (v >= 50)
            )
            ratios.append(float(mask.mean()))
        return float(np.mean(ratios))

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
        remaining = n - len(frames)
        if remaining > 0 and total > 0:
            step = max(1, int(total / (remaining + 1)))
            for i in range(1, remaining + 2):
                cap.set(cv2.CAP_PROP_POS_FRAMES, i * step)
                ret, f = cap.read()
                if ret:
                    frames.append(f)
                    if len(frames) >= n:
                        break

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
