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

// Separate multer instance for image uploads (logos)
const imageUpload = multer({
  storage,
  limits: { fileSize: 5 * 1024 * 1024 }, // 5 MB
  fileFilter: (req, file, cb) => {
    const allowed = [".png", ".jpg", ".jpeg", ".webp", ".svg"];
    const ext = path.extname(file.originalname).toLowerCase();
    if (allowed.includes(ext)) cb(null, true);
    else cb(new Error("Unsupported image format. Allowed: png, jpg, jpeg, webp, svg"));
  },
});

// POST /api/upload — upload a single video and queue analysis
router.post("/", optionalAuth, upload.single("video"), async (req, res) => {
  if (!req.file) return res.status(400).json({ error: "No video file provided" });

  const jobId = uuidv4();
  const userId = req.user?.id || "anonymous";

  try {
    await Job.create({
      jobId,
      userId,
      inputFile: req.file.filename,
      inputMimeType: req.file.mimetype,
      fileSizeBytes: req.file.size,
      status: "queued",
      stage: "Queued for analysis",
    });

    setImmediate(() => startAnalyze(jobId));
    logger.info(`Job ${jobId} created — file: ${req.file.filename}`);
    res.status(201).json({ jobId, status: "queued" });
  } catch (err) {
    logger.error("Upload route error:", err);
    res.status(500).json({ error: "Failed to create job" });
  }
});

// POST /api/upload/multi — upload up to 5 video clips; HF Space merges before analysis
router.post("/multi", optionalAuth, upload.array("videos", 5), async (req, res) => {
  if (!req.files || req.files.length === 0)
    return res.status(400).json({ error: "No video files provided" });

  const jobId = uuidv4();
  const userId = req.user?.id || "anonymous";
  const [primary, ...extras] = req.files;

  try {
    await Job.create({
      jobId,
      userId,
      inputFile: primary.filename,
      inputFiles: extras.map((f) => f.filename),
      inputMimeType: primary.mimetype,
      fileSizeBytes: req.files.reduce((s, f) => s + f.size, 0),
      status: "queued",
      stage: `Queued — merging ${req.files.length} clip${req.files.length > 1 ? "s" : ""}`,
    });

    setImmediate(() => startAnalyze(jobId));
    logger.info(`Job ${jobId} created (multi) — ${req.files.length} clips`);
    res.status(201).json({ jobId, status: "queued", clipCount: req.files.length });
  } catch (err) {
    logger.error("Multi-upload route error:", err);
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

// POST /api/upload/logo/:jobId — upload logo image for watermark overlay
router.post("/logo/:jobId", optionalAuth, imageUpload.single("logo"), async (req, res) => {
  const { jobId } = req.params;
  const job = await Job.findOne({ jobId });
  if (!job) return res.status(404).json({ error: "Job not found" });
  if (!req.file) return res.status(400).json({ error: "No image file provided" });

  try {
    await Job.findOneAndUpdate({ jobId }, { logoFile: req.file.filename });
    res.json({ ok: true, logoFile: req.file.filename });
  } catch (err) {
    res.status(500).json({ error: "Failed to attach logo" });
  }
});

// Error handler for multer
router.use((err, req, res, next) => {
  if (err.code === "LIMIT_FILE_SIZE") return res.status(413).json({ error: "File too large (max 500 MB)" });
  res.status(400).json({ error: err.message });
});

module.exports = router;
