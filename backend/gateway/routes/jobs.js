const express = require("express");
const axios = require("axios");
const router = express.Router();

const Job = require("../models/Job");
const { startRender } = require("../services/ai");
const { optionalAuth } = require("../middleware/auth");
const logger = require("../services/logger");

const AI_URL = process.env.AI_SERVICE_URL || "http://localhost:7860";

// GET /api/jobs/:jobId — poll job status + analysis results
router.get("/:jobId", optionalAuth, async (req, res) => {
  const { jobId } = req.params;
  const job = await Job.findOne({ jobId }).lean();
  if (!job) return res.status(404).json({ error: "Job not found" });

  // If AI task is running, sync progress from Celery
  if (job.celeryTaskId && ["analyzing", "rendering"].includes(job.status)) {
    try {
      const { data } = await axios.get(`${AI_URL}/task/${job.celeryTaskId}`, { timeout: 5000 });
      if (data.state === "SUCCESS" && job.status === "analyzing") {
        // AI analysis complete — persist results and move to "done" (analysis phase)
        await Job.findOneAndUpdate(
          { jobId },
          {
            status: "done",
            stage: "Analysis complete — ready to render",
            progress: 40,
            contentType: data.result.content_type,
            confidence: data.result.confidence,
            segments: data.result.segments,
            captions: data.result.captions,
            beatTimestamps: data.result.beat_timestamps,
            dominantColors: data.result.dominant_colors,
            sceneCount: data.result.scene_count,
            durationSeconds: data.result.duration,
            template: data.result.suggested_template,
            hookText: data.result.hook_text,
          }
        );
      } else if (data.state === "SUCCESS" && job.status === "rendering") {
        await Job.findOneAndUpdate(
          { jobId },
          {
            status: "done",
            stage: "Reel ready",
            progress: 100,
            outputFile: data.result.output_file,
            watermarkedFile: data.result.watermarked_file,
            thumbnailFile: data.result.thumbnail_file,
          }
        );
      } else if (data.state === "FAILURE") {
        await Job.findOneAndUpdate({ jobId }, { status: "failed", error: data.traceback });
      } else if (data.state === "PROGRESS") {
        await Job.findOneAndUpdate({ jobId }, { progress: data.meta?.percent || job.progress });
      }
    } catch (_) {
      // AI service unreachable — return stale data
    }
  }

  const fresh = await Job.findOne({ jobId }).lean();
  res.json(fresh);
});

// PATCH /api/jobs/:jobId — update editing preferences (template, music, etc.)
router.patch("/:jobId", optionalAuth, async (req, res) => {
  const { jobId } = req.params;
  const allowed = [
    "template", "musicFile", "musicOffset", "aspectRatio",
    "captionStyle", "transitionStyle", "targetDurationSec",
    "includeHookText", "hookText",
  ];
  const updates = {};
  allowed.forEach((k) => { if (req.body[k] !== undefined) updates[k] = req.body[k]; });

  const job = await Job.findOneAndUpdate({ jobId }, updates, { new: true });
  if (!job) return res.status(404).json({ error: "Job not found" });
  res.json(job);
});

// POST /api/jobs/:jobId/render — kick off reel rendering
router.post("/:jobId/render", optionalAuth, async (req, res) => {
  const { jobId } = req.params;
  const job = await Job.findOne({ jobId });
  if (!job) return res.status(404).json({ error: "Job not found" });
  if (job.status !== "done" || job.progress < 40) {
    return res.status(409).json({ error: "Analysis not complete yet" });
  }
  if (job.outputFile) {
    return res.json({ jobId, status: "already_rendered", outputFile: job.outputFile });
  }

  // Guard against duplicate render requests (e.g. double-click)
  if (job.status === "rendering") {
    return res.json({ jobId, status: "rendering", message: "Already rendering" });
  }

  // Apply any body overrides before rendering
  const overrides = req.body || {};
  if (Object.keys(overrides).length) {
    await Job.findOneAndUpdate({ jobId }, overrides);
  }

  // Fire-and-forget: call HF Space directly (no Redis/Bull needed)
  setImmediate(() => startRender(jobId));
  await Job.findOneAndUpdate({ jobId }, { status: "rendering", stage: "Rendering queued", progress: 50 });

  res.json({ jobId, status: "rendering" });
});

// GET /api/jobs/:jobId/download — redirect to output file (post-payment)
router.get("/:jobId/download", optionalAuth, async (req, res) => {
  const { jobId } = req.params;
  const job = await Job.findOne({ jobId });
  if (!job) return res.status(404).json({ error: "Not found" });
  if (!job.outputFile) return res.status(409).json({ error: "Not rendered yet" });

  return res.redirect(`/outputs/${job.outputFile}`);
});

module.exports = router;
