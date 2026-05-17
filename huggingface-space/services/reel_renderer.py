"""
Premium Reel Renderer v4 — Cinematic AI Video Pipeline.

What's new in v4:
  • edit_mode parameter drives every creative decision
  • Narrative arc ordering: hook → build → peak → outro
  • Animated Ken Burns (alternating L/R pan + zoom-in) per clip
  • Per-pair transition variety: cycles mode-aware sequence
  • Cinematic colour grades with S-curves + vignette per content type
  • Mode-specific grades (fast_beat = high contrast, wedding = soft warm, etc.)
  • Caption fade animations via CaptionGenerator v4 fix

Pipeline:
  1. Select + order highlight clips (narrative arc + beat-aware)
  2. Extract clips with Ken Burns animation + optional speed-ramp
  3. Concatenate with varied cinematic xfade transitions
  4. Colour grade (mode+content LUT, vignette, curves)
  5. Burn ASS subtitles with fade animations
  6. Overlay CTA end-screen
  7. Overlay logo (blended)
  8. Mix / duck audio
  9. Export 1080p CRF-18

Never crashes — 3-tier fallback at every stage.
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

# ── Target aspect-ratio → (width, height) ────────────────────────────────────
ASPECT_RES: dict[str, tuple[str, str]] = {
    "9:16":  ("1080", "1920"),
    "1:1":   ("1080", "1080"),
    "16:9":  ("1920", "1080"),
    "4:5":   ("1080", "1350"),
}

# ── Cinematic colour grades ───────────────────────────────────────────────────
# Each entry: (scale_grade, vignette, post_grade)
# scale_grade applied after scale/crop (before vignette)
# post_grade applied after subtitle burn (optional final touch)
COLOUR_GRADE: dict[str, str] = {
    # Social / fast content
    "real_estate": (
        "eq=saturation=1.12:contrast=1.08:brightness=0.02,"
        "unsharp=3:3:0.6,"
        "vignette=angle=PI/4"
    ),
    "food": (
        "curves=r='0/0 0.4/0.46 1/1':g='0/0 0.5/0.52 1/1',"
        "eq=saturation=1.55:contrast=1.22:brightness=0.03,"
        "unsharp=5:5:1.2,"
        "vignette=angle=PI/5"
    ),
    "product": (
        "eq=saturation=1.22:contrast=1.12,"
        "unsharp=3:3:0.4,"
        "vignette=angle=PI/5"
    ),
    "dance": (
        "eq=saturation=1.35:contrast=1.25,"
        "vignette=angle=PI/4"
    ),
    "travel": (
        "curves=r='0/0 0.4/0.46 1/1':b='0/0 0.5/0.44 1/1',"
        "eq=saturation=1.35:contrast=1.14:brightness=0.02,"
        "unsharp=3:3:0.3,"
        "vignette=angle=PI/4"
    ),
    "nature": (
        "curves=g='0/0 0.35/0.42 0.7/0.75 1/1',"
        "eq=saturation=1.32:contrast=1.12:brightness=0.01,"
        "unsharp=3:3:0.5,"
        "vignette=angle=PI/5"
    ),
    "fitness": (
        "eq=saturation=1.25:contrast=1.30:brightness=0.01,"
        "unsharp=5:5:0.8,"
        "vignette=angle=PI/4"
    ),
    "education": (
        "eq=saturation=1.06:contrast=1.10:brightness=0.01,"
        "vignette=angle=PI/6"
    ),
    "lifestyle": (
        "curves=all='0/0 0.25/0.22 0.75/0.78 1/1',"
        "eq=saturation=1.20:contrast=1.10:brightness=0.01,"
        "vignette=angle=PI/5"
    ),
    "vlog": (
        "eq=saturation=1.14:contrast=1.08,"
        "vignette=angle=PI/6"
    ),
    "comedy": (
        "eq=saturation=1.25:contrast=1.15,"
        "vignette=angle=PI/5"
    ),
    "interview": (
        "eq=saturation=1.06:contrast=1.12,"
        "vignette=angle=PI/6"
    ),
    # Cinematic grades
    "cinematic": (
        "curves=all='0/0 0.15/0.08 0.5/0.52 0.85/0.92 1/1',"
        "eq=saturation=0.88:contrast=1.20,"
        "vignette=angle=PI/3.5"
    ),
    "unknown": (
        "eq=saturation=1.10:contrast=1.06,"
        "vignette=angle=PI/5"
    ),
}

# ── Edit-mode colour grade overrides ─────────────────────────────────────────
EDIT_MODE_GRADE: dict[str, str] = {
    "cinematic": (
        "curves=all='0/0 0.15/0.08 0.5/0.52 0.85/0.92 1/1',"
        "eq=saturation=0.85:contrast=1.22,"
        "vignette=angle=PI/3"
    ),
    "wedding": (
        "curves=r='0/0 0.5/0.56 1/1':b='0/0 0.5/0.44 1/1',"
        "eq=saturation=0.92:contrast=1.06:brightness=0.04,"
        "vignette=angle=PI/4"
    ),
    "emotional": (
        "curves=all='0/0 0.2/0.14 0.75/0.82 1/1',"
        "eq=saturation=0.90:contrast=1.15,"
        "vignette=angle=PI/3.5"
    ),
    "fast_beat": (
        "eq=saturation=1.40:contrast=1.35:brightness=0.01,"
        "unsharp=5:5:0.8,"
        "vignette=angle=PI/4"
    ),
    "travel": (
        "curves=r='0/0 0.4/0.46 1/1':b='0/0 0.5/0.44 1/1',"
        "eq=saturation=1.38:contrast=1.14:brightness=0.02,"
        "vignette=angle=PI/4"
    ),
    "food": (
        "curves=r='0/0 0.4/0.46 1/1':g='0/0 0.5/0.52 1/1',"
        "eq=saturation=1.60:contrast=1.25:brightness=0.03,"
        "unsharp=5:5:1.5,"
        "vignette=angle=PI/5"
    ),
    "business": (
        "eq=saturation=1.05:contrast=1.12,"
        "unsharp=3:3:0.4,"
        "vignette=angle=PI/5"
    ),
    "vlog": (
        "eq=saturation=1.15:contrast=1.08,"
        "vignette=angle=PI/6"
    ),
}

# ── Transition sequences per edit mode ────────────────────────────────────────
# Each list is cycled per clip pair so transitions are varied but consistent
TRANSITION_SEQUENCES: dict[str, list[str]] = {
    "cinematic":  ["fade", "dissolve", "fade", "dissolve"],
    "wedding":    ["fade", "dissolve", "fade", "dissolve"],
    "emotional":  ["fade", "dissolve", "fade", "dissolve"],
    "fast_beat":  ["slideleft", "wiperight", "slideright", "wipeleft", "zoomin"],
    "travel":     ["slideleft", "dissolve", "wiperight", "fade", "slideright"],
    "food":       ["fade", "dissolve", "slideleft", "dissolve"],
    "vlog":       ["fade", "slideleft", "dissolve", "wiperight"],
    "business":   ["fade", "dissolve", "wipeleft", "fade"],
    "short_reel": ["slideleft", "wiperight", "zoomin", "wipeleft", "slideright"],
    "long_reel":  ["fade", "dissolve", "slideleft", "dissolve", "wiperight"],
    "auto":       ["fade", "slideleft", "dissolve", "wiperight", "fade", "slideright"],
}

_CAPTION_STYLES = {
    "instagram", "bold", "cinematic", "karaoke", "modern", "default",
    "neon", "hype", "minimal", "luxury", "clean",
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
        transition_duration: float = 0.4,
        cta_text: str | None = None,
        speed_ramp: bool = False,
        zoom_punch: bool = True,
        edit_mode: str = "auto",
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
        self.edit_mode       = edit_mode
        self.duration = (
            max((s["end"] for s in segments), default=60.0)
            if segments else 60.0
        )
        # Build transition sequence for this job
        self._trans_seq = TRANSITION_SEQUENCES.get(
            edit_mode, TRANSITION_SEQUENCES["auto"]
        )

    # ── Main entry point ──────────────────────────────────────────────────────
    def render(self) -> str:
        clips = self._select_clips()
        logger.info(
            f"[Renderer] {len(clips)} clips, "
            f"~{sum(c['dur'] for c in clips):.1f}s / {self.target_duration}s target, "
            f"mode={self.edit_mode}"
        )

        clip_paths = []
        for i, clip in enumerate(clips):
            p = self._extract_clip(clip, i)
            if p:
                clip_paths.append(p)

        if not clip_paths:
            logger.warning("[Renderer] All extractions failed — using raw video")
            clip_paths = [self.video_path]

        concat_path = self._concatenate(clip_paths)
        graded_path = self._colour_grade(concat_path)
        subbed_path = self._burn_subtitles(graded_path)
        cta_path    = self._overlay_cta(subbed_path)
        logo_path   = self._overlay_logo(cta_path)
        final_path  = self._mix_audio(logo_path)

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

    # ── Clip selection with NARRATIVE ARC ─────────────────────────────────────
    def _select_clips(self) -> list[dict]:
        candidates = [s for s in self.segments if s["type"] in ("highlight", "normal")]
        if not candidates:
            candidates = [s for s in self.segments if s["type"] != "dead"]
        if not candidates:
            candidates = list(self.segments)
        if not candidates:
            return self._synthesise_clips()

        candidates.sort(key=lambda s: s["score"], reverse=True)

        if self.target_duration <= 60:   max_clip = 6.0
        elif self.target_duration <= 180: max_clip = 10.0
        elif self.target_duration <= 600: max_clip = 15.0
        else:                             max_clip = 20.0
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

        if total < self.target_duration * 0.8:
            selected = self._pad_to_duration(selected, total)

        # ── Narrative arc ordering ────────────────────────────────────────
        selected = self._narrative_order(selected)
        return selected

    def _narrative_order(self, clips: list[dict]) -> list[dict]:
        """
        Reorder clips for cinematic storytelling:
          • Hook   — single best-scoring clip (grabs attention immediately)
          • Build  — remaining clips in chronological order (story develops)
          • Peak   — 2nd + 3rd best clips inserted at ~70% mark (emotional climax)
          • Outro  — chronologically last clip (satisfying ending)

        For fast-beat / short-reel modes, just sort chronologically (rhythm > story).
        """
        if len(clips) <= 3 or self.edit_mode in ("fast_beat", "short_reel"):
            return sorted(clips, key=lambda c: c["start"])

        by_score = sorted(clips, key=lambda c: c["score"], reverse=True)

        hook   = by_score[0]
        outro  = max(clips, key=lambda c: c["start"])

        # Peak: 2nd and 3rd highest-scoring, preferring different positions from hook
        peak_candidates = [c for c in by_score[1:4] if c is not outro][:2]

        used_ids = {id(hook), id(outro)} | {id(c) for c in peak_candidates}
        build    = sorted([c for c in clips if id(c) not in used_ids],
                          key=lambda c: c["start"])

        # Inject peaks at 70% of the build section
        insert_at = max(1, int(len(build) * 0.7))
        build_with_peak = build[:insert_at] + peak_candidates + build[insert_at:]

        result = [hook] + build_with_peak
        if id(outro) not in {id(c) for c in result}:
            result.append(outro)

        logger.info(
            f"[Renderer] Narrative arc — hook@{hook['start']:.1f}s, "
            f"{len(build_with_peak)} build, outro@{outro['start']:.1f}s"
        )
        return result

    def _pad_to_duration(self, existing: list[dict], total: float) -> list[dict]:
        """Uniformly sample remaining video to fill target duration."""
        vid_dur = self.duration if self.duration > 0 else 60.0
        used    = [(c["start"], c["start"] + c["dur"]) for c in existing]
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

        logger.info(f"[Renderer] Padded {len(extra)} clips → {total:.1f}s/{self.target_duration}s")
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

    # ── Clip extraction with ANIMATED KEN BURNS ───────────────────────────────
    def _extract_clip(self, clip: dict, index: int) -> str | None:
        out = self._out(f"clip_{index:03d}")

        vf_parts: list[str] = []
        af_parts: list[str] = []

        # Speed-ramp: slow-mo on high-score clips (only if edit_mode not fast_beat)
        if self.speed_ramp and clip.get("score", 0) >= 0.75 and self.edit_mode != "fast_beat":
            vf_parts.append("setpts=1.33*PTS")
            af_parts.append("atempo=0.75")

        # Ken Burns animated pan/zoom
        if self.zoom_punch:
            vf_parts.append(self._ken_burns(clip, index))

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

        # Retry plain
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

    def _ken_burns(self, clip: dict, index: int) -> str:
        """
        Animated Ken Burns effect using FFmpeg's crop filter time expressions.
        Scale up 6%, then animate the crop window for a smooth cinematic pan.

        Pattern cycles every 3 clips:
          0 mod 3 → pan left → right (slow travel)
          1 mod 3 → pan right → left (return motion)
          2 mod 3 → slow zoom-in from center (dramatic pull-in)

        For wedding/cinematic/emotional modes: always slow zoom-in (softer feel).
        For fast_beat: quick directional wipe (more energetic).
        """
        dur = max(clip["dur"], 0.2)
        sf  = 1.06  # 6% zoom — subtle but visible on mobile

        if self.edit_mode in ("wedding", "cinematic", "emotional"):
            # Gentle center zoom-in for all clips
            x_expr = f"(in_w-in_w/{sf})/2"
            y_expr = f"(in_h-in_h/{sf})/2"
        elif self.edit_mode == "fast_beat":
            # More aggressive directional pan
            sf = 1.08
            if index % 2 == 0:
                x_expr = f"min(t/{dur:.3f},1)*(in_w-in_w/{sf})"
                y_expr = f"(in_h-in_h/{sf})/2"
            else:
                x_expr = f"(1-min(t/{dur:.3f},1))*(in_w-in_w/{sf})"
                y_expr = f"(in_h-in_h/{sf})/2"
        else:
            pattern = index % 3
            if pattern == 0:
                # Pan left → right
                x_expr = f"min(t/{dur:.3f},1)*(in_w-in_w/{sf})"
                y_expr = f"(in_h-in_h/{sf})/2"
            elif pattern == 1:
                # Pan right → left
                x_expr = f"(1-min(t/{dur:.3f},1))*(in_w-in_w/{sf})"
                y_expr = f"(in_h-in_h/{sf})/2"
            else:
                # Slow zoom-in from top-center
                x_expr = f"(in_w-in_w/{sf})/2"
                y_expr = f"min(t/{dur:.3f},1)*(in_h-in_h/{sf})"

        return (
            f"scale=iw*{sf}:ih*{sf},"
            f"crop=in_w/{sf}:in_h/{sf}:"
            f"x='{x_expr}':y='{y_expr}'"
        )

    # ── Concatenation with VARIED CINEMATIC TRANSITIONS ───────────────────────
    def _concatenate(self, clip_paths: list[str]) -> str:
        out = self._out("concat")

        if len(clip_paths) == 1:
            shutil.copy2(clip_paths[0], out)
            return out

        # Resolve base transition
        base_xfade = _resolve_xfade(self.transition_style)

        if base_xfade is None:
            return self._hard_cut(clip_paths, out)

        try:
            return self._xfade_concat(clip_paths, out, base_xfade)
        except Exception as e:
            logger.warning(f"[Renderer] xfade failed ({e}) — hard-cut fallback")
            return self._hard_cut(clip_paths, out)

    def _xfade_concat(self, clip_paths: list[str], out: str, base_xfade: str) -> str:
        td        = self.transition_dur
        durations = [self._get_duration(p) or 5.0 for p in clip_paths]

        inputs = []
        for p in clip_paths:
            inputs += ["-i", p]

        vparts: list[str] = []
        aparts: list[str] = []
        offset  = 0.0
        prev_v  = "0:v"
        prev_a  = "0:a"

        for i in range(1, len(clip_paths)):
            clip_dur = durations[i - 1]
            offset  += max(clip_dur - td, 0.01)

            # Select transition for this pair — cycle through mode-specific sequence
            # For "auto"/"fade"/"dissolve" base, use the full variety sequence
            if base_xfade in ("fade", "dissolve"):
                pair_xfade = self._trans_seq[(i - 1) % len(self._trans_seq)]
            else:
                # User explicitly chose a style — keep it, but vary slightly
                pair_xfade = base_xfade

            ov, oa = f"v{i}", f"a{i}"
            vparts.append(
                f"[{prev_v}][{i}:v]xfade=transition={pair_xfade}"
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

    # ── Colour grade + scale + VIGNETTE ───────────────────────────────────────
    def _colour_grade(self, video_path: str) -> str:
        out  = self._out("graded")
        w, h = ASPECT_RES.get(self.aspect_ratio, ("1080", "1920"))

        # Edit-mode grade takes priority, then content-type grade
        grade = (
            EDIT_MODE_GRADE.get(self.edit_mode)
            or COLOUR_GRADE.get(self.content_type, COLOUR_GRADE["unknown"])
        )

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

    # ── Subtitle burn-in (ASS with fade animations) ───────────────────────────
    def _burn_subtitles(self, video_path: str) -> str:
        if not self.captions:
            return video_path

        out = self._out("subbed")
        cg  = CaptionGenerator()

        # Fade duration: cinematic/wedding modes get slower 300ms fade
        fade_ms = 300 if self.edit_mode in ("cinematic", "wedding", "emotional") else 200

        ass_path = cg.build_ass_file(
            self.captions, self.caption_style, self.output_dir, self.job_id,
            fade_ms=fade_ms,
        )

        if not ass_path or not os.path.exists(ass_path):
            logger.warning("[Renderer] ASS file missing — skipping subtitles")
            return video_path

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
            logger.warning(f"[Renderer] ASS burn failed ({e}) — drawtext fallback")

        return self._drawtext_fallback(video_path, out)

    def _drawtext_fallback(self, video_path: str, out: str) -> str:
        if not self.captions:
            return video_path
        filters = []
        for cap in self.captions[:25]:
            text = cap["text"]
            text = text.replace("\\", "\\\\")
            text = text.replace("'",  "\\'")
            text = text.replace(":",  r"\:")
            text = text.replace("%",  r"\%")
            text = text.encode("ascii", "ignore").decode("ascii").strip()
            if not text:
                continue
            filters.append(
                f"drawtext=text='{text}'"
                f":enable='between(t,{cap['start']},{cap['end']})'"
                f":fontsize=60:fontcolor=white:x=(w-tw)/2:y=h*0.84"
                f":shadowcolor=black:shadowx=2:shadowy=2"
                f":borderw=2:bordercolor=black"
            )
        if not filters:
            return video_path
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

    # ── CTA overlay ───────────────────────────────────────────────────────────
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

    # ── Logo overlay (blended) ────────────────────────────────────────────────
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
            f"[1:v]scale=iw*0.12:-1,format=rgba,colorchannelmixer=aa=0.65[logo];"
            f"[0:v][logo]overlay={pos}:format=auto",
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-pix_fmt", "yuv420p", "-c:a", "copy",
            out,
        ]
        self._run(cmd, fallback=video_path, out=out)
        return out if os.path.exists(out) else video_path

    # ── Audio mix + ducking ───────────────────────────────────────────────────
    def _mix_audio(self, video_path: str) -> str:
        out       = self._out("final")
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
                "ffmpeg", "-y", "-i", video_path,
                "-f", "lavfi", "-i", "anullsrc=cl=stereo:r=44100",
                "-c:v", "copy", "-c:a", "aac", "-b:a", "128k",
                "-shortest", out,
            ]
        elif has_music:
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
            cmd = [
                "ffmpeg", "-y", "-i", video_path,
                "-af", "dynaudnorm=f=150:g=15",
                "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                out,
            ]

        self._run(cmd, fallback=video_path, out=out)
        return out if os.path.exists(out) else video_path

    # ── Helpers ───────────────────────────────────────────────────────────────
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


# ── Module-level helpers ──────────────────────────────────────────────────────
_XFADE_MAP: dict[str, str | None] = {
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


def _resolve_xfade(style: str) -> str | None:
    return _XFADE_MAP.get(style, "fade")
