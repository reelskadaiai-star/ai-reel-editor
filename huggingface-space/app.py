"""
ReelAI — HuggingFace Space AI Service
Runs on port 7860 (HF Spaces requirement).
Uses threading instead of Celery — no Redis needed.
Jobs stored in memory; results served as static files.
"""
import os
import uuid
import threading
import tempfile
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from loguru import logger

from services.scene_detector import SceneDetector
from services.content_classifier import ContentClassifier
from services.audio_analyzer import AudioAnalyzer
from services.caption_generator import CaptionGenerator
from services.reel_renderer import ReelRenderer

# ── Directories ───────────────────────────────────────────────────────
UPLOADS_DIR = Path("/tmp/uploads")
OUTPUTS_DIR = Path("/tmp/outputs")
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

# ── In-memory job store ───────────────────────────────────────────────
_jobs: dict = {}
_lock = threading.Lock()

def _set_job(task_id: str, data: dict):
    with _lock:
        _jobs[task_id] = data

def _get_job(task_id: str) -> dict:
    with _lock:
        return _jobs.get(task_id, {"state": "PENDING"})

def _progress(task_id: str, percent: int, message: str):
    _set_job(task_id, {"state": "PROGRESS", "meta": {"percent": percent, "message": message}})

# ── App ───────────────────────────────────────────────────────────────
app = FastAPI(title="ReelAI HF Space", version="1.0.0")

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Serve output files (renders, thumbnails, watermarked)
app.mount("/outputs", StaticFiles(directory=str(OUTPUTS_DIR)), name="outputs")


# ── Request models ────────────────────────────────────────────────────
class AnalyzeRequest(BaseModel):
    job_id: str
    video_url: str          # Public URL of the uploaded video on Render gateway


class RenderRequest(BaseModel):
    job_id: str
    video_url: str
    template: str = "auto"
    music_url: str | None = None
    music_offset: float = 0.0
    aspect_ratio: str = "9:16"
    caption_style: str = "modern"
    transition_style: str = "auto"
    target_duration: int = 30
    include_hook: bool = True
    hook_text: str | None = None


# ── Routes ────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/analyze")
def analyze(req: AnalyzeRequest):
    task_id = str(uuid.uuid4())
    _set_job(task_id, {"state": "STARTED"})
    t = threading.Thread(target=_run_analyze, args=(task_id, req.job_id, req.video_url), daemon=True)
    t.start()
    logger.info(f"[Analyze] task={task_id} job={req.job_id}")
    return {"task_id": task_id}


@app.post("/render")
def render(req: RenderRequest):
    task_id = str(uuid.uuid4())
    _set_job(task_id, {"state": "STARTED"})
    t = threading.Thread(
        target=_run_render,
        args=(task_id, req.job_id, req.video_url, req.template, req.music_url,
              req.music_offset, req.aspect_ratio, req.caption_style,
              req.transition_style, req.target_duration, req.include_hook, req.hook_text),
        daemon=True,
    )
    t.start()
    logger.info(f"[Render] task={task_id} job={req.job_id}")
    return {"task_id": task_id}


@app.get("/task/{task_id}")
def get_task(task_id: str):
    return _get_job(task_id)


# ── Background workers ─────────────────────────────────────────────────
def _download_video(video_url: str, job_id: str) -> Path:
    """Download video from gateway to local /tmp/uploads."""
    suffix = Path(video_url).suffix or ".mp4"
    dest = UPLOADS_DIR / f"{job_id}{suffix}"
    if dest.exists():
        return dest
    logger.info(f"Downloading {video_url} → {dest}")
    with httpx.stream("GET", video_url, timeout=300, follow_redirects=True) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_bytes(chunk_size=8192):
                f.write(chunk)
    return dest


