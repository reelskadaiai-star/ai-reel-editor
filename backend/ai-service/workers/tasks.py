"""
Celery tasks — orchestrate the AI pipeline.
Each task updates its own state so the gateway can poll progress.
"""
import os
from pathlib import Path
from celery import current_task
from loguru import logger

from workers.celery_app import celery_app
from services.scene_detector import SceneDetector
from services.content_classifier import ContentClassifier
from services.audio_analyzer import AudioAnalyzer
from services.caption_generator import CaptionGenerator
from services.reel_renderer import ReelRenderer

UPLOADS_DIR = Path(os.getenv("UPLOADS_DIR", "./uploads"))
OUTPUTS_DIR = Path(os.getenv("OUTPUTS_DIR", "./outputs"))
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)


def _progress(percent: int, message: str):
    current_task.update_state(state="PROGRESS", meta={"percent": percent, "message": message})


@celery_app.task(bind=True, name="workers.tasks.analyze_video", max_retries=2)
def analyze_video(self, job_id: str, video_path: str):
    logger.info(f"[Task] analyze_video start — job={job_id}")
    try:
        _progress(5, "Detecting scenes")
        scene_detector = SceneDetector(video_path)
        scenes = scene_detector.detect()
        duration = scene_detector.duration

        _progress(20, "Classifying content type")
        classifier = ContentClassifier()
        content_type, confidence, dominant_colors = classifier.classify(video_path, scenes)

        _progress(35, "Analyzing audio & beats")
        audio_analyzer = AudioAnalyzer(video_path)
        beat_timestamps = audio_analyzer.detect_beats()

        _progress(50, "Generating captions")
        caption_gen = CaptionGenerator()
        captions = caption_gen.transcribe(video_path)

        _progress(70, "Scoring highlights")
        segments = scene_detector.score_segments(beat_timestamps, content_type)

        _progress(85, "Selecting template & hook text")
        template = _suggest_template(content_type)
        hook_text = _generate_hook(content_type, captions)

        _progress(100, "Analysis complete")

        return {
            "content_type": content_type,
            "confidence": float(confidence),
            "segments": segments,
            "captions": captions,
            "beat_timestamps": beat_timestamps,
            "dominant_colors": dominant_colors,
            "scene_count": len(scenes),
            "duration": duration,
            "suggested_template": template,
            "hook_text": hook_text,
        }

    except Exception as exc:
        logger.exception(f"[Task] analyze_video failed — job={job_id}: {exc}")
        raise self.retry(exc=exc, countdown=10)


@celery_app.task(bind=True, name="workers.tasks.render_reel", max_retries=1)
def render_reel(
    self,
    job_id: str,
    template: str,
    music_file: str | None,
    music_offset: float,
    aspect_ratio: str,
    caption_style: str,
    transition_style: str,
    target_duration: int,
    include_hook: bool,
    hook_text: str | None,
):
    logger.info(f"[Task] render_reel start — job={job_id}, template={template}")
    try:
        # Find source video
        video_path = _find_input(job_id)

        _progress(5, "Loading analysis results")
        # In a real system, fetch persisted analysis from DB/Redis cache.
        # Here we re-run a fast scene detect to get segments.
        scene_detector = SceneDetector(str(video_path))
        scenes = scene_detector.detect()
        classifier = ContentClassifier()
        content_type, _, _ = classifier.classify(str(video_path), scenes)
        audio_analyzer = AudioAnalyzer(str(video_path))
        beat_timestamps = audio_analyzer.detect_beats()
        caption_gen = CaptionGenerator()
        captions = caption_gen.transcribe(str(video_path))
        segments = scene_detector.score_segments(beat_timestamps, content_type)

        _progress(40, "Rendering reel")
        renderer = ReelRenderer(
            job_id=job_id,
            video_path=str(video_path),
            segments=segments,
            captions=captions,
            beat_timestamps=beat_timestamps,
            content_type=content_type,
            template=template,
            music_file=str(UPLOADS_DIR / music_file) if music_file else None,
            music_offset=music_offset,
            aspect_ratio=aspect_ratio,
            caption_style=caption_style,
            transition_style=transition_style,
            target_duration=target_duration,
            include_hook=include_hook,
            hook_text=hook_text,
            output_dir=str(OUTPUTS_DIR),
        )

        _progress(45, "Cutting & stitching clips")
        output_file = renderer.render()

        _progress(85, "Adding watermark")
        watermarked_file = renderer.add_watermark(output_file)

        _progress(92, "Generating thumbnail")
        thumbnail_file = renderer.generate_thumbnail(output_file)

        _progress(100, "Done")
        logger.info(f"[Task] render_reel done — job={job_id} → {output_file}")

        return {
            "output_file": Path(output_file).name,
            "watermarked_file": Path(watermarked_file).name,
            "thumbnail_file": Path(thumbnail_file).name,
        }

    except Exception as exc:
        logger.exception(f"[Task] render_reel failed — job={job_id}: {exc}")
        raise self.retry(exc=exc, countdown=15)


# ── Helpers ───────────────────────────────────────────────────────────
def _find_input(job_id: str) -> Path:
    for f in UPLOADS_DIR.iterdir():
        if f.stem.startswith(job_id) or f.name.startswith(job_id):
            return f
    raise FileNotFoundError(f"Upload file not found for job {job_id}")


TEMPLATE_MAP = {
    "real_estate": "real_estate_luxury",
    "food": "food_vibrant",
    "product": "product_showcase",
    "dance": "dance_beat_sync",
    "travel": "travel_cinematic",
    "vlog": "vlog_trendy",
    "interview": "interview_clean",
    "cinematic": "cinematic_epic",
    "comedy": "comedy_fast",
}

HOOK_TEMPLATES = {
    "real_estate": ["Your dream home awaits 🏡", "This listing won't last long 🔑", "Step inside luxury ✨"],
    "food": ["You NEED to try this 😍", "The most satisfying thing you'll see today 🤤", "Recipe reveal incoming 👇"],
    "product": ["This changed everything for me 🔥", "Why didn't I find this sooner? 😭", "POV: You just levelled up ⚡"],
    "dance": ["She said 'just one take' 😂", "This transition is INSANE 🤯", "Drop the song name below 👇"],
}


def _suggest_template(content_type: str) -> str:
    return TEMPLATE_MAP.get(content_type, "generic_modern")


def _generate_hook(content_type: str, captions: list) -> str:
    import random
    hooks = HOOK_TEMPLATES.get(content_type, ["Watch till the end 👇", "You won't believe this 🔥"])
    return random.choice(hooks)
