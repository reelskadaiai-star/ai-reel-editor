"""
Core reel renderer — v2.
Uses FFmpeg to:
  1. Select highlight segments (beat-aware snap)
  2. Trim, speed-ramp & zoom-punch individual clips
  3. Concatenate with smooth xfade transitions
  4. Convert to target aspect ratio + colour grade
  5. Overlay animated captions (drawtext)
  6. Overlay end-screen CTA text
  7. Overlay user logo / watermark
  8. Mix background music (4 audio modes)
  9. Generate thumbnail
"""
from __future__ import annotations
import os
import uuid
import subprocess
import json
import shutil
from pathlib import Path
from loguru import logger


WATERMARK_TEXT = os.getenv("WATERMARK_TEXT", "@ReelAI")

FILTERS = {
    "real_estate": "eq=saturation=1.1:contrast=1.05:brightness=0.02,unsharp=3:3:0.5",
    "food":        "eq=saturation=1.4:contrast=1.15:brightness=0.03,unsharp=5:5:1.0",
    "product":     "eq=saturation=1.2:contrast=1.1",
    "dance":       "eq=saturation=1.3:contrast=1.2",
    "travel":      "eq=saturation=1.3:contrast=1.1:brightness=0.02",
    "cinematic":   "eq=saturation=0.85:contrast=1.2,curves=all='0/0 0.5/0.4 1/1'",
    "fitness":     "eq=saturation=1.2:contrast=1.25:brightness=0.01",
    "education":   "eq=saturation=1.0:contrast=1.05",
    "lifestyle":   "eq=saturation=1.15:contrast=1.08:brightness=0.01",
    "vlog":        "eq=saturation=1.1:contrast=1.05",
    "comedy":      "eq=saturation=1.2:contrast=1.1",
    "interview":   "eq=saturation=1.0:contrast=1.1",
    "unknown":     "eq=saturation=1.1",
}

ASPECT_RES = {
    "9:16":  ("1080", "1920"),
    "1:1":   ("1080", "1080"),
    "16:9":  ("1920", "1080"),
    "4:5":   ("1080", "1350"),
}

