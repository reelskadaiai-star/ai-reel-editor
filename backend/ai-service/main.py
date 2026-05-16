"""
AI Reel Editor — FastAPI entry point
Handles HTTP interface; delegates heavy work to Celery workers.
"""
import os
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from loguru import logger

from workers.celery_app import celery_app
from workers import tasks  # noqa — registers tasks

app = FastAPI(title="AI Reel Service", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOADS_DIR = Path(os.getenv("UPLOADS_DIR", "./uploads"))
OUTPUTS_DIR = Path(os.getenv("OUTPUTS_DIR", "./outputs"))


# ── Request models ────────────────────────────────────────────────────
class AnalyzeRequest(BaseModel):
    job_id: str


class RenderRequest(BaseModel):
    job_id: str
    template: str = "auto"
    music_file: str | None = None
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
    """Queue a video analysis Celery task."""
    video_path = UPLOADS_DIR / _find_file(UPLOADS_DIR, req.job_id)
    if not video_path.exists():
        # fallback: maybe jobId is the filename prefix
        raise HTTPException(404, f"Video file not found for job {req.job_id}")

    task = tasks.analyze_video.delay(req.job_id, str(video_path))
    logger.info(f"[Analyze] Queued task {task.id} for job {req.job_id}")
    return {"task_id": task.id}


@app.post("/render")
def render(req: RenderRequest):
    """Queue a reel render Celery task."""
    task = tasks.render_reel.delay(
        req.job_id,
        req.template,
        req.music_file,
        req.music_offset,
        req.aspect_ratio,
        req.caption_style,
        req.transition_style,
        req.target_duration,
        req.include_hook,
        req.hook_text,
    )
    logger.info(f"[Render] Queued task {task.id} for job {req.job_id}")
    return {"task_id": task.id}


@app.get("/task/{task_id}")
def get_task(task_id: str):
    """Proxy Celery task state for the gateway to poll."""
    result = celery_app.AsyncResult(task_id)
    response = {"state": result.state}
    if result.state == "PROGRESS":
        response["meta"] = result.info
    elif result.state == "SUCCESS":
        response["result"] = result.result
    elif result.state == "FAILURE":
        response["traceback"] = str(result.traceback)
    return response


# ── Helpers ───────────────────────────────────────────────────────────
def _find_file(directory: Path, job_id: str) -> str:
    """Find upload file whose name starts with job_id (UUID prefix)."""
    for f in directory.iterdir():
        if f.stem.startswith(job_id) or f.name.startswith(job_id):
            return f.name
    raise FileNotFoundError(f"No file for job {job_id}")
