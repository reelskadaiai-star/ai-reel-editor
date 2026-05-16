"""
Caption generation using local OpenAI Whisper (free, runs on CPU).
No API key required.
"""
from __future__ import annotations
import os
import subprocess
import tempfile
from pathlib import Path
from loguru import logger

try:
    import whisper
    WHISPER_AVAILABLE = True
except ImportError:
    WHISPER_AVAILABLE = False
    logger.warning("whisper not installed — captions disabled")


class CaptionGenerator:
    # Cached at class level so model loads once per worker process
    _model = None
    _model_size: str = os.getenv("WHISPER_MODEL", "base")

    def __init__(self):
        if WHISPER_AVAILABLE and CaptionGenerator._model is None:
            logger.info(f"[Whisper] Loading model: {self._model_size}")
            CaptionGenerator._model = whisper.load_model(self._model_size)
            logger.info("[Whisper] Model ready")

    def transcribe(self, video_path: str) -> list[dict]:
        """
        Returns list of caption segments:
        [{start, end, text, style}]
        """
        if not WHISPER_AVAILABLE or self._model is None:
            return []

        audio_path = None
        try:
            audio_path = self._extract_audio(video_path)
            logger.info(f"[Whisper] Transcribing {Path(video_path).name}")

            result = self._model.transcribe(
                audio_path,
                task="transcribe",
                word_timestamps=True,
                verbose=False,
            )

            captions = []
            for seg in result.get("segments", []):
                text = seg["text"].strip()
                if not text:
                    continue
                captions.append({
                    "start": round(seg["start"], 3),
                    "end": round(seg["end"], 3),
                    "text": text,
                    "style": "default",
                })

            logger.info(f"[Whisper] {len(captions)} caption segments")
            return captions

        except Exception as e:
            logger.error(f"[Whisper] Transcription failed: {e}")
            return []
        finally:
            if audio_path and os.path.exists(audio_path):
                os.remove(audio_path)

    def _extract_audio(self, video_path: str) -> str:
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp_path = tmp.name
        tmp.close()

        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-vn",
            "-ar", "16000",   # Whisper expects 16 kHz
            "-ac", "1",
            tmp_path,
        ]
        r = subprocess.run(cmd, capture_output=True, timeout=120)
        if r.returncode != 0:
            raise RuntimeError(f"Audio extract failed: {r.stderr.decode()}")
        return tmp_path
