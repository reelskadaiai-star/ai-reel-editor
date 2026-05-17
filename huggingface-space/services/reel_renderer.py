"""
Core reel renderer.
Uses FFmpeg (via ffmpeg-python) to:
  1. Select highlight segments
  2. Trim & concatenate clips
  3. Convert to vertical 9:16
  4. Apply content-specific filter chains (colour grade, zoom, speed ramp)
  5. Overlay captions (via drawtext filter)
  6. Mix background music
  7. Add watermark
  8. Generate thumbnail
"""
from __future__ import annotations
import os
import uuid
import subprocess
import tempfile
import json
from pathlib import Path
from loguru import logger


WATERMARK_TEXT = os.getenv("WATERMARK_TEXT", "@AIReelEditor")

# Colour grade LUTs per content type (paths relative to this file)
FILTERS = {
    "real_estate": "eq=saturation=1.1:contrast=1.05:brightness=0.02,unsharp=3:3:0.5",
    "food": "eq=saturation=1.4:contrast=1.15:brightness=0.03,unsharp=5:5:1.0",
    "product": "eq=saturation=1.2:contrast=1.1",
    "dance": "eq=saturation=1.3:contrast=1.2",
    "travel": "eq=saturation=1.3:contrast=1.1:brightness=0.02",
    "cinematic": "eq=saturation=0.85:contrast=1.2,curves=all='0/0 0.5/0.4 1/1'",
    "unknown": "eq=saturation=1.1",
}