def _run_analyze(task_id: str, job_id: str, video_url: str):
    try:
        _progress(task_id, 5, "Downloading video")
        video_path = str(_download_video(video_url, job_id))

        _progress(task_id, 15, "Detecting scenes")
        detector = SceneDetector(video_path)
        scenes = detector.detect()
        duration = detector.duration

        _progress(task_id, 30, "Classifying content")
        classifier = ContentClassifier()
        content_type, confidence, dominant_colors = classifier.classify(video_path, scenes)

        _progress(task_id, 45, "Analysing audio & beats")
        audio = AudioAnalyzer(video_path)
        beats = audio.detect_beats()

        _progress(task_id, 60, "Generating captions")
        captions = CaptionGenerator().transcribe(video_path)

        _progress(task_id, 75, "Scoring highlights")
        segments = detector.score_segments(beats, content_type)

        _progress(task_id, 90, "Building result")
        template = _suggest_template(content_type)
        hook_text = _generate_hook(content_type)

        _set_job(task_id, {
            "state": "SUCCESS",
            "result": {
                "content_type": content_type,
                "confidence": float(confidence),
                "segments": segments,
                "captions": captions,
                "beat_timestamps": beats,
                "dominant_colors": dominant_colors,
                "scene_count": len(scenes),
                "duration": duration,
                "suggested_template": template,
                "hook_text": hook_text,
            }
        })
        logger.info(f"[Analyze] ✅ task={task_id} type={content_type}")

    except Exception as exc:
        logger.exception(f"[Analyze] ❌ task={task_id}: {exc}")
        _set_job(task_id, {"state": "FAILURE", "traceback": str(exc)})


def _run_render(task_id, job_id, video_url, template, music_url,
                music_offset, aspect_ratio, caption_style,
                transition_style, target_duration, include_hook, hook_text):
    try:
        _progress(task_id, 5, "Downloading video")
        video_path = str(_download_video(video_url, job_id))

        _progress(task_id, 15, "Re-analysing for render")
        detector = SceneDetector(video_path)
        scenes = detector.detect()
        classifier = ContentClassifier()
        content_type, _, _ = classifier.classify(video_path, scenes)
        beats = AudioAnalyzer(video_path).detect_beats()
        captions = CaptionGenerator().transcribe(video_path)
        segments = detector.score_segments(beats, content_type)

        # Download music if provided
        music_path = None
        if music_url:
            music_dest = UPLOADS_DIR / f"{job_id}_music.mp3"
            with httpx.stream("GET", music_url, timeout=60, follow_redirects=True) as r:
                with open(music_dest, "wb") as f:
                    for chunk in r.iter_bytes(8192):
                        f.write(chunk)
            music_path = str(music_dest)

        _progress(task_id, 40, "Rendering reel")
        renderer = ReelRenderer(
            job_id=job_id,
            video_path=video_path,
            segments=segments,
            captions=captions,
            beat_timestamps=beats,
            content_type=content_type,
            template=template,
            music_file=music_path,
            music_offset=music_offset,
            aspect_ratio=aspect_ratio,
            caption_style=caption_style,
            transition_style=transition_style,
            target_duration=target_duration,
            include_hook=include_hook,
            hook_text=hook_text,
            output_dir=str(OUTPUTS_DIR),
        )

        _progress(task_id, 50, "Cutting clips")
        output_file = renderer.render()

        _progress(task_id, 85, "Adding watermark")
        watermarked = renderer.add_watermark(output_file)

        _progress(task_id, 92, "Generating thumbnail")
        thumbnail = renderer.generate_thumbnail(output_file)

        # Build public URLs for gateway to download
        base_url = os.getenv("SPACE_URL", "")  # set in HF Space secrets
        def pub(path): return f"{base_url}/outputs/{Path(path).name}"

        _set_job(task_id, {
            "state": "SUCCESS",
            "result": {
                "output_file": Path(output_file).name,
                "watermarked_file": Path(watermarked).name,
                "thumbnail_file": Path(thumbnail).name,
                "output_url": pub(output_file),
                "watermarked_url": pub(watermarked),
                "thumbnail_url": pub(thumbnail),
            }
        })
        logger.info(f"[Render] ✅ task={task_id}")

    except Exception as exc:
        logger.exception(f"[Render] ❌ task={task_id}: {exc}")
        _set_job(task_id, {"state": "FAILURE", "traceback": str(exc)})


# ── Helpers ───────────────────────────────────────────────────────────
TEMPLATE_MAP = {
    "real_estate": "real_estate_luxury", "food": "food_vibrant",
    "product": "product_showcase", "dance": "dance_beat_sync",
    "travel": "travel_cinematic",
}
HOOK_MAP = {
    "real_estate": "Your dream home awaits 🏡",
    "food": "You NEED to try this 😍",
    "product": "This changed everything for me 🔥",
}

def _suggest_template(ct): return TEMPLATE_MAP.get(ct, "generic_modern")
def _generate_hook(ct): return HOOK_MAP.get(ct, "Watch till the end 👇")
