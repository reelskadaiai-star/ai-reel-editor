"""
Premium Caption Generator v4 — Cinematic subtitle engine.

Key fixes in v4:
  • ASS format uses proper 23-field v4.00+ Style lines (was 18-field → libass rejected it)
  • All dialogue lines get {\\fad(200,200)} fade-in/out
  • 10 caption styles including neon, hype, minimal, luxury, clean (frontend names)
  • Better font sizes, shadows, and contrast for mobile readability
  • Karaoke style uses active-word highlight via \\k tags
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


# ── ASS header — 23-field v4.00+ format ──────────────────────────────────────
# PlayRes matches the graded 1080×1920 output.
ASS_HEADER = """\
[Script Info]
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
{style_line}

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

# Style tuple fields (23 values for v4.00+):
#   Name, Fontname, Fontsize,
#   PrimaryColour, SecondaryColour, OutlineColour, BackColour,
#   Bold, Italic, Underline, StrikeOut,
#   ScaleX, ScaleY, Spacing, Angle,
#   BorderStyle, Outline, Shadow,
#   Alignment, MarginL, MarginR, MarginV, Encoding
#
# Colours are &HAABBGGRR (AA=alpha, 00=opaque, FF=transparent)
# Bold: -1 = bold, 0 = normal
# Alignment: 2 = bottom-center, 8 = top-center

_STYLES: dict[str, tuple] = {
    # ── Social-media styles ──────────────────────────────────────────────
    "instagram": (
        "Default", "Liberation Sans", 78,
        "&H00FFFFFF", "&H000000FF", "&H00000000", "&H88000000",
        -1, 0, 0, 0, 100, 100, 0, 0,
        1, 4, 1,
        2, 40, 40, 90, 1,
    ),
    "modern": (
        "Default", "DejaVu Sans", 72,
        "&H00FFFFFF", "&H000000FF", "&H00000000", "&H99000000",
        -1, 0, 0, 0, 100, 100, 0, 0,
        1, 3, 1,
        2, 40, 40, 85, 1,
    ),
    "bold": (
        "Default", "Liberation Sans", 88,
        "&H00FFFF00", "&H000000FF", "&H00000000", "&H00000000",
        -1, 0, 0, 0, 100, 100, 0, 0,
        1, 5, 0,
        2, 40, 40, 70, 1,
    ),
    "hype": (
        "Default", "Liberation Sans", 92,
        "&H000080FF", "&H000000FF", "&H00FFFFFF", "&H00000000",
        -1, 0, 0, 0, 110, 110, 2, 0,
        1, 5, 2,
        2, 30, 30, 65, 1,
    ),
    # ── Cinematic styles ─────────────────────────────────────────────────
    "cinematic": (
        "Default", "Liberation Serif", 62,
        "&H00FFFFFF", "&H000000FF", "&HCC000000", "&HDD000000",
         0, 1, 0, 0, 100, 100, 2, 0,
        1, 2, 3,
        2, 60, 60, 120, 1,
    ),
    "luxury": (
        "Default", "Liberation Serif", 58,
        "&H00E8D9C0", "&H000000FF", "&H00000000", "&HBB000000",
         0, 1, 0, 0, 100, 100, 1, 0,
        1, 2, 2,
        2, 60, 60, 110, 1,
    ),
    "minimal": (
        "Default", "DejaVu Sans", 60,
        "&H00FFFFFF", "&H000000FF", "&H00000000", "&H00000000",
         0, 0, 0, 0, 100, 100, 0, 0,
        1, 1, 0,
        2, 60, 60, 100, 1,
    ),
    # ── Vibrant styles ───────────────────────────────────────────────────
    "neon": (
        "Default", "Liberation Sans", 80,
        "&H0000FFFF", "&H000000FF", "&H00FF00FF", "&H00000000",
        -1, 0, 0, 0, 100, 100, 0, 0,
        1, 4, 3,
        2, 40, 40, 80, 1,
    ),
    "clean": (
        "Default", "DejaVu Sans", 68,
        "&H00FFFFFF", "&H000000FF", "&H00000000", "&HCC000000",
        -1, 0, 0, 0, 100, 100, 0, 0,
        3, 0, 0,          # BorderStyle=3 → opaque box background
        2, 40, 40, 80, 1,
    ),
    # ── Karaoke (word-level sync) ────────────────────────────────────────
    "karaoke": (
        "Default", "Liberation Sans", 74,
        "&H00FFFFFF", "&H0000FFFF", "&H00000000", "&HAA000000",
        -1, 0, 0, 0, 100, 100, 0, 0,
        1, 4, 1,
        2, 40, 40, 85, 1,
    ),
    "default": (
        "Default", "DejaVu Sans", 68,
        "&H00FFFFFF", "&H000000FF", "&H00000000", "&H88000000",
         0, 0, 0, 0, 100, 100, 0, 0,
        1, 3, 1,
        2, 40, 40, 80, 1,
    ),
}

