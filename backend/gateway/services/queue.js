const Bull = require("bull");
const axios = require("axios");
const logger = require("./logger");
const Job = require("../models/Job");

const REDIS_URL = process.env.REDIS_URL || "redis://localhost:6379";
const AI_URL = process.env.AI_SERVICE_URL || "http://localhost:8000";

// ── Queues ────────────────────────────────────────────────────────────
const analyzeQueue = new Bull("analyze", REDIS_URL);
const renderQueue = new Bull("render", REDIS_URL);

// ── Process: Analyze ─────────────────────────────────────────────────
analyzeQueue.process(2, async (bullJob) => {
  const { jobId } = bullJob.data;
  logger.info(`[Queue] Analyzing job ${jobId}`);

  await Job.findOneAndUpdate({ jobId }, { status: "analyzing", stage: "Analyzing video content", progress: 5 });

  try {
    const res = await axios.post(`${AI_URL}/analyze`, { job_id: jobId }, { timeout: 120_000 });
    const { task_id } = res.data;

    await Job.findOneAndUpdate({ jobId }, { celeryTaskId: task_id, progress: 10 });
    return { task_id };
  } catch (err) {
    logger.error(`[Analyze] Error for ${jobId}: ${err.message}`);
    await Job.findOneAndUpdate({ jobId }, { status: "failed", error: err.message });
    throw err;
  }
});

// ── Process: Render ───────────────────────────────────────────────────
renderQueue.process(1, async (bullJob) => {
  const { jobId } = bullJob.data;
  logger.info(`[Queue] Rendering job ${jobId}`);

  await Job.findOneAndUpdate({ jobId }, { status: "rendering", stage: "Generating reel", progress: 50 });

  try {
    const job = await Job.findOne({ jobId });
    const res = await axios.post(
      `${AI_URL}/render`,
      {
        job_id: jobId,
        template: job.template,
        music_file: job.musicFile,
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
    const { task_id } = res.data;
    await Job.findOneAndUpdate({ jobId }, { celeryTaskId: task_id, progress: 55 });
    return { task_id };
  } catch (err) {
    logger.error(`[Render] Error for ${jobId}: ${err.message}`);
    await Job.findOneAndUpdate({ jobId }, { status: "failed", error: err.message });
    throw err;
  }
});

// ── Events ────────────────────────────────────────────────────────────
analyzeQueue.on("failed", (job, err) => logger.error(`Analyze job failed: ${job.id} — ${err.message}`));
renderQueue.on("failed", (job, err) => logger.error(`Render job failed: ${job.id} — ${err.message}`));

module.exports = { analyzeQueue, renderQueue };
