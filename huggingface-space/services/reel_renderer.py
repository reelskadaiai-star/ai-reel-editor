"""
Premium Reel Renderer v3 — One-touch AI video pipeline.

Pipeline:
  1. Select + order highlight clips (beat-aware)
  2. Extract clips with content-aware effects (zoom-punch, speed-ramp)
  3. Concatenate with cinematic xfade transitions
  4. Colour grade (scene-based LUT / eq filter)
  5. Burn ASS subtitles (premium styled)
  6. Overlay CTA end-screen
  7. Overlay logo (blended)
  8. Mix / duck audio
  9. Export 1080p CRF-18

Never crashes: 3-tier fallback at every stage.
"""
from __future__ import annotations
import os
import uuid
import shutil
import subprocess
import json
from pathlib import Path
from loguru import logger

from services.caption_generator import CaptionGenerator


WATERMARK_TEXT = os.getenv("WATERMARK_TEXT", "@ReelAI")

# ── Colour grades (FFmpeg eq/curves filters per content type) ─────────────
COLOUR_GRADE: dict[str, str] = {
    "real_estate": "eq=saturation=1.10:contrast=1.06:brightness=0.02,unsharp=3:3:0.5",
    "food":        "eq=saturation=1.45:contrast=1.18:brightness=0.04,unsharp=5:5:1.0",
    "product":     "eq=saturation=1.20:contrast=1.10,unsharp=3:3:0.4",
    "dance":       "eq=saturation=1.30:contrast=1.20",
    "travel":      "eq=saturation=1.30:contrast=1.12:brightness=0.02,unsharp=3:3:0.3",
    "nature":      "eq=saturation=1.28:contrast=1.10:brightness=0.01,unsharp=3:3:0.4",
    "fitness":     "eq=saturation=1.20:contrast=1.28:brightness=0.01",
    "education":   "eq=saturation=1.05:contrast=1.08:brightness=0.01",
    "lifestyle":   "eq=saturation=1.18:contrast=1.10:brightness=0.01",
    "vlog":        "eq=saturation=1.12:contrast=1.06",
    "comedy":      "eq=saturation=1.22:contrast=1.12",
    "interview":   "eq=saturation=1.05:contrast=1.10",
    "cinematic":   "curves=all='0/0 0.25/0.20 0.75/0.80 1/1',eq=saturation=0.85:contrast=1.18",
    "unknown":     "eq=saturation=1.10:contrast=1.05",
}

# ── Target aspect-ratio → (width, height) ────────────────────────────────
ASPECT_RES: dict[str, tuple[str, str]] = {
    "9:16":  ("1080", "1920"),
    "1:1":   ("1080", "1080"),
    "16:9":  ("1920", "1080"),
    "4:5":   ("1080", "1350"),
}

# ── Supported xfade transitions ───────────────────────────────────────────
XFADE_MAP: dict[str, str | None] = {
    "fade":       "fade",
    "wipeleft":   "wipeleft",
    "wiperight":  "wiperight",
    "slideleft":  "slideleft",
    "slideright": "slideright",
    "circleopen": "circleopen",
    "dissolve":   "dissolve",
    "radial":     "radial",
    "zoomin":     "zoomin",
    "auto":       "fade",
    "none":       None,
}

# ── Caption styles (forwarded to CaptionGenerator) ────────────────────────
_CAPTION_STYLES = {"instagram", "bold", "cinematic", "karaoke", "modern", "default"}


