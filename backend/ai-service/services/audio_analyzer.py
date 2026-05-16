"""
Audio analysis: beat detection using librosa.
Extracts audio from video via FFmpeg, then analyses tempo & beats.
"""
from __future__ import annotations
import os
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from loguru import logger

try:
    import librosa
    LIBROSA_AVAILABLE = True
except ImportError:
    LIBROSA_AVAILABLE = False
    logger.warning("librosa not installed — beat detection disabled")


class AudioAnalyzer:
    def __init__(self, video_path: str, sr: int = 22050):
        self.video_path = video_path
        self.sr = sr
        self._audio_path: str | None = None

    def detect_beats(self) -> list[float]:
        """
        Returns list of beat timestamps in seconds.
        Falls back to evenly-spaced beats at 120 BPM if audio extraction fails.
        """
        if not LIBROSA_AVAILABLE:
            return self._fallback_beats()

        try:
            audio_path = self._extract_audio()
            y, sr = librosa.load(audio_path, sr=self.sr, mono=True)
            tempo, beats = librosa.beat.beat_track(y=y, sr=sr, units="time")
            logger.info(f"[Audio] Tempo={tempo:.1f} BPM, {len(beats)} beats")
            return [round(float(b), 3) for b in beats]
        except Exception as e:
            logger.warning(f"[Audio] Beat detection failed: {e} — using fallback")
            return self._fallback_beats()
        finally:
            self._cleanup()

    def _extract_audio(self) -> str:
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        self._audio_path = tmp.name
        tmp.close()

        cmd = [
            "ffmpeg", "-y",
            "-i", self.video_path,
            "-vn",                         # no video
            "-acodec", "pcm_s16le",
            "-ar", str(self.sr),
            "-ac", "1",                    # mono
            self._audio_path,
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=60)
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg audio extract failed: {result.stderr.decode()}")
        return self._audio_path

    def _fallback_beats(self, bpm: float = 120.0) -> list[float]:
        """Generate evenly-spaced beats assuming 120 BPM."""
        import cv2
        cap = cv2.VideoCapture(self.video_path)
        total_frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        cap.release()
        duration = total_frames / fps
        beat_interval = 60.0 / bpm
        return [round(i * beat_interval, 3) for i in range(int(duration / beat_interval))]

    def _cleanup(self):
        if self._audio_path and os.path.exists(self._audio_path):
            os.remove(self._audio_path)
            self._audio_path = None
