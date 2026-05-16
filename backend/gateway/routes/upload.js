const express = require("express");
const multer = require("multer");
const path = require("path");
const { v4: uuidv4 } = require("uuid");
const router = express.Router();

const Job = require("../models/Job");
const { startAnalyze } = require("../services/ai");
const { optionalAuth } = require("../middleware/auth");
const logger = require("../services/logger");

const UPLOADS_DIR = process.env.UPLOADS_DIR || "./uploads";
const MAX_FILE_SIZE = 500 * 1024 * 1024; // 500 MB

// ── Multer config ──────────────────────────────────────────────────
const storage = multer.diskStorage({
  destination: UPLOADS_DIR,
  filename: (req, file, cb) => {
    const ext = path.extname(file.originalname).toLowerCase();
    cb(null, `${uuidv4()}${ext}`);
  },
});

const upload = multer({
  storage,
  limits: { fileSize: MAX_FILE_SIZE },
  fileFilter: (req, file, cb) => {
    const allowed = [".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"];
    const ext = path.extname(file.originalname).toLowerCase();
    if (allowed.includes(ext)) cb(null, true);
    else cb(new Error("Unsupported video format. Allowed: mp4, mov, avi, mkv, webm, m4v"));
  },
});

// POST /api/upload  — upload raw video and queue analysis
router.post("/", optionalAuth, upload.single("video"), async (req, res) => {
  if (!req.file) return res.status(400).json({ error: "No video file provided" });

  const jobId = uuidv4();
  const userId = req.user?.id || "anonymous";

  try {
    const job = await Job.create({
      jobId,
      userId,
      inputFile: req.file.filename,
      inputMimeType: req.file.mimetype,
      fileSizeBytes: req.file.size,
      status: "queued",
      stage: "Queued for analysis",
    });

    // Fire-and-forget: call HF Space directly (no Redis/Bull needed)
    setImmediate(() => startAnalyze(jobId));

    logger.info(`Job ${jobId} created — file: ${req.file.filename}`);
    res.status(201).json({ jobId, status: "queued" });
  } catch (err) {
    logger.error("Upload route error:", err);
    res.status(500).json({ error: "Failed to create job" });
  }
});

// POST /api/upload/audio — upload custom audio for a job
router.post("/audio/:jobId", optionalAuth, upload.single("audio"), async (req, res) => {
  const { jobId } = req.params;
  const job = await Job.findOne({ jobId });
  if (!job) return res.status(404).json({ error: "Job not found" });

  try {
    await Job.findOneAndUpdate({ jobId }, { musicFile: req.file.filename });
    res.json({ ok: true, musicFile: req.file.filename });
  } catch (err) {
    res.status(500).json({ error: "Failed to attach audio" });
  }
});

// Error handler for multer
router.use((err, req, res, next) => {
  if (err.code === "LIMIT_FILE_SIZE") return res.status(413).json({ error: "File too large (max 500 MB)" });
  res.status(400).json({ error: err.message });
});

module.exports = router;
