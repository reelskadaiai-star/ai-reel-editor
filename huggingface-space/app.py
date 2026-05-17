"""
ReelAI — HuggingFace Space AI Service
Runs on port 7860 (HF Spaces requirement).
Uses threading instead of Celery — no Redis needed.
Jobs stored in memory; results served as static files.
"""
import os
import uuid
import threading
import subprocess
from pathlib import Path
from typing import List

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
app = FastAPI(title="ReelAI HF Space", version="2.0.0")

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Serve output files (renders, thumbnails, watermarked)
app.mount("/outputs", StaticFiles(directory=str(OUTPUTS_DIR)), name="outputs")


# ── Request models ────────────────────────────────────────────────────
class AnalyzeRequest(BaseModel):
    job_id: str
    video_url: str
    extra_video_urls: List[str] = []   # additional clips for multi-upload merge


class RenderRequest(BaseModel):
    job_id: str
    video_url: str
    extra_video_urls: List[str] = []
    template: str = "auto"
    music_url: str | None = None
    music_offset: float = 0.0
    aspect_ratio: str = "9:16"
    caption_style: str = "modern"
    transition_style: str = "fade"
    transition_duration: float = 0.3
    target_duration: int = 30
    include_hook: bool = True
    hook_text: str | None = None
    mute_audio: bool = False
    logo_url: str | None = None
    logo_position: str = "bottom_right"
    cta_text: str | None = "Follow for more 🔥"
    speed_ramp: bool = False
    zoom_punch: bool = True


# ── Routes ────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {"status": "ok", "version": "2.0.0"}


@app.post("/analyze")
def analyze(req: AnalyzeRequest):
    task_id = str(uuid.uuid4())
    _set_job(task_id, {"state": "STARTED"})
    t = threading.Thread(
        target=_run_analyze,
        args=(task_id, req.job_id, req.video_url, req.extra_video_urls),
        daemon=True,
    )
    t.start()
    logger.info(f"[Analyze] task={task_id} job={req.job_id} clips={1 + len(req.extra_video_urls)}")
    return {"task_id": task_id}


@app.post("/render")
def render(req: RenderRequest):
    task_id = str(uuid.uuid4())
    _set_job(task_id, {"state": "STARTED"})
    t = threading.Thread(
        target=_run_render,
        args=(
            task_id, req.job_id, req.video_url, req.extra_video_urls,
            req.template, req.music_url, req.music_offset,
            req.aspect_ratio, req.caption_style,
            req.transition_style, req.transition_duration,
            req.target_duration, req.include_hook, req.hook_text,
            req.mute_audio, req.logo_url, req.logo_position,
            req.cta_text, req.speed_ramp, req.zoom_punch,
        ),
        daemon=True,
    )
    t.start()
    logger.info(f"[Render] task={task_id} job={req.job_id}")
    return {"task_id": task_id}


@app.get("/task/{task_id}")
def get_task(task_id: str):
    return _get_job(task_id)


# ── Background workers ─────────────────────────────────────────────────
def _download_file(url: str, dest: Path) -> Path:
    """Download any file from a URL if not already cached."""
    if dest.exists():
        return dest
    logger.info(f"Downloading {url} → {dest}")
    with httpx.stream("GET", url, timeout=300, follow_redirects=True) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_bytes(chunk_size=8192):
                f.write(chunk)
    return dest


def _download_video(video_url: str, job_id: str, suffix: str = "") -> Path:
    """Download primary video."""
    ext = Path(video_url).suffix or ".mp4"
    dest = UPLOADS_DIR / f"{job_id}{suffix}{ext}"
    return _download_file(video_url, dest)


def _merge_clips(clip_paths: list[str], job_id: str) -> str:
    """Concatenate multiple video files into one using FFmpeg concat demuxer."""
    if len(clip_paths) == 1:
        return clip_paths[0]

    out = str(UPLOADS_DIR / f"{job_id}_merged.mp4")
    list_file = str(UPLOADS_DIR / f"{job_id}_merge_list.txt")

    with open(list_file, "w") as f:
        for p in clip_paths:
            f.write(f"file '{p}'\n")

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", list_file,
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
        out,
    ]
    result = subprocess.run(cmd, capture_output=True, timeout=300)
    if result.returncode != 0:
        logger.warning(f"Merge failed: {result.stderr.decode()[-1000:]}, using first clip only")
        return clip_paths[0]

    try:
        os.remove(list_file)
    except Exception:
        pass

    return out