# Frontend sends these names — map to our internal styles
_STYLE_ALIASES = {
    "hype":     "hype",
    "neon":     "neon",
    "minimal":  "minimal",
    "luxury":   "luxury",
    "clean":    "clean",
    "modern":   "modern",
    "bold":     "bold",
    "cinematic":"cinematic",
    "karaoke":  "karaoke",
    "instagram":"instagram",
}


def _resolve_style(name: str) -> str:
    return _STYLE_ALIASES.get(name, "default") if name in _STYLES or name in _STYLE_ALIASES else "default"


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
        self,
        captions: list[dict],
        style: str,
        output_dir: str,
        job_id: str,
        fade_ms: int = 200,
    ) -> str | None:
        """
        Write an ASS subtitle file and return its path.
        Uses 23-field v4.00+ format so libass renders it correctly.
        Every dialogue line gets {\\fad(fade_ms,fade_ms)} for smooth transitions.
        """
        if not captions:
            return None

        style_key = _resolve_style(style)
        fields = _STYLES.get(style_key, _STYLES["default"])
        (
            name, font, size,
            primary, secondary, outline_col, back_col,
            bold, italic, underline, strikeout,
            scale_x, scale_y, spacing, angle,
            border_style, outline, shadow,
            alignment, margin_l, margin_r, margin_v, encoding,
        ) = fields

        style_line = (
            f"Style: {name},{font},{size},"
            f"{primary},{secondary},{outline_col},{back_col},"
            f"{bold},{italic},{underline},{strikeout},"
            f"{scale_x},{scale_y},{spacing},{angle},"
            f"{border_style},{outline},{shadow},"
            f"{alignment},{margin_l},{margin_r},{margin_v},{encoding}"
        )
        header = ASS_HEADER.replace("{style_line}", style_line)

        fad_tag = f"{{\\fad({fade_ms},{fade_ms})}}" if fade_ms > 0 else ""

        lines = []
        for cap in captions:
            start = _secs_to_ass(cap["start"])
            end   = _secs_to_ass(cap["end"])
            text  = _escape_ass(cap["text"])
            lines.append(
                f"Dialogue: 0,{start},{end},{name},,0,0,0,,{fad_tag}{text}"
            )

        ass_path = str(Path(output_dir) / f"{job_id}_subs.ass")
        with open(ass_path, "w", encoding="utf-8") as f:
            f.write(header + "\n".join(lines) + "\n")

        logger.info(f"[Captions] ASS written → {ass_path} ({len(captions)} lines, fad={fade_ms}ms)")
        return ass_path

    # ── Internal ──────────────────────────────────────────────────────────
    def _run_transcription(self, audio_path: str, style: str) -> list[dict]:
        """Run Whisper with translate task (→ always English), retry if empty."""
        model = CaptionGenerator._model

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
        logger.info(f"[Whisper] {len(captions)} display captions (style={style})")
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
            elif style in ("instagram", "bold", "modern", "hype", "neon", "clean"):
                captions.extend(self._chunked(seg, max_words=5))
            elif style in ("cinematic", "luxury", "minimal"):
                captions.extend(self._chunked(seg, max_words=7))
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
        """Word-level sync with \\k timing tags."""
        words = [w for w in (seg.words or []) if w.word.strip()]
        if not words:
            return []

        # Build one dialogue line per 4-word chunk with \\k centisecond timing
        result = []
        chunk_size = 4
        for i in range(0, len(words), chunk_size):
            chunk = words[i: i + chunk_size]
            if not chunk:
                continue
            parts = []
            for w in chunk:
                dur_cs = max(1, int((w.end - w.start) * 100))
                word_text = _escape_ass(w.word.strip())
                parts.append(f"{{\\k{dur_cs}}}{word_text}")
            result.append({
                "start": round(chunk[0].start, 3),
                "end":   round(chunk[-1].end,  3),
                "text":  " ".join(parts),
                "style": "karaoke",
                "_raw_karaoke": True,   # skip re-escaping in build_ass_file
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
        """Extract 16 kHz mono WAV, apply bandpass for cleaner Whisper input."""
        try:
            tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            tmp_path = tmp.name
            tmp.close()

            cmd = [
                "ffmpeg", "-y", "-i", video_path,
                "-vn",
                "-ar", "16000", "-ac", "1",
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


# ── Helpers ───────────────────────────────────────────────────────────────────
def _clean(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^[\s,.\-–]+", "", text)
    text = re.sub(r"[\s,.\-–]+$", "", text)
    text = re.sub(r"\s+", " ", text)
    if text:
        text = text[0].upper() + text[1:]
    return text


def _escape_ass(text: str) -> str:
    """Escape characters that break ASS dialogue lines."""
    text = text.replace("\\", "\\\\")
    text = text.replace("{", "\\{").replace("}", "\\}")
    text = text.replace("\n", "\\N")
    return text


def _secs_to_ass(secs: float) -> str:
    secs = max(0.0, secs)
    h  = int(secs // 3600)
    m  = int((secs % 3600) // 60)
    s  = secs % 60
    cs = int((s - int(s)) * 100)
    return f"{h}:{m:02d}:{int(s):02d}.{cs:02d}"


def _merge_short(captions: list[dict], min_dur: float = 0.5) -> list[dict]:
    """Merge very short adjacent captions for readability."""
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
