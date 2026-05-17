"""
Premium Caption Generator v3.
Always outputs English text (auto-translates Tamil, Hindi, Tanglish, etc.).
Generates ASS subtitle files for clean, styled burn-in via FFmpeg.
Supports: instagram · bold · cinematic · karaoke styles.
"""
from __future__ import annotations
import os
import re
import subprocess
import tempfile
from pathlib import Path
from loguru import logger

try:
    from faster_whisper import WhisperModel
    WHISPER_AVAILABLE = True
except ImportError:
    WHISPER_AVAILABLE = False
    logger.warning("faster-whisper not installed — captions disabled")


# ── ASS style presets ─────────────────────────────────────────────────────
# PlayRes matches the graded 1080×1920 output.
# Alignment 2 = bottom-center, 8 = top-center.
ASS_HEADER = """\
[Script Info]
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
{style_line}

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
"""

# (Name, Fontname, size, primary, outline_col, back_col, bold, outline, shadow, align, marginv)
# Using fonts available on Ubuntu/HuggingFace Space:
#   "Liberation Sans"  = metric-compatible Arial replacement
#   "DejaVu Sans"      = fallback sans-serif
#   "Liberation Serif" = metric-compatible Georgia replacement
_STYLES: dict[str, tuple] = {
    "instagram": (
        "Default", "Liberation Sans", 72,
        "&H00FFFFFF", "&H00000000", "&HAA000000",
        -1, 3, 1, 2, 80
    ),
    "bold": (
        "Default", "Liberation Sans", 80,
        "&H00FFFF00", "&H00000000", "&H00000000",
        -1, 4, 0, 2, 60
    ),
    "cinematic": (
        "Default", "Liberation Serif", 58,
        "&H00FFFFFF", "&H00000000", "&HCC000000",
         0, 2, 2, 2, 110
    ),
    "karaoke": (
        "Default", "Liberation Sans", 70,
        "&H00FFFFFF", "&H0000FFFF", "&HAA000000",
        -1, 3, 1, 2, 80
    ),
    "modern": (
        "Default", "DejaVu Sans", 68,
        "&H00FFFFFF", "&H00000000", "&H88000000",
        -1, 3, 1, 2, 80
    ),
    "default": (
        "Default", "DejaVu Sans", 64,
        "&H00FFFFFF", "&H00000000", "&H88000000",
         0, 2, 1, 2, 80
    ),
}