def _run_analyze(task_id: str, job_id: str, video_url: str, extra_video_urls: list[str]):
    try:
        # Download all clips
        _progress(task_id, 5, f"Downloading {1 + len(extra_video_urls)} clip(s)")
        primary_path = str(_download_video(video_url, job_id))

        extra_paths = []
        for i, url in enumerate(extra_video_urls):
            p = _download_video(url, job_id, suffix=f"_clip{i+1}")
            extra_paths.append(str(p))

        # Merge if multi-upload
        if extra_paths:
            _progress(task_id, 12, "Merging clips")
            video_path = _merge_clips([primary_path] + extra_paths, job_id)
        else:
            video_path = primary_path

        _progress(task_id, 18, "Detecting scenes")
        detector = SceneDetector(video_path)
        scenes = detector.detect()
        duration = detector.duration

        _progress(task_id, 32, "Classifying content")
        classifier = ContentClassifier()
        content_type, confidence, dominant_colors = classifier.classify(video_path, scenes)

        _progress(task_id, 47, "Analysing audio & beats")
        audio = AudioAnalyzer(video_path)
        beats = audio.detect_beats()

        _progress(task_id, 62, "Generating captions")
        captions = CaptionGenerator().transcribe(video_path)
        captions_auto = False
        if not captions:
            _progress(task_id, 70, "No speech — generating content captions")
            captions = _generate_content_captions(content_type, beats, duration)
            captions_auto = True
            logger.info(f"[Analyze] Auto-generated {len(captions)} captions for {content_type}")

        _progress(task_id, 78, "Scoring highlights")
        segments = detector.score_segments(beats, content_type)

        _progress(task_id, 90, "Building result")
        template = _suggest_template(content_type)
        hook_options = _generate_hook_options(content_type)
        cta_text = _generate_cta(content_type)

        _set_job(task_id, {
            "state": "SUCCESS",
            "result": {
                "content_type": content_type,
                "confidence": float(confidence),
                "segments": segments,
                "captions": captions,
                "captions_auto_generated": captions_auto,
                "beat_timestamps": beats,
                "dominant_colors": dominant_colors,
                "scene_count": len(scenes),
                "duration": duration,
                "suggested_template": template,
                "hook_text": hook_options[0],
                "hook_text_options": hook_options,
                "cta_text": cta_text,
            }
        })
        logger.info(f"[Analyze] ✅ task={task_id} type={content_type} conf={confidence:.0%}")

    except Exception as exc:
        logger.exception(f"[Analyze] ❌ task={task_id}: {exc}")
        _set_job(task_id, {"state": "FAILURE", "traceback": str(exc)})


