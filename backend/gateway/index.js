require("dotenv").config();
const express = require("express");
const cors = require("cors");
const helmet = require("helmet");
const morgan = require("morgan");
const rateLimit = require("express-rate-limit");
const mongoose = require("mongoose");
const path = require("path");
const fs = require("fs");

const logger = require("./services/logger");
const uploadRoutes = require("./routes/upload");
const jobRoutes = require("./routes/jobs");
const paymentRoutes = require("./routes/payment");
const authRoutes = require("./routes/auth");
const templateRoutes = require("./routes/templates");

const app = express();
const PORT = process.env.PORT || 4000;

// ── Ensure upload/output dirs exist ──────────────────────────────────
[process.env.UPLOADS_DIR || "./uploads", process.env.OUTPUTS_DIR || "./outputs"].forEach((d) => {
  if (!fs.existsSync(d)) fs.mkdirSync(d, { recursive: true });
});

// ── Middleware ────────────────────────────────────────────────────────
app.use(helmet({ crossOriginEmbedderPolicy: false }));
app.use(
  cors({
    origin: process.env.FRONTEND_URL || "*",
    credentials: true,
  })
);
app.use(morgan("combined", { stream: { write: (msg) => logger.info(msg.trim()) } }));
app.use(express.json({ limit: "2mb" }));
app.use(express.urlencoded({ extended: true }));

// Rate limiting
const apiLimiter = rateLimit({
  windowMs: 15 * 60 * 1000, // 15 min
  max: 100,
  standardHeaders: true,
  legacyHeaders: false,
  message: { error: "Too many requests, slow down." },
});
app.use("/api/", apiLimiter);

// Serve processed outputs (behind signed check in production)
app.use("/outputs", express.static(path.resolve(process.env.OUTPUTS_DIR || "./outputs")));

// ── Routes ────────────────────────────────────────────────────────────
app.use("/api/auth", authRoutes);
app.use("/api/upload", uploadRoutes);
app.use("/api/jobs", jobRoutes);
app.use("/api/payment", paymentRoutes);
app.use("/api/templates", templateRoutes);

// Health
app.get("/health", (req, res) => res.json({ status: "ok", ts: Date.now() }));

// 404
app.use((req, res) => res.status(404).json({ error: "Not found" }));

// Global error handler
app.use((err, req, res, next) => {
  logger.error(err.stack || err.message);
  res.status(err.status || 500).json({ error: err.message || "Internal server error" });
});

// ── DB & Start ────────────────────────────────────────────────────────
async function start() {
  const uri = process.env.MONGO_URI;
  if (!uri) {
    logger.error("❌ MONGO_URI environment variable is not set!");
    process.exit(1);
  }
  // Log a masked URI so we can confirm it's being picked up
  const masked = uri.replace(/:([^@]+)@/, ":****@");
  logger.info(`🔌 Connecting to MongoDB: ${masked}`);

  try {
    await mongoose.connect(uri, {
      serverSelectionTimeoutMS: 10000,
    });
    logger.info("✅ MongoDB connected");
    app.listen(PORT, () => logger.info(`🚀 Gateway running on port ${PORT}`));
  } catch (err) {
    logger.error(`❌ MongoDB connection failed: ${err.message}`);
    process.exit(1);
  }
}

start();