class CaptionGenerator:
    """
    Load once, reuse across jobs.
    Transcribes audio → English captions → ASS file ready for FFmpeg.
    """
    _model: "WhisperModel | None" = None
    _model_size: str = os.getenv("WHISPER_MODEL", "small")

    def __init__(self):
        if WHISPER_AVAILABLE and CaptionGenerator._model is None:
            for size in [self._model_size, "base"]:
                try:
                    logger.info(f"[Whisper] Loading '{size}' model …")
                    CaptionGenerator._model = WhisperModel(
                        size, device="cpu", compute_type="int8", num_workers=2
                    )
                    CaptionGenerator._model_size = size
                    logger.info(f"[Whisper] '{size}' ready")
                    break
                except Exception as e:
                    logger.warning(f"[Whisper] '{size}' failed: {e}")

    # ── Public ────────────────────────────────────────────────────────────
    def transcribe(self, video_path: str, style: str = "instagram") -> list[dict]:
        """
        Transcribe video audio → English caption list.
        Returns [{start, end, text, style}]
        Falls back through retry + smaller model.
        """
        if not WHISPER_AVAILABLE or CaptionGenerator._model is None:
            logger.warning("[Whisper] Model unavailable — no captions")
            return []

        audio_path = self._extract_audio(video_path)
        if not audio_path:
            return []

        try:
            return self._run_transcription(audio_path, style)
        except Exception as e:
            logger.error(f"[Whisper] Transcription error: {e}")
            return []
        finally:
            try:
                os.remove(audio_path)
            except Exception:
                pass

    def build_ass_file(
        self, captions: list[dict], style: str, output_dir: str, job_id: str
    ) -> str | None:
        """
        Write an ASS subtitle file and return its path.
        Returns None if captions is empty.
        """
        if not captions:
            return None

        style_key = style if style in _STYLES else "default"
        name, font, size, primary, outline_col, back_col, bold, outline, shadow, align, marginv = (
            _STYLES[style_key]
        )

        style_line = (
            f"Style: {name},{font},{size},{primary},&H000000FF,"
            f"{outline_col},{back_col},{bold},0,0,1,{outline},{shadow},"
            f"{align},30,30,{marginv},1"
        )
        header = ASS_HEADER.replace("{style_line}", style_line)

        lines = []
        for cap in captions:
            start = _secs_to_ass(cap["start"])
            end   = _secs_to_ass(cap["end"])
            text  = _escape_ass(cap["text"])
            lines.append(f"Dialogue: 0,{start},{end},{name},,0,0,0,,{text}")

        ass_path = str(Path(output_dir) / f"{job_id}_subs.ass")
        with open(ass_path, "w", encoding="utf-8") as f:
            f.write(header + "\n".join(lines) + "\n")

        logger.info(f"[Captions] ASS written → {ass_path} ({len(captions)} lines)")
        return ass_path

    # ── Internal ──────────────────────────────────────────────────────────
    def _run_transcription(self, audio_path: str, style: str) -> list[dict]:
        """Run Whisper with translate task, retry with transcribe on empty."""
        model = CaptionGenerator._model

        # Attempt 1: translate → always English output
        raw_segs, info = model.transcribe(
            audio_path,
            task="translate",
            word_timestamps=True,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 400},
            beam_size=5,
            best_of=5,
            temperature=0.0,
            condition_on_previous_text=True,
        )
        raw_segs = list(raw_segs)
        logger.info(
            f"[Whisper] lang={info.language} "
            f"(p={info.language_probability:.2f}), {len(raw_segs)} segs"
        )

        # Attempt 2: if empty (no speech or very quiet), retry with transcribe
        if not raw_segs:
            logger.warning("[Whisper] No segments — retrying with transcribe + higher temp")
            raw_segs2, _ = model.transcribe(
                audio_path,
                task="transcribe",
                word_timestamps=True,
                vad_filter=True,
                beam_size=3,
                temperature=0.4,
            )
            raw_segs = list(raw_segs2)

        if not raw_segs:
            logger.warning("[Whisper] Still no segments — returning empty")
            return []

        captions = self._build_captions(raw_segs, style)
        logger.info(f"[Whisper] {len(captions)} display captions ({style} style)")
        return captions

    def _build_captions(self, segments, style: str) -> list[dict]:
        """Convert Whisper segments to display caption dicts."""
        captions = []
        for seg in segments:
            text = _clean(seg.text)
            if not text:
                continue

            if style == "karaoke":
                captions.extend(self._karaoke(seg))
            elif style in ("instagram", "bold", "modern"):
                captions.extend(self._chunked(seg, max_words=5))
            else:
                captions.append({
                    "start": round(seg.start, 3),
                    "end":   round(seg.end,   3),
                    "text":  text,
                    "style": style,
                })

        captions = _merge_short(captions, min_dur=0.5)
        captions = _deduplicate(captions)
        return captions

    def _karaoke(self, seg) -> list[dict]:
        words = [w for w in (seg.words or []) if w.word.strip()]
        result = []
        chunk = 4
        for i in range(0, len(words), chunk):
            w = words[i: i + chunk]
            if not w:
                continue
            result.append({
                "start": round(w[0].start, 3),
                "end":   round(w[-1].end,  3),
                "text":  " ".join(x.word.strip() for x in w),
                "style": "karaoke",
            })
        return result

    def _chunked(self, seg, max_words: int = 5) -> list[dict]:
        words = [w for w in (seg.words or []) if w.word.strip()]
        if not words:
            return [{
                "start": round(seg.start, 3),
                "end":   round(seg.end,   3),
                "text":  _clean(seg.text),
                "style": "instagram",
            }]
        result = []
        for i in range(0, len(words), max_words):
            w = words[i: i + max_words]
            if not w:
                continue
            result.append({
                "start": round(w[0].start, 3),
                "end":   round(w[-1].end,  3),
                "text":  " ".join(x.word.strip() for x in w),
                "style": "instagram",
            })
        return result

    def _extract_audio(self, video_path: str) -> str | None:
        """Extract 16 kHz mono WAV, apply mild bandpass to clean speech."""
        try:
            tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            tmp_path = tmp.name
            tmp.close()

            cmd = [
                "ffmpeg", "-y", "-i", video_path,
                "-vn",
                "-ar", "16000", "-ac", "1",
                # Bandpass 80–8000 Hz cleans rumble and high-freq noise for Whisper
                "-af", "highpass=f=80,lowpass=f=8000,dynaudnorm",
                tmp_path,
            ]
            r = subprocess.run(cmd, capture_output=True, timeout=180)
            if r.returncode != 0:
                logger.error(f"[Whisper] Audio extract failed: {r.stderr.decode()[-300:]}")
                return None
            return tmp_path
        except Exception as e:
            logger.error(f"[Whisper] Audio extract error: {e}")
            return None


# ── Helpers ───────────────────────────────────────────────────────────────
def _clean(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^[\s,.\-–]+", "", text)
    text = re.sub(r"[\s,.\-–]+$", "", text)
    text = re.sub(r"\s+", " ", text)
    if text:
        text = text[0].upper() + text[1:]
    return text


def _escape_ass(text: str) -> str:
    """Escape characters that break ASS format."""
    text = text.replace("\\", "\\\\")
    text = text.replace("{", "\\{").replace("}", "\\}")
    text = text.replace("\n", "\\N")
    return text


def _secs_to_ass(secs: float) -> str:
    secs = max(0.0, secs)
    h = int(secs // 3600)
    m = int((secs % 3600) // 60)
    s = secs % 60
    cs = int((s - int(s)) * 100)
    return f"{h}:{m:02d}:{int(s):02d}.{cs:02d}"


def _merge_short(captions: list[dict], min_dur: float = 0.5) -> list[dict]:
    """Merge very short adjacent captions so they're readable."""
    if not captions:
        return []
    merged = []
    buf = captions[0].copy()
    for cap in captions[1:]:
        dur = buf["end"] - buf["start"]
        gap = cap["start"] - buf["end"]
        if dur < min_dur and gap < 0.4:
            buf["text"] = buf["text"] + " " + cap["text"]
            buf["end"]  = cap["end"]
        else:
            if buf["text"].strip():
                merged.append(buf)
            buf = cap.copy()
    if buf["text"].strip():
        merged.append(buf)
    return merged


def _deduplicate(captions: list[dict]) -> list[dict]:
    """Remove consecutive duplicate texts (Whisper hallucination artefact)."""
    if not captions:
        return []
    out = [captions[0]]
    for cap in captions[1:]:
        if cap["text"].strip().lower() != out[-1]["text"].strip().lower():
            out.append(cap)
    return out
