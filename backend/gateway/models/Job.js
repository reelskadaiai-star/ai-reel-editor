const mongoose = require("mongoose");

const segmentSchema = new mongoose.Schema(
  {
    start: Number,
    end: Number,
    type: { type: String, enum: ["highlight", "dead", "transition", "beat"] },
    score: Number,
    label: String,
  },
  { _id: false }
);

const captionSchema = new mongoose.Schema(
  {
    start: Number,
    end: Number,
    text: String,
    style: { type: String, default: "default" },
  },
  { _id: false }
);

const jobSchema = new mongoose.Schema(
  {
    jobId: { type: String, required: true, unique: true, index: true },
    userId: { type: String, default: "anonymous" },
    status: {
      type: String,
      enum: ["queued", "analyzing", "rendering", "done", "failed"],
      default: "queued",
    },
    progress: { type: Number, default: 0 }, // 0-100
    stage: { type: String, default: "" },   // human-readable current step

    // Input
    inputFile: { type: String, required: true },
    inputMimeType: String,
    durationSeconds: Number,
    fileSizeBytes: Number,

    // AI Analysis results
    contentType: {
      type: String,
      enum: ["real_estate", "food", "product", "dance", "travel", "cinematic", "vlog", "interview", "comedy", "unknown"],
      default: "unknown",
    },
    confidence: Number,
    segments: [segmentSchema],
    captions: [captionSchema],
    beatTimestamps: [Number],
    dominantColors: [String],
    sceneCount: Number,

    // Editing config (user can override)
    template: { type: String, default: "auto" },
    musicFile: String,
    musicOffset: { type: Number, default: 0 },
    aspectRatio: { type: String, default: "9:16" },
    captionStyle: { type: String, default: "modern" },
    transitionStyle: { type: String, default: "auto" },
    targetDurationSec: { type: Number, default: 30 },
    includeHookText: { type: Boolean, default: true },
    hookText: String,

    // Output
    outputFile: String,
    watermarkedFile: String,
    thumbnailFile: String,
    outputResolution: { type: String, default: "1080x1920" },

    // Payment
    paid: { type: Boolean, default: false },
    paymentOrderId: String,
    paymentId: String,

    // Error
    error: String,
    celeryTaskId: String,
  },
  { timestamps: true }
);

jobSchema.index({ userId: 1, createdAt: -1 });
jobSchema.index({ status: 1 });

module.exports = mongoose.model("Job", jobSchema);
