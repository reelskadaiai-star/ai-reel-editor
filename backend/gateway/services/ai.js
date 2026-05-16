/**
 * Direct HTTP calls to the HuggingFace Space AI service.
 * Replaces Bull/Redis queues — fire-and-forget background tasks.
 */
const axios = require("axios");
const logger = require("./logger");
const Job = require("../models/Job");

const AI_URL = process.env.AI_SERVICE_URL || "http://localhost:7860";
const GATEWAY_URL = process.env.GATEWAY_PUBLIC_URL || "http://localhost:4000";

function videoUrl(filename) {
  return `${GATEWAY_URL}/uploads/${filename}`;
}

// ── Analyze ───────────────────────────────────────────────────────────
async function startAnalyze(jobId) {
  logger.info(`[AI] Starting analyze for job ${jobId}`);
  await Job.findOneAndUpdate({ jobId }, { status: "analyzing", stage: "Analyzing video content", progress: 5 });

  try {
    const job = await Job.findOne({ jobId });
    const { data } = await axios.post(
      `${AI_URL}/analyze`,
      { job_id: jobId, video_url: videoUrl(job.inputFile) },
      { timeout: 120_000 }
    );
    await Job.findOneAndUpdate({ jobId }, { celeryTaskId: data.task_id, progress: 10 });
    logger.info(`[AI] Analyze task started: ${data.task_id}`);
  } catch (err) {
    logger.error(`[AI] Analyze failed for ${jobId}: ${err.message}`);
    await Job.findOneAndUpdate({ jobId }, { status: "failed", error: err.message });
  }
}

// ── Render ────────────────────────────────────────────────────────────
async function startRender(jobId) {
  logger.info(`[AI] Starting render for job ${jobId}`);
  await Job.findOneAndUpdate({ jobId }, { status: "rendering", stage: "Generating reel", progress: 50 });

  try {
    const job = await Job.findOne({ jobId });
    const { data } = await axios.post(
      `${AI_URL}/render`,
      {
        job_id: jobId,
        video_url: videoUrl(job.inputFile),
        music_url: job.musicFile ? videoUrl(job.musicFile) : null,
        template: job.template,
        music_offset: job.musicOffset,
        aspect_ratio: job.aspectRatio,
        caption_style: job.captionStyle,
        transition_style: job.transitionStyle,
        target_duration: job.targetDurationSec,
        include_hook: job.includeHookText,
        hook_text: job.hookText,
      },
      { timeout: 300_000 }
    );
    await Job.findOneAndUpdate({ jobId }, { celeryTaskId: data.task_id, progress: 55 });
    logger.info(`[AI] Render task started: ${data.task_id}`);
  } catch (err) {
    logger.error(`[AI] Render failed for ${jobId}: ${err.message}`);
    await Job.findOneAndUpdate({ jobId }, { status: "failed", error: err.message });
  }
}

module.exports = { startAnalyze, startRender };