def _run_render(
    task_id, job_id, video_url, extra_video_urls,
    template, music_url, music_offset,
    aspect_ratio, caption_style,
    transition_style, transition_duration,
    target_duration, include_hook, hook_text,
    mute_audio=False, logo_url=None, logo_position="bottom_right",
    cta_text=None, speed_ramp=False, zoom_punch=True,
):
    try:
        _progress(task_id, 5, f"Downloading {1 + len(extra_video_urls)} clip(s)")
        primary_path = str(_download_video(video_url, job_id))
        extra_paths = [
            str(_download_video(url, job_id, suffix=f"_clip{i+1}"))
            for i, url in enumerate(extra_video_urls)
        ]

        if extra_paths:
            _progress(task_id, 12, "Merging clips")
            video_path = _merge_clips([primary_path] + extra_paths, job_id)
        else:
            video_path = primary_path

        _progress(task_id, 18, "Re-analysing for render")
        detector = SceneDetector(video_path)
        scenes = detector.detect()
        duration = detector.duration
        classifier = ContentClassifier()
        content_type, _, _ = classifier.classify(video_path, scenes)
        beats = AudioAnalyzer(video_path).detect_beats()
        captions = CaptionGenerator().transcribe(video_path)
        if not captions:
            captions = _generate_content_captions(content_type, beats, duration)
            logger.info(f"[Render] Auto-generated {len(captions)} captions for {content_type}")
        segments = detector.score_segments(beats, content_type)

        # Download music
        music_path = None
        if music_url:
            music_dest = UPLOADS_DIR / f"{job_id}_music.mp3"
            try:
                _download_file(music_url, music_dest)
                music_path = str(music_dest)
            except Exception as e:
                logger.warning(f"Music download failed: {e}")

        # Download logo
        logo_path = None
        if logo_url:
            logo_ext = Path(logo_url).suffix or ".png"
            logo_dest = UPLOADS_DIR / f"{job_id}_logo{logo_ext}"
            try:
                _download_file(logo_url, logo_dest)
                logo_path = str(logo_dest)
            except Exception as e:
                logger.warning(f"Logo download failed: {e}")

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
            transition_duration=transition_duration,
            target_duration=target_duration,
            include_hook=include_hook,
            hook_text=hook_text,
            output_dir=str(OUTPUTS_DIR),
            mute_audio=mute_audio,
            logo_file=logo_path,
            logo_position=logo_position,
            cta_text=cta_text,
            speed_ramp=speed_ramp,
            zoom_punch=zoom_punch,
        )

        _progress(task_id, 52, "Cutting & grading clips")
        output_file = renderer.render()

        _progress(task_id, 85, "Adding watermark")
        watermarked = renderer.add_watermark(output_file)

        _progress(task_id, 93, "Generating thumbnail")
        thumbnail = renderer.generate_thumbnail(output_file)

        base_url = os.getenv("SPACE_URL", "")
        def pub(p): return f"{base_url}/outputs/{Path(p).name}"

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
    "real_estate": "real_estate_luxury",
    "food":        "food_vibrant",
    "product":     "product_showcase",
    "dance":       "dance_beat_sync",
    "travel":      "travel_cinematic",
    "nature":      "nature_relaxing",
    "fitness":     "fitness_hype",
    "education":   "education_clean",
    "lifestyle":   "lifestyle_aesthetic",
    "vlog":        "vlog_dynamic",
    "comedy":      "comedy_punchy",
    "interview":   "interview_minimal",
    "cinematic":   "cinematic_epic",
}

HOOK_OPTIONS: dict[str, list[str]] = {
    "real_estate":  ["Your dream home awaits 🏡", "This property won't last long 😱", "POV: You just found your dream home ✨"],
    "food":         ["You NEED to try this 😍", "This recipe changed my life 🔥", "Wait for that money shot… 👀"],
    "product":      ["This changed everything for me 🔥", "I can't believe this actually works 😤", "The product everyone is talking about 👇"],
    "dance":        ["This transition 🔥🔥🔥", "How is this even possible?? 😱", "POV: You just learned this move ✨"],
    "travel":       ["You won't believe this place exists 😱", "Add this to your bucket list NOW 🌍", "POV: Living abroad ✈️"],
    "nature":       ["This plant is so satisfying 🌿", "Nature's most stunning creation 🌱", "Did you know plants can feel? 🌸"],
    "fitness":      ["This workout changed my body 💪", "30 days of this = results 🔥", "No excuses after watching this 😤"],
    "education":    ["Learn this in 60 seconds 🧠", "I wish I knew this sooner 💡", "This knowledge is worth millions 📚"],
    "lifestyle":    ["POV: Living your best life ✨", "This is the routine that changed everything 🌟", "Small habits, massive results 💫"],
    "vlog":         ["Come with me 🎬", "A day in my life 📍", "You have to see this…👀"],
    "comedy":       ["Wait for it… 😂", "I cannot 💀💀💀", "The ending killed me 😭"],
    "interview":    ["This advice changed my life 💡", "You need to hear this 🎙️", "The truth about success 🔑"],
    "cinematic":    ["Captured this by accident 🎥", "This moment is everything ✨", "The shot everyone is talking about 🎬"],
    "unknown":      ["Watch till the end 👇", "This is unbelievable 😱", "You've never seen anything like this 🔥"],
}