# xfade transition names (all supported in FFmpeg 4.3+)
XFADE_TRANSITIONS = {
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
        transition_duration: float = 0.3,
        cta_text: str | None = None,
        speed_ramp: bool = False,
        zoom_punch: bool = True,
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
        self.transition_duration = max(0.1, min(transition_duration, 0.8))
        self.target_duration = target_duration
        self.include_hook = include_hook
        self.hook_text = hook_text
        self.output_dir = output_dir
        self.mute_audio = mute_audio
        self.logo_file = logo_file
        self.logo_position = logo_position
        self.cta_text = cta_text
        self.speed_ramp = speed_ramp
        self.zoom_punch = zoom_punch

    def render(self) -> str:
        clips = self._select_clips()
        logger.info(f"[Renderer] {len(clips)} clips, ~{sum(c['dur'] for c in clips):.1f}s total")

        clip_paths = []
        for i, clip in enumerate(clips):
            out = self._extract_clip(clip, index=i)
            if out:
                clip_paths.append(out)

        if not clip_paths:
            raise RuntimeError("No valid clips extracted")

        concat_path = self._concatenate_xfade(clip_paths)
        graded_path = self._apply_grade(concat_path)
        captioned_path = self._overlay_captions(graded_path)
        cta_path = self._overlay_cta(captioned_path)
        logo_path = self._overlay_logo(cta_path)
        final_path = self._mix_audio(logo_path)

        for p in clip_paths + [concat_path, graded_path, captioned_path, cta_path, logo_path]:
            if p != final_path and os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass

        logger.info(f"[Renderer] Render complete → {final_path}")
        return final_path

    def add_watermark(self, video_path: str) -> str:
        out = str(Path(self.output_dir) / f"{self.job_id}_wm.mp4")
        text = WATERMARK_TEXT.replace(":", r"\:").replace("'", r"\'")
        cmd = [
            "ffmpeg", "-y", "-i", video_path,
            "-vf",
            f"drawtext=text='{text}':fontsize=32:fontcolor=white@0.5"
            f":x=w-tw-20:y=h-th-20:shadowcolor=black@0.6:shadowx=2:shadowy=2",
            "-c:a", "copy",
            "-c:v", "libx264", "-crf", "23", "-preset", "fast",
            out,
        ]
        self._run(cmd)
        return out

    def generate_thumbnail(self, video_path: str) -> str:
        out = str(Path(self.output_dir) / f"{self.job_id}_thumb.jpg")
        cmd = [
            "ffmpeg", "-y",
            "-ss", "00:00:01",
            "-i", video_path,
            "-vframes", "1",
            "-q:v", "2",
            out,
        ]
        self._run(cmd)
        return out

    # ── Private ───────────────────────────────────────────────────────
    def _select_clips(self) -> list[dict]:
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
            remaining = self.target_duration - total
            if clip_dur > remaining:
                clip_dur = remaining
                if clip_dur < 1.0:
                    break
            start = self._snap_to_beat(seg["start"])
            selected.append({"start": start, "dur": clip_dur, "score": seg["score"]})
            total += clip_dur
            if total >= self.target_duration:
                break

        selected.sort(key=lambda c: c["start"])
        return selected

    def _snap_to_beat(self, t: float) -> float:
        if not self.beats:
            return t
        closest = min(self.beats, key=lambda b: abs(b - t))
        return closest if abs(closest - t) < 0.5 else t

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
        ]

        # Speed ramp: high-score clips play at 0.75x speed (slow-mo feel)
        if self.speed_ramp and clip.get("score", 0) >= 0.75:
            cmd += ["-vf", "setpts=1.33*PTS", "-af", "atempo=0.75"]

        cmd.append(out)

        try:
            self._run(cmd)
            return out
        except Exception as e:
            logger.warning(f"[Renderer] Clip {index} failed: {e}")
            return None

    def _get_video_duration(self, path: str) -> float:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json",
             "-show_streams", "-select_streams", "v:0", path],
            capture_output=True, timeout=15,
        )
        if result.returncode != 0:
            return 0.0
        try:
            info = json.loads(result.stdout)
            return float(info["streams"][0].get("duration", 0))
        except Exception:
            return 0.0

    def _concatenate_xfade(self, clip_paths: list[str]) -> str:
        out = str(Path(self.output_dir) / f"{self.job_id}_concat.mp4")

        if len(clip_paths) == 1:
            shutil.copy2(clip_paths[0], out)
            return out

        xfade_name = XFADE_TRANSITIONS.get(self.transition_style, "fade")

        if xfade_name is None:
            return self._concatenate_hardcut(clip_paths, out)

        try:
            return self._concatenate_with_xfade(clip_paths, out, xfade_name)
        except Exception as e:
            logger.warning(f"[Renderer] xfade failed ({e}), hard-cut fallback")
            return self._concatenate_hardcut(clip_paths, out)

    def _concatenate_with_xfade(self, clip_paths: list[str], out: str, xfade_name: str) -> str:
        td = self.transition_duration
        durations = [self._get_video_duration(p) for p in clip_paths]
        durations = [d if d > 0 else 5.0 for d in durations]

        inputs = []
        for p in clip_paths:
            inputs += ["-i", p]

        # Chain xfade + acrossfade for N clips
        vparts = []
        aparts = []
        offset = 0.0
        prev_v = "0:v"
        prev_a = "0:a"

        for i in range(1, len(clip_paths)):
            offset += durations[i - 1] - td
            out_v = f"v{i}"
            out_a = f"a{i}"
            vparts.append(
                f"[{prev_v}][{i}:v]xfade=transition={xfade_name}:duration={td}:offset={offset:.3f}[{out_v}]"
            )
            aparts.append(
                f"[{prev_a}][{i}:a]acrossfade=d={td}[{out_a}]"
            )
            prev_v = out_v
            prev_a = out_a

        filtergraph = ";".join(vparts + aparts)

        cmd = (
            ["ffmpeg", "-y"]
            + inputs
            + [
                "-filter_complex", filtergraph,
                "-map", f"[{prev_v}]",
                "-map", f"[{prev_a}]",
                "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "128k",
                out,
            ]
        )
        self._run(cmd)
        if not os.path.exists(out):
            raise RuntimeError("xfade concat produced no output")
        return out

    def _concatenate_hardcut(self, clip_paths: list[str], out: str) -> str:
        list_file = str(Path(self.output_dir) / f"{self.job_id}_list.txt")
        with open(list_file, "w") as f:
            for p in clip_paths:
                f.write(f"file '{p}'\n")
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0", "-i", list_file,
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
            out,
        ]
        try:
            self._run(cmd)
        finally:
            try:
                os.remove(list_file)
            except Exception:
                pass
        if not os.path.exists(out):
            raise RuntimeError("Hard-cut concat produced no output")
        return out

    def _apply_grade(self, video_path: str) -> str:
        out = str(Path(self.output_dir) / f"{self.job_id}_graded.mp4")
        w, h = ASPECT_RES.get(self.aspect_ratio, ("1080", "1920"))
        grade = FILTERS.get(self.content_type, FILTERS["unknown"])

        vf = (
            f"scale={w}:{h}:force_original_aspect_ratio=increase,"
            f"crop={w}:{h},"
            f"{grade}"
        )
        cmd = [
            "ffmpeg", "-y", "-i", video_path,
            "-vf", vf,
            "-c:v", "libx264", "-preset", "fast", "-crf", "22",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k",
            out,
        ]
        try:
            self._run(cmd)
        except Exception as e:
            logger.warning(f"[Renderer] Grade failed ({e}), scale-only fallback")
            vf2 = f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}"
            cmd2 = ["ffmpeg", "-y", "-i", video_path, "-vf", vf2,
                    "-c:v", "libx264", "-preset", "fast", "-crf", "22",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-ar", "44100", out]
            self._run(cmd2)

        if not os.path.exists(out):
            raise RuntimeError(f"Grade step produced no output at {out}")
        return out

    def _overlay_captions(self, video_path: str) -> str:
        if not self.captions:
            return video_path

        out = str(Path(self.output_dir) / f"{self.job_id}_captions.mp4")
        captions = self.captions[:20]
        filters = []

        for cap in captions:
            text = (cap["text"]
                    .replace("'", "'\\''")
                    .replace(":", r"\:")
                    .replace("%", r"\%")
                    .replace("\\", "\\\\"))
            style = self._caption_style_params(cap.get("style", self.caption_style))
            filters.append(
                f"drawtext=text='{text}'"
                f":enable='between(t,{cap['start']},{cap['end']})'"
                f":{style}"
            )

        cmd = [
            "ffmpeg", "-y", "-i", video_path,
            "-vf", ",".join(filters),
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

    def _overlay_cta(self, video_path: str) -> str:
        """Burn CTA text onto the last 3.5 seconds of the reel."""
        if not self.cta_text:
            return video_path

        out = str(Path(self.output_dir) / f"{self.job_id}_cta.mp4")
        duration = self._get_video_duration(video_path)
        if duration <= 0:
            return video_path

        cta_start = max(0.0, duration - 3.5)
        text = (self.cta_text
                .replace("'", "'\\''")
                .replace(":", r"\:")
                .replace("%", r"\%"))

        vf = (
            f"drawtext=text='{text}'"
            f":enable='between(t,{cta_start:.2f},{duration:.2f})'"
            f":fontsize=50:fontcolor=white:x=(w-tw)/2:y=h*0.79"
            f":shadowcolor=black@0.8:shadowx=3:shadowy=3"
            f":borderw=2:bordercolor=black@0.6"
        )
        cmd = [
            "ffmpeg", "-y", "-i", video_path,
            "-vf", vf,
            "-c:v", "libx264", "-preset", "fast", "-crf", "22",
            "-c:a", "copy",
            out,
        ]
        try:
            self._run(cmd)
            return out
        except Exception as e:
            logger.warning(f"[Renderer] CTA overlay failed: {e}")
            return video_path

    def _overlay_logo(self, video_path: str) -> str:
        if not self.logo_file or not os.path.exists(self.logo_file):
            return video_path

        out = str(Path(self.output_dir) / f"{self.job_id}_logo.mp4")
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
        has_music = bool(self.music_file and os.path.exists(self.music_file))

        if self.mute_audio and has_music:
            cmd = [
                "ffmpeg", "-y",
                "-i", video_path,
                "-ss", str(self.music_offset), "-i", self.music_file,
                "-map", "0:v", "-map", "1:a",
                "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                "-shortest", out,
            ]
        elif self.mute_audio:
            cmd = [
                "ffmpeg", "-y",
                "-i", video_path,
                "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
                "-c:v", "copy", "-c:a", "aac", "-b:a", "128k",
                "-shortest", out,
            ]
        elif has_music:
            cmd = [
                "ffmpeg", "-y",
                "-i", video_path,
                "-ss", str(self.music_offset), "-i", self.music_file,
                "-filter_complex",
                "[0:a]volume=0.25[orig];[1:a]volume=1.0[music];"
                "[orig][music]amix=inputs=2:duration=first[aout]",
                "-map", "0:v", "-map", "[aout]",
                "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                "-shortest", out,
            ]
        else:
            cmd = [
                "ffmpeg", "-y",
                "-i", video_path,
                "-c:v", "copy", "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
                out,
            ]

        try:
            self._run(cmd)
        except Exception as e:
            logger.warning(f"[Renderer] Audio mix failed ({e}), silent fallback")
            cmd2 = [
                "ffmpeg", "-y",
                "-i", video_path,
                "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
                "-c:v", "copy", "-c:a", "aac", "-b:a", "128k", "-shortest", out,
            ]
            self._run(cmd2)
        return out

    def _caption_style_params(self, style: str) -> str:
        styles = {
            "modern":  "fontsize=48:fontcolor=white:x=(w-tw)/2:y=h*0.85:shadowcolor=black:shadowx=2:shadowy=2:borderw=2:bordercolor=black",
            "luxury":  "fontsize=42:fontcolor=white:x=(w-tw)/2:y=h*0.88",
            "bold":    "fontsize=58:fontcolor=yellow:x=(w-tw)/2:y=h*0.82:shadowcolor=black:shadowx=3:shadowy=3:borderw=3:bordercolor=black",
            "minimal": "fontsize=36:fontcolor=white@0.9:x=(w-tw)/2:y=h*0.90",
            "hype":    "fontsize=64:fontcolor=#ff3366:x=(w-tw)/2:y=h*0.80:shadowcolor=black:shadowx=4:shadowy=4:borderw=3:bordercolor=black",
            "neon":    "fontsize=52:fontcolor=#00ffcc:x=(w-tw)/2:y=h*0.84:borderw=3:bordercolor=#00ffcc",
            "clean":   "fontsize=40:fontcolor=white:x=(w-tw)/2:y=h*0.87:box=1:boxcolor=black@0.4:boxborderw=8",
            "default": "fontsize=44:fontcolor=white:x=(w-tw)/2:y=h*0.85:shadowcolor=black:shadowx=2:shadowy=2",
        }
        return styles.get(style, styles["default"])

    @staticmethod
    def _run(cmd: list[str]):
        result = subprocess.run(cmd, capture_output=True, timeout=600)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.decode()[-2000:])