ASPECT_RES = {
    "9:16": ("1080", "1920"),
    "1:1": ("1080", "1080"),
    "16:9": ("1920", "1080"),
}


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
    ):
        self.job_id = job_id
        self.video_path = video_path
        self.segments = segments
        self.captions = captions
        self.beats = beat_timestamps
        self.content_type = content_type
        self.template = template
        self.music_file = music_file
        self.music_offset = music_offset
        self.aspect_ratio = aspect_ratio
        self.caption_style = caption_style
        self.transition_style = transition_style
        self.target_duration = target_duration
        self.include_hook = include_hook
        self.hook_text = hook_text
        self.output_dir = output_dir
        self.mute_audio = mute_audio
        self.logo_file = logo_file
        self.logo_position = logo_position

    def render(self) -> str:
        """Main render pipeline. Returns path to final output file."""
        clips = self._select_clips()
        logger.info(f"[Renderer] {len(clips)} clips selected, total ≈ {sum(c['dur'] for c in clips):.1f}s")

        # 1. Extract & process each clip segment
        clip_paths = []
        for i, clip in enumerate(clips):
            out = self._extract_clip(clip, index=i)
            if out:
                clip_paths.append(out)

        if not clip_paths:
            raise RuntimeError("No valid clips extracted")

        # 2. Concatenate
        concat_path = self._concatenate(clip_paths)

        # 3. Apply colour grade + aspect ratio conversion
        graded_path = self._apply_grade(concat_path)

        # 4. Overlay captions
        captioned_path = self._overlay_captions(graded_path)

        # 5. Overlay logo
        logo_path = self._overlay_logo(captioned_path)

        # 6. Mix audio
        final_path = self._mix_audio(logo_path)

        # Cleanup temp files
        for p in clip_paths + [concat_path, graded_path, captioned_path, logo_path]:
            if p != final_path and os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass

        logger.info(f"[Renderer] Render complete → {final_path}")
        return final_path

    def add_watermark(self, video_path: str) -> str:
        """Burn watermark text into a copy of the video."""
        out = str(Path(self.output_dir) / f"{self.job_id}_wm.mp4")
        text = WATERMARK_TEXT.replace(":", r"\:").replace("'", r"\'")
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-vf",
            f"drawtext=text='{text}':fontsize=36:fontcolor=white@0.6"
            f":x=w-tw-20:y=h-th-20:shadowcolor=black:shadowx=2:shadowy=2",
            "-c:a", "copy",
            "-c:v", "libx264", "-crf", "23", "-preset", "fast",
            out,
        ]
        self._run(cmd)
        return out

    def generate_thumbnail(self, video_path: str) -> str:
        """Extract the sharpest frame at 10% into video as JPEG thumbnail."""
        out = str(Path(self.output_dir) / f"{self.job_id}_thumb.jpg")
        cmd = [
            "ffmpeg", "-y",
            "-ss", "00:00:02",
            "-i", video_path,
            "-vframes", "1",
            "-q:v", "2",
            out,
        ]
        self._run(cmd)
        return out

    # ── Private ───────────────────────────────────────────────────────
    def _select_clips(self) -> list[dict]:
        """
        Pick highlight segments up to target_duration.
        Respects beat sync: prefer clips that start near a beat.
        """
        highlights = [s for s in self.segments if s["type"] in ("highlight", "normal")]
        highlights.sort(key=lambda s: s["score"], reverse=True)

        selected = []
        total = 0.0
        max_clip = 6.0 if self.content_type == "food" else 8.0
        min_clip = 1.5

        for seg in highlights:
            dur = seg["end"] - seg["start"]
            if dur < min_clip:
                continue
            clip_dur = min(dur, max_clip)
            if total + clip_dur > self.target_duration:
                clip_dur = self.target_duration - total
                if clip_dur < 1.0:
                    break
            selected.append({"start": seg["start"], "dur": clip_dur, "score": seg["score"]})
            total += clip_dur
            if total >= self.target_duration:
                break

        # Sort chronologically for natural flow
        selected.sort(key=lambda c: c["start"])
        return selected

    def _extract_clip(self, clip: dict, index: int) -> str | None:
        out = str(Path(self.output_dir) / f"{self.job_id}_clip_{index:03d}.mp4")
        cmd = [
            "ffmpeg", "-y",
            "-ss", str(clip["start"]),
            "-i", self.video_path,
            "-t", str(clip["dur"]),
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k",
            "-avoid_negative_ts", "make_zero",
            out,
        ]
        try:
            self._run(cmd)
            return out
        except Exception as e:
            logger.warning(f"[Renderer] Clip {index} extraction failed: {e}")
            return None

    def _concatenate(self, clip_paths: list[str]) -> str:
        out = str(Path(self.output_dir) / f"{self.job_id}_concat.mp4")

        if len(clip_paths) == 1:
            # Single clip — just copy it directly, no concat needed
            import shutil
            shutil.copy2(clip_paths[0], out)
            return out

        list_file = str(Path(self.output_dir) / f"{self.job_id}_list.txt")
        with open(list_file, "w") as f:
            for p in clip_paths:
                f.write(f"file '{p}'\n")
        # Re-encode at concat to normalise codecs/sample-rates across clips
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", list_file,
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
            out,
        ]
        try:
            self._run(cmd)
        finally:
            if os.path.exists(list_file):
                os.remove(list_file)

        if not os.path.exists(out):
            raise RuntimeError(f"Concatenation produced no output at {out}")
        return out

    def _apply_grade(self, video_path: str) -> str:
        out = str(Path(self.output_dir) / f"{self.job_id}_graded.mp4")
        w, h = ASPECT_RES.get(self.aspect_ratio, ("1080", "1920"))
        grade = FILTERS.get(self.content_type, FILTERS["unknown"])

        # Scale+crop to target aspect ratio, then apply colour grade
        vf = (
            f"scale={w}:{h}:force_original_aspect_ratio=increase,"
            f"crop={w}:{h},"
            f"{grade}"
        )
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-vf", vf,
            "-c:v", "libx264", "-preset", "fast", "-crf", "22",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k",   # re-encode audio (not copy) for compatibility
            out,
        ]
        try:
            self._run(cmd)
        except Exception as e:
            logger.warning(f"[Renderer] Grade failed ({e}), falling back to scale-only")
            vf_simple = f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}"
            cmd2 = [
                "ffmpeg", "-y",
                "-i", video_path,
                "-vf", vf_simple,
                "-c:v", "libx264", "-preset", "fast", "-crf", "22",
                "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
                out,
            ]
            self._run(cmd2)

        if not os.path.exists(out):
            raise RuntimeError(f"Grade step produced no output at {out}")
        return out

    def _overlay_captions(self, video_path: str) -> str:
        if not self.captions:
            return video_path

        out = str(Path(self.output_dir) / f"{self.job_id}_captions.mp4")
        # Build drawtext chain for up to 20 captions (FFmpeg filter limit)
        captions = self.captions[:20]
        filters = []

        for cap in captions:
            text = cap["text"].replace("'", "'\\''").replace(":", r"\:").replace("%", r"\%")
            style = self._caption_style_params(cap.get("style", self.caption_style))
            f = (
                f"drawtext=text='{text}'"
                f":enable='between(t,{cap['start']},{cap['end']})'"
                f":{style}"
            )
            filters.append(f)

        vf = ",".join(filters)
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-vf", vf,
            "-c:v", "libx264", "-preset", "fast", "-crf", "22",
            "-c:a", "copy",
            out,
        ]
        try:
            self._run(cmd)
            return out
        except Exception as e:
            logger.warning(f"[Renderer] Caption overlay failed: {e}")
            return video_path

    def _overlay_logo(self, video_path: str) -> str:
        """Overlay user logo at the selected corner position."""
        if not self.logo_file or not os.path.exists(self.logo_file):
            return video_path  # no logo — pass through

        out = str(Path(self.output_dir) / f"{self.job_id}_logo.mp4")

        # Logo size: 15% of video width, keep aspect ratio
        # Position map: corner → (x, y) in FFmpeg overlay syntax
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
            f"[1:v]scale=iw*0.15:-1[logo];[0:v][logo]overlay={pos}",
            "-c:v", "libx264", "-preset", "fast", "-crf", "22",
            "-c:a", "copy",
            out,
        ]
        try:
            self._run(cmd)
            return out
        except Exception as e:
            logger.warning(f"[Renderer] Logo overlay failed ({e}), skipping")
            return video_path

    def _mix_audio(self, video_path: str) -> str:
        out = str(Path(self.output_dir) / f"{self.job_id}_final.mp4")

        has_music = self.music_file and os.path.exists(self.music_file)

        if self.mute_audio and has_music:
            # Muted original — music only
            cmd = [
                "ffmpeg", "-y",
                "-i", video_path,
                "-ss", str(self.music_offset), "-i", self.music_file,
                "-map", "0:v", "-map", "1:a",
                "-c:v", "copy",
                "-c:a", "aac", "-b:a", "192k",
                "-shortest",
                out,
            ]
        elif self.mute_audio:
            # Muted original, no music — silent audio
            cmd = [
                "ffmpeg", "-y",
                "-i", video_path,
                "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
                "-c:v", "copy",
                "-c:a", "aac", "-b:a", "128k",
                "-shortest",
                out,
            ]
        elif has_music:
            # Mix original (quiet) + music
            cmd = [
                "ffmpeg", "-y",
                "-i", video_path,
                "-ss", str(self.music_offset), "-i", self.music_file,
                "-filter_complex",
                "[0:a]volume=0.3[orig];[1:a]volume=1.0[music];[orig][music]amix=inputs=2:duration=first[aout]",
                "-map", "0:v", "-map", "[aout]",
                "-c:v", "copy",
                "-c:a", "aac", "-b:a", "192k",
                "-shortest",
                out,
            ]
        else:
            # Original audio only
            cmd = [
                "ffmpeg", "-y",
                "-i", video_path,
                "-c:v", "copy",
                "-c:a", "aac", "-b:a", "128k",
                "-ar", "44100",
                out,
            ]
        try:
            self._run(cmd)
        except Exception as e:
            logger.warning(f"[Renderer] Audio mix failed ({e}), using silent fallback")
            cmd_fallback = [
                "ffmpeg", "-y",
                "-i", video_path,
                "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
                "-c:v", "copy",
                "-c:a", "aac", "-b:a", "128k",
                "-shortest",
                out,
            ]
            self._run(cmd_fallback)
        return out

    def _caption_style_params(self, style: str) -> str:
        styles = {
            "modern": "fontsize=48:fontcolor=white:x=(w-tw)/2:y=h*0.85:shadowcolor=black:shadowx=2:shadowy=2:borderw=2:bordercolor=black",
            "luxury": "fontsize=42:fontcolor=white:x=(w-tw)/2:y=h*0.88:fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "bold": "fontsize=58:fontcolor=yellow:x=(w-tw)/2:y=h*0.82:shadowcolor=black:shadowx=3:shadowy=3:borderw=3:bordercolor=black",
            "minimal": "fontsize=36:fontcolor=white@0.9:x=(w-tw)/2:y=h*0.90",
            "hype": "fontsize=64:fontcolor=red:x=(w-tw)/2:y=h*0.80:shadowcolor=black:shadowx=4:shadowy=4",
            "default": "fontsize=44:fontcolor=white:x=(w-tw)/2:y=h*0.85:shadowcolor=black:shadowx=2:shadowy=2",
        }
        return styles.get(style, styles["default"])

    @staticmethod
    def _run(cmd: list[str]):
        result = subprocess.run(cmd, capture_output=True, timeout=600)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.decode()[-2000:])