CTA_MAP = {
    "real_estate":  "DM for a private tour 🏡",
    "food":         "Recipe in bio 🍽️",
    "product":      "Link in bio 🛒",
    "dance":        "Follow for more moves 🕺",
    "travel":       "Follow for more hidden gems 🌍",
    "nature":       "Follow for plant tips 🌿",
    "fitness":      "Full program in bio 💪",
    "education":    "Follow for daily tips 🧠",
    "lifestyle":    "Follow my journey ✨",
    "vlog":         "Subscribe for more 🎬",
    "comedy":       "Follow for more 😂",
    "interview":    "More interviews in bio 🎙️",
    "cinematic":    "Behind the scenes in bio 🎥",
    "unknown":      "Follow for more 🔥",
}


def _suggest_template(ct): return TEMPLATE_MAP.get(ct, "generic_modern")
def _generate_hook_options(ct): return HOOK_OPTIONS.get(ct, HOOK_OPTIONS["unknown"])
def _generate_cta(ct): return CTA_MAP.get(ct, "Follow for more 🔥")


# ── Auto-caption pools (shown when no speech detected) ────────────────
# Short punchy overlays timed to beats — 3-6 words, visual-only context
CAPTION_POOLS: dict[str, list[str]] = {
    "real_estate": [
        "Prime location 📍",
        "Dream kitchen ✨",
        "Stunning views 🌅",
        "Open plan living 🏡",
        "High ceilings ↕️",
        "Natural light 🌤️",
        "Brand new build 🔑",
        "Move-in ready ✅",
        "Luxury finishes 💎",
        "Book a tour today 👇",
    ],
    "food": [
        "Watch closely 👀",
        "Secret ingredient 🤫",
        "The flip 🍳",
        "Golden brown ✨",
        "Almost ready… ⏱️",
        "The money shot 😍",
        "Crispy perfection 🔥",
        "Taste this 👇",
        "Just like that ✨",
        "Chef's kiss 🤌",
    ],
    "product": [
        "Look at this 👀",
        "Game changer 🔥",
        "Premium quality ✨",
        "Worth every penny 💯",
        "The details 🔍",
        "You need this 👇",
        "Obsessed 😍",
        "Before & after ↕️",
        "Limited stock ⚡",
        "Link in bio 🛒",
    ],
    "dance": [
        "The transition 🔥",
        "Clean footwork 💨",
        "Hit the beat 🎵",
        "Smooth 🌊",
        "Level up 📈",
        "Feel the music 🎶",
        "Locked in 🎯",
        "The drop 💥",
        "Full send 🚀",
        "Tutorial coming 👇",
    ],
    "travel": [
        "Hidden gem 💎",
        "You need to go 🌍",
        "Worth the flight ✈️",
        "Unreal views 😱",
        "Local secret 🤫",
        "Golden hour 🌅",
        "Off the map 📍",
        "Add to bucket list ✅",
        "No filter needed ✨",
        "More details in bio 👇",
    ],
    "nature": [
        "Water when soil is dry 💧",
        "Bright indirect light ☀️",
        "Native to tropical regions 🌍",
        "Air-purifying plant 🌬️",
        "Grows up to 3ft tall 📏",
        "Toxic to pets 🐾 — keep away",
        "Mist leaves weekly 🌫️",
        "Repot every 2 years 🪴",
        "Propagates easily in water 💧",
        "One of the easiest to grow ✅",
        "Low maintenance & stunning 🌿",
        "Did you know it blooms once a year? 🌸",
        "Thrives in humid environments 🌴",
        "Fertilise monthly in summer 🌱",
        "New leaf = plant is happy 💚",
    ],
    "fitness": [
        "Feel the burn 🔥",
        "No days off 💪",
        "Rep 1 of many 📈",
        "Form is everything ✅",
        "Mind-muscle connection 🧠",
        "Push through it 💥",
        "Results don't lie 📊",
        "60 days of this 🗓️",
        "Full routine in bio 👇",
        "You vs you 🏆",
    ],
    "education": [
        "Did you know? 🧠",
        "Step 1 👆",
        "Step 2 ✌️",
        "Step 3 🤟",
        "Pro tip 💡",
        "Most people miss this ⚠️",
        "The secret 🤫",
        "Game changer 🔥",
        "Save this 🔖",
        "Follow for more 👇",
    ],
    "lifestyle": [
        "Morning routine ☀️",
        "This changed everything ✨",
        "Small habit 📈",
        "Daily non-negotiable ✅",
        "Level up your life 🚀",
        "Consistency is key 🔑",
        "The glow-up 💫",
        "Aesthetic 🤍",
        "Balance 🧘",
        "More on my page 👇",
    ],
    "vlog": [
        "A day in the life 📍",
        "Morning ☀️",
        "Afternoon 🌤️",
        "Evening 🌙",
        "Unexpected 😳",
        "The highlight 🌟",
        "Real moment 🎬",
        "Unfiltered 🤍",
        "New vlog out 👇",
        "Come with me 🎒",
    ],
    "comedy": [
        "POV: 👀",
        "Me every morning 😭",
        "Not me… 💀",
        "The audacity 😤",
        "Wait for it ⏳",
        "Every. Single. Time. 🙄",
        "No way 😱",
        "We've all been here 😂",
        "I cannot 💀",
        "Tag someone 👇",
    ],
    "interview": [
        "Golden advice 💡",
        "Write this down 📝",
        "Key insight 🔑",
        "Changed my mindset 🧠",
        "Unpopular opinion 🗣️",
        "The truth 💯",
        "This hit different 🎯",
        "Share this 🔁",
        "Full interview in bio 👇",
        "Bookmark this 🔖",
    ],
    "cinematic": [
        "Shot on location 📍",
        "Golden hour 🌅",
        "No edits ✨",
        "Natural light 🌤️",
        "The moment 🎬",
        "Unscripted 🤍",
        "Raw beauty 🌿",
        "Frame by frame 🎞️",
        "Behind the scenes in bio 👇",
        "More like this 📸",
    ],
    "unknown": [
        "Watch till the end 👀",
        "Unexpected 😱",
        "Trust the process ✨",
        "The reveal 🔓",
        "Worth it 💯",
        "You won't regret it 🔥",
        "Save this 🔖",
        "Share with a friend 👇",
        "Real talk 🎯",
        "More coming 📲",
    ],
}