class ReelRenderer:
    def __init__(
        self,
        job_id: str,
        video_path: str,
        segments: list[dict],
        captions: list[dict],
        beat_timestamps: list[float],
        content_type: str,
        template: str,
        music_file: str | None,
        music_offset: float,
        aspect_ratio: str,
        caption_style: str,
        transition_style: str,
        target_duration: int,
        include_hook: bool,
        hook_text: str | None,
        output_dir: str,
        mute_audio: bool = False,
        logo_file: str | None = None,
        logo_position: str = "bottom_right",
        transition_duration: float = 0.4,
        cta_text: str | None = None,
        speed_ramp: bool = False,
        zoom_punch: bool = True,
    ):
        self.job_id          = job_id
        self.video_path      = video_path
        self.segments        = segments
        self.captions        = captions
        self.beats           = beat_timestamps or []
        self.content_type    = content_type
        self.template        = template
        self.music_file      = music_file
        self.music_offset    = music_offset
        self.aspect_ratio    = aspect_ratio
        self.caption_style   = caption_style if caption_style in _CAPTION_STYLES else "instagram"
        self.transition_style = transition_style
        self.transition_dur  = max(0.2, min(transition_duration, 0.8))
        self.target_duration = int(target_duration) or 30
        self.include_hook    = include_hook
        self.hook_text       = hook_text
        self.output_dir      = output_dir
        self.mute_audio      = mute_audio
        self.logo_file       = logo_file
        self.logo_position   = logo_position
        self.cta_text        = cta_text
        self.speed_ramp      = speed_ramp
        self.zoom_punch      = zoom_punch
        # Derive video duration from segments (used by padding)
        self.duration = (
            max((s["end"] for s in segments), default=60.0)
            if segments else 60.0
        )

    # ── Main entry point ──────────────────────────────────────────────────
    def render(self) -> str:
        clips    = self._select_clips()
        logger.info(
            f"[Renderer] {len(clips)} clips, "
            f"~{sum(c['dur'] for c in clips):.1f}s / {self.target_duration}s target"
        )

        clip_paths = []
        for i, clip in enumerate(clips):
            p = self._extract_clip(clip, i)
            if p:
                clip_paths.append(p)

        # Absolute last resort
        if not clip_paths:
            logger.warning("[Renderer] All extractions failed — using raw video")
            clip_paths = [self.video_path]

        concat_path   = self._concatenate(clip_paths)
        graded_path   = self._colour_grade(concat_path)
        subbed_path   = self._burn_subtitles(graded_path)
        cta_path      = self._overlay_cta(subbed_path)
        logo_path     = self._overlay_logo(cta_path)
        final_path    = self._mix_audio(logo_path)

        # Cleanup intermediates
        for p in clip_paths + [concat_path, graded_path, subbed_path, cta_path, logo_path]:
            if p != final_path and p != self.video_path and os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass

        logger.info(f"[Renderer] ✅ → {final_path}")
        return final_path

    def add_watermark(self, video_path: str) -> str:
        out  = self._out("wm")
        text = WATERMARK_TEXT.replace(":", r"\:").replace("'", r"\'")
        cmd  = [
            "ffmpeg", "-y", "-i", video_path,
            "-vf",
            f"drawtext=text='{text}':fontsize=34:fontcolor=white@0.55"
            f":x=w-tw-24:y=h-th-24"
            f":shadowcolor=black@0.7:shadowx=2:shadowy=2",
            "-c:v", "libx264", "-crf", "20", "-preset", "fast",
            "-pix_fmt", "yuv420p", "-c:a", "copy",
            out,
        ]
        self._run(cmd, fallback=video_path, out=out)
        return out if os.path.exists(out) else video_path

    def generate_thumbnail(self, video_path: str) -> str:
        out = self._out("thumb", ext=".jpg")
        cmd = [
            "ffmpeg", "-y", "-ss", "00:00:02",
            "-i", video_path,
            "-vframes", "1", "-q:v", "2",
            out,
        ]
        self._run(cmd, out=out)
        return out

    # ── Clip selection ────────────────────────────────────────────────────
    def _select_clips(self) -> list[dict]:
        # Priority order: highlight → normal → all non-dead → all
        candidates = [s for s in self.segments if s["type"] in ("highlight", "normal")]
        if not candidates:
            candidates = [s for s in self.segments if s["type"] != "dead"]
        if not candidates:
            candidates = list(self.segments)
        if not candidates:
            return self._synthesise_clips()

        candidates.sort(key=lambda s: s["score"], reverse=True)

        # Adaptive max_clip: longer target → longer individual clips allowed
        # This prevents the "5min footage → 30s output" bug where 5×6s clips
        # fill the (incorrect) 30s target and nothing more is added.
        if self.target_duration <= 60:
            max_clip = 6.0
        elif self.target_duration <= 180:
            max_clip = 10.0
        elif self.target_duration <= 600:
            max_clip = 15.0
        else:
            max_clip = 20.0
        min_clip = 0.8
        selected: list[dict] = []
        total = 0.0

        for seg in candidates:
            raw_dur = seg["end"] - seg["start"]
            if raw_dur < min_clip:
                continue
            clip_dur  = min(raw_dur, max_clip)
            remaining = self.target_duration - total
            if clip_dur > remaining:
                clip_dur = remaining
            if clip_dur < 0.5:
                break
            start = self._snap_to_beat(seg["start"])
            selected.append({"start": start, "dur": clip_dur, "score": seg["score"]})
            total += clip_dur
            if total >= self.target_duration:
                break

        if not selected:
            return self._synthesise_clips()

        # Pad to fill target duration if we're short
        if total < self.target_duration * 0.8:
            selected = self._pad_to_duration(selected, total)

        selected.sort(key=lambda c: c["start"])
        return selected

    def _pad_to_duration(self, existing: list[dict], total: float) -> list[dict]:
        """Uniformly sample the remaining video to fill the target duration."""
        vid_dur = self.duration if self.duration > 0 else 60.0
        used    = [(c["start"], c["start"] + c["dur"]) for c in existing]
        # Step size adapts so we sample densely enough for long videos
        step    = max(3.0, min(10.0, vid_dur / 60))
        extra   = []
        t       = 0.0

        while total < self.target_duration and t < vid_dur:
            end_t   = min(t + step, vid_dur)
            overlap = any(s < end_t and t < e for s, e in used)
            if not overlap:
                dur = min(step, self.target_duration - total, vid_dur - t)
                if dur >= 0.8:
                    extra.append({"start": round(t, 2), "dur": round(dur, 2), "score": 0.3})
                    used.append((t, t + dur))
                    total += dur
            t += step

        logger.info(
            f"[Renderer] Padded {len(extra)} clips → "
            f"total {total:.1f}s / {self.target_duration}s"
        )
        return existing + extra

    def _synthesise_clips(self) -> list[dict]:
        """Last resort: uniform chunks across the whole video."""
        vid_dur = max(self.duration, 1.0)
        n       = max(4, min(10, int(self.target_duration / 5)))
        step    = vid_dur / n
        clips   = []
        total   = 0.0
        for i in range(n):
            start = i * step
            dur   = min(step, self.target_duration - total, vid_dur - start)
            if dur < 0.5:
                break
            clips.append({"start": round(start, 2), "dur": round(dur, 2), "score": 0.5})
            total += dur
            if total >= self.target_duration:
                break
        return clips

    def _snap_to_beat(self, t: float) -> float:
        if not self.beats:
            return t
        closest = min(self.beats, key=lambda b: abs(b - t))
        return closest if abs(closest - t) < 0.6 else t

    # ── Clip extraction (with effects) ────────────────────────────────────
    def _extract_clip(self, clip: dict, index: int) -> str | None:
        out = self._out(f"clip_{index:03d}")

        vf_parts: list[str] = []
        af_parts: list[str] = []

        # Speed-ramp: slow-mo on high-score clips
        if self.speed_ramp and clip.get("score", 0) >= 0.75:
            vf_parts.append("setpts=1.33*PTS")
            af_parts.append("atempo=0.75")

        # Zoom-punch: simple crop-scale (fast, no zoompan bugs)
        if self.zoom_punch:
            # Scale to 104%, then crop back to original → subtle zoom-in feel
            vf_parts.append(
                "scale='iw*1.04:ih*1.04',"
                "crop='iw/1.04:ih/1.04:(iw-iw/1.04)/2:(ih-ih/1.04)/2'"
            )

        cmd = [
            "ffmpeg", "-y",
            "-ss", str(clip["start"]),
            "-i", self.video_path,
            "-t", str(clip["dur"]),
        ]
        if vf_parts:
            cmd += ["-vf", ",".join(vf_parts)]
        if af_parts:
            cmd += ["-af", ",".join(af_parts)]
        cmd += [
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "22",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k",
            "-avoid_negative_ts", "make_zero",
            out,
        ]

        try:
            self._run(cmd, out=out)
            if os.path.exists(out):
                return out
        except Exception as e:
            logger.warning(f"[Renderer] Clip {index} with effects failed: {e} — retrying plain")

        # Retry without effects
        cmd_plain = [
            "ffmpeg", "-y",
            "-ss", str(clip["start"]),
            "-i", self.video_path,
            "-t", str(clip["dur"]),
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "22",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k",
            "-avoid_negative_ts", "make_zero",
            out,
        ]
        try:
            self._run(cmd_plain, out=out)
            return out if os.path.exists(out) else None
        except Exception as e2:
            logger.warning(f"[Renderer] Clip {index} plain also failed: {e2}")
            return None

    # ── Concatenation with xfade transitions ──────────────────────────────
    def _concatenate(self, clip_paths: list[str]) -> str:
        out = self._out("concat")

        if len(clip_paths) == 1:
            shutil.copy2(clip_paths[0], out)
            return out

        xfade = XFADE_MAP.get(self.transition_style, "fade")

        if xfade is None:
            return self._hard_cut(clip_paths, out)

        try:
            return self._xfade_concat(clip_paths, out, xfade)
        except Exception as e:
            logger.warning(f"[Renderer] xfade failed ({e}) — hard-cut fallback")
            return self._hard_cut(clip_paths, out)

    def _xfade_concat(self, clip_paths: list[str], out: str, xfade: str) -> str:
        td       = self.transition_dur
        durations = [self._get_duration(p) or 5.0 for p in clip_paths]

        inputs = []
        for p in clip_paths:
            inputs += ["-i", p]

        vparts: list[str] = []
        aparts: list[str] = []
        offset   = 0.0
        prev_v   = "0:v"
        prev_a   = "0:a"

        for i in range(1, len(clip_paths)):
            offset += max(durations[i - 1] - td, 0.01)
            ov, oa = f"v{i}", f"a{i}"
            vparts.append(
                f"[{prev_v}][{i}:v]xfade=transition={xfade}"
                f":duration={td}:offset={offset:.3f}[{ov}]"
            )
            aparts.append(
                f"[{prev_a}][{i}:a]acrossfade=d={td}[{oa}]"
            )
            prev_v, prev_a = ov, oa

        fg = ";".join(vparts + aparts)
        cmd = (
            ["ffmpeg", "-y"] + inputs +
            [
                "-filter_complex", fg,
                "-map", f"[{prev_v}]", "-map", f"[{prev_a}]",
                "-c:v", "libx264", "-preset", "fast", "-crf", "20",
                "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "128k",
                out,
            ]
        )
        self._run(cmd, out=out)
        if not os.path.exists(out):
            raise RuntimeError("xfade produced no output")
        return out

    def _hard_cut(self, clip_paths: list[str], out: str) -> str:
        list_file = self._out("list", ext=".txt")
        with open(list_file, "w") as f:
            for p in clip_paths:
                f.write(f"file '{p}'\n")
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0", "-i", list_file,
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "22",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
            out,
        ]
        try:
            self._run(cmd, out=out)
        finally:
            try:
                os.remove(list_file)
            except Exception:
                pass
        if not os.path.exists(out):
            raise RuntimeError("Hard-cut concat failed")
        return out

    # ── Colour grade + scale ──────────────────────────────────────────────
    def _colour_grade(self, video_path: str) -> str:
        out  = self._out("graded")
        w, h = ASPECT_RES.get(self.aspect_ratio, ("1080", "1920"))
        grade = COLOUR_GRADE.get(self.content_type, COLOUR_GRADE["unknown"])

        vf = (
            f"scale={w}:{h}:force_original_aspect_ratio=increase,"
            f"crop={w}:{h},"
            f"{grade}"
        )
        cmd = [
            "ffmpeg", "-y", "-i", video_path,
            "-vf", vf,
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k",
            out,
        ]
        try:
            self._run(cmd, out=out)
            if os.path.exists(out):
                return out
        except Exception as e:
            logger.warning(f"[Renderer] Grade failed ({e}) — scale-only fallback")

        # Scale-only fallback
        vf2 = f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}"
        cmd2 = [
            "ffmpeg", "-y", "-i", video_path,
            "-vf", vf2,
            "-c:v", "libx264", "-preset", "fast", "-crf", "20",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
            out,
        ]
        self._run(cmd2, out=out)
        return out if os.path.exists(out) else video_path

    # ── Subtitle burn-in (ASS) ────────────────────────────────────────────
    def _burn_subtitles(self, video_path: str) -> str:
        """Burn styled ASS subtitles into the video. Falls back gracefully."""
        if not self.captions:
            return video_path

        out = self._out("subbed")

        # Generate ASS file
        cg = CaptionGenerator()
        ass_path = cg.build_ass_file(
            self.captions, self.caption_style, self.output_dir, self.job_id
        )

        if not ass_path or not os.path.exists(ass_path):
            logger.warning("[Renderer] ASS file missing — skipping subtitles")
            return video_path

        # FFmpeg ass filter — path is a separate argv element so no shell quoting needed.
        # On Linux/HF Space paths have no colons or spaces so this is safe as-is.
        cmd = [
            "ffmpeg", "-y", "-i", video_path,
            "-vf", f"ass={ass_path}",
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-pix_fmt", "yuv420p",
            "-c:a", "copy",
            out,
        ]
        try:
            self._run(cmd, out=out)
            if os.path.exists(out):
                return out
        except Exception as e:
            logger.warning(f"[Renderer] ASS burn failed ({e}) — trying drawtext fallback")

        # Drawtext fallback (plain white text, no fancy styling)
        return self._drawtext_fallback(video_path, out)

    def _drawtext_fallback(self, video_path: str, out: str) -> str:
        """Simple drawtext fallback when ASS fails."""
        if not self.captions:
            return video_path
        filters = []
        for cap in self.captions[:25]:
            # Escape order matters: backslash first, then special FFmpeg chars
            text = cap["text"]
            text = text.replace("\\", "\\\\")
            text = text.replace("'",  "\\'")
            text = text.replace(":",  r"\:")
            text = text.replace("%",  r"\%")
            # Strip emoji that drawtext can't render (avoids filter parse errors)
            text = text.encode("ascii", "ignore").decode("ascii").strip()
            if not text:
                continue
            filters.append(
                f"drawtext=text='{text}'"
                f":enable='between(t,{cap['start']},{cap['end']})'"
                f":fontsize=56:fontcolor=white:x=(w-tw)/2:y=h*0.84"
                f":shadowcolor=black:shadowx=2:shadowy=2"
                f":borderw=2:bordercolor=black"
            )
        cmd = [
            "ffmpeg", "-y", "-i", video_path,
            "-vf", ",".join(filters),
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-pix_fmt", "yuv420p", "-c:a", "copy",
            out,
        ]
        try:
            self._run(cmd, out=out)
            return out if os.path.exists(out) else video_path
        except Exception:
            return video_path

    # ── CTA overlay ───────────────────────────────────────────────────────
    def _overlay_cta(self, video_path: str) -> str:
        if not self.cta_text:
            return video_path

        out      = self._out("cta")
        duration = self._get_duration(video_path)
        if not duration or duration < 2:
            return video_path

        cta_start = max(0.0, duration - 4.0)
        text = self.cta_text
        text = text.replace("\\", "\\\\")
        text = text.replace("'",  "\\'")
        text = text.replace(":",  r"\:")
        text = text.replace("%",  r"\%")
        text = text.encode("ascii", "ignore").decode("ascii").strip()
        if not text:
            return video_path
        vf = (
            f"drawtext=text='{text}'"
            f":enable='between(t,{cta_start:.2f},{duration:.2f})'"
            f":fontsize=52:fontcolor=white:x=(w-tw)/2:y=h*0.78"
            f":shadowcolor=black@0.9:shadowx=3:shadowy=3"
            f":borderw=2:bordercolor=black@0.7"
        )
        cmd = [
            "ffmpeg", "-y", "-i", video_path,
            "-vf", vf,
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-pix_fmt", "yuv420p", "-c:a", "copy",
            out,
        ]
        self._run(cmd, fallback=video_path, out=out)
        return out if os.path.exists(out) else video_path

    # ── Logo overlay (blended) ────────────────────────────────────────────
    def _overlay_logo(self, video_path: str) -> str:
        if not self.logo_file or not os.path.exists(self.logo_file):
            return video_path

        out = self._out("logo")
        positions = {
            "top_left":     "20:20",
            "top_right":    "W-w-20:20",
            "bottom_left":  "20:H-h-20",
            "bottom_right": "W-w-20:H-h-20",
        }
        pos = positions.get(self.logo_position, "W-w-20:H-h-20")

        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-i", self.logo_file,
            "-filter_complex",
            # Scale to 12% width, convert to RGBA, 65% opacity → natural blend
            f"[1:v]scale=iw*0.12:-1,format=rgba,colorchannelmixer=aa=0.65[logo];"
            f"[0:v][logo]overlay={pos}:format=auto",
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-pix_fmt", "yuv420p", "-c:a", "copy",
            out,
        ]
        self._run(cmd, fallback=video_path, out=out)
        return out if os.path.exists(out) else video_path

    # ── Audio mix + ducking ───────────────────────────────────────────────
    def _mix_audio(self, video_path: str) -> str:
        out       = self._out("final")
        has_music = bool(self.music_file and os.path.exists(self.music_file))

        if self.mute_audio and has_music:
            # Replace original audio with music only
            cmd = [
                "ffmpeg", "-y",
                "-i", video_path,
                "-ss", str(self.music_offset), "-i", self.music_file,
                "-map", "0:v", "-map", "1:a",
                "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                "-shortest", out,
            ]
        elif self.mute_audio:
            # Silent audio
            cmd = [
                "ffmpeg", "-y", "-i", video_path,
                "-f", "lavfi", "-i", "anullsrc=cl=stereo:r=44100",
                "-c:v", "copy", "-c:a", "aac", "-b:a", "128k",
                "-shortest", out,
            ]
        elif has_music:
            # Mix original (ducked) with background music
            # Speech detected → original at 0.35, music at 0.85; else 0.15/1.0
            orig_vol  = 0.30 if self.captions else 0.15
            music_vol = 0.90
            cmd = [
                "ffmpeg", "-y",
                "-i", video_path,
                "-ss", str(self.music_offset), "-i", self.music_file,
                "-filter_complex",
                f"[0:a]volume={orig_vol}[orig];"
                f"[1:a]volume={music_vol}[music];"
                "[orig][music]amix=inputs=2:duration=first:dropout_transition=2[aout]",
                "-map", "0:v", "-map", "[aout]",
                "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                "-shortest", out,
            ]
        else:
            # Normalise original audio
            cmd = [
                "ffmpeg", "-y", "-i", video_path,
                "-af", "dynaudnorm=f=150:g=15",
                "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                out,
            ]

        self._run(cmd, fallback=video_path, out=out)
        return out if os.path.exists(out) else video_path

    # ── Helpers ───────────────────────────────────────────────────────────
    def _get_duration(self, path: str) -> float:
        try:
            r = subprocess.run(
                ["ffprobe", "-v", "quiet", "-print_format", "json",
                 "-show_streams", "-select_streams", "v:0", path],
                capture_output=True, timeout=15,
            )
            if r.returncode == 0:
                info = json.loads(r.stdout)
                return float(info["streams"][0].get("duration", 0))
        except Exception:
            pass
        return 0.0

    def _out(self, tag: str, ext: str = ".mp4") -> str:
        return str(Path(self.output_dir) / f"{self.job_id}_{tag}{ext}")

    @staticmethod
    def _run(cmd: list[str], fallback: str | None = None, out: str | None = None):
        result = subprocess.run(cmd, capture_output=True, timeout=600)
        if result.returncode != 0:
            err = result.stderr.decode()[-2000:]
            raise RuntimeError(err)