def _generate_content_captions(
    content_type: str,
    beats: list[float],
    duration: float,
    caption_hold: float = 2.5,
) -> list[dict]:
    """
    Generate contextual text overlays for silent videos.

    Strategy:
    - Pick phrases from the content-type pool in order.
    - Space them across the video, snapping to beats where available.
    - Each caption is shown for `caption_hold` seconds.
    - Target ~1 caption every 3 seconds (so ~10 for a 30s reel).
    """
    import random

    pool = CAPTION_POOLS.get(content_type, CAPTION_POOLS["unknown"])
    # Shuffle a copy so captions vary between renders
    phrases = pool[:]
    random.shuffle(phrases)

    if duration <= 0:
        duration = 30.0

    # Decide how many captions to show — 1 every ~3 s
    n = max(3, min(len(phrases), int(duration / 3)))

    # Evenly space target times across the video (skip first & last 2s)
    start_offset = 2.0
    end_offset = duration - 2.5
    span = max(1.0, end_offset - start_offset)
    step = span / n

    result = []
    for i in range(n):
        ideal_t = start_offset + i * step

        # Snap to nearest beat within a ±1.5 s window
        if beats:
            candidates = [b for b in beats if abs(b - ideal_t) <= 1.5]
            t = min(candidates, key=lambda b: abs(b - ideal_t)) if candidates else ideal_t
        else:
            t = ideal_t

        end_t = min(t + caption_hold, duration - 0.2)
        result.append({
            "start": round(t, 2),
            "end":   round(end_t, 2),
            "text":  phrases[i % len(phrases)],
            "style": "bold",   # eye-catching default for silent videos
        })

    # Sort chronologically (beat-snapping can shuffle order slightly)
    result.sort(key=lambda c: c["start"])
    return result
