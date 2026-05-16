const express = require("express");
const Razorpay = require("razorpay");
const crypto = require("crypto");
const router = express.Router();

const Job = require("../models/Job");
const User = require("../models/User");
const { optionalAuth } = require("../middleware/auth");
const logger = require("../services/logger");

const razorpay = new Razorpay({
  key_id: process.env.RAZORPAY_KEY_ID,
  key_secret: process.env.RAZORPAY_KEY_SECRET,
});

const EXPORT_PRICE_INR_PAISE = parseInt(process.env.EXPORT_PRICE_INR || "2000", 10); // 2000 paise = ₹20

// POST /api/payment/create-order
router.post("/create-order", optionalAuth, async (req, res) => {
  const { jobId } = req.body;
  if (!jobId) return res.status(400).json({ error: "jobId required" });

  const job = await Job.findOne({ jobId });
  if (!job) return res.status(404).json({ error: "Job not found" });
  if (job.paid) return res.json({ alreadyPaid: true });
  if (!job.outputFile && !job.watermarkedFile) {
    return res.status(409).json({ error: "Reel not rendered yet. Render first." });
  }

  try {
    const order = await razorpay.orders.create({
      amount: EXPORT_PRICE_INR_PAISE,
      currency: "INR",
      receipt: jobId.slice(0, 40),
      notes: { jobId, userId: job.userId },
    });

    await Job.findOneAndUpdate({ jobId }, { paymentOrderId: order.id });

    res.json({
      orderId: order.id,
      amount: order.amount,
      currency: order.currency,
      key: process.env.RAZORPAY_KEY_ID,
    });
  } catch (err) {
    logger.error("Razorpay order creation error:", err);
    res.status(500).json({ error: "Payment gateway error" });
  }
});

// POST /api/payment/verify — called by frontend after Razorpay success
router.post("/verify", optionalAuth, async (req, res) => {
  const { razorpay_order_id, razorpay_payment_id, razorpay_signature, jobId } = req.body;

  if (!razorpay_order_id || !razorpay_payment_id || !razorpay_signature || !jobId) {
    return res.status(400).json({ error: "Missing payment fields" });
  }

  // HMAC-SHA256 verification
  const expected = crypto
    .createHmac("sha256", process.env.RAZORPAY_KEY_SECRET)
    .update(`${razorpay_order_id}|${razorpay_payment_id}`)
    .digest("hex");

  if (expected !== razorpay_signature) {
    logger.warn(`Payment signature mismatch for job ${jobId}`);
    return res.status(400).json({ error: "Invalid payment signature" });
  }

  await Job.findOneAndUpdate({ jobId }, { paid: true, paymentId: razorpay_payment_id });

  // Update user stats
  if (req.user?.id) {
    await User.findByIdAndUpdate(req.user.id, {
      $inc: { exportsUsed: 1, totalPaid: EXPORT_PRICE_INR_PAISE },
    });
  }

  logger.info(`Payment verified for job ${jobId}, payment ${razorpay_payment_id}`);
  res.json({ success: true, downloadUrl: `/api/jobs/${jobId}/download` });
});

// POST /api/payment/webhook — Razorpay server-to-server webhook (backup)
router.post("/webhook", express.raw({ type: "application/json" }), async (req, res) => {
  const sig = req.headers["x-razorpay-signature"];
  const body = req.body.toString();

  const expected = crypto
    .createHmac("sha256", process.env.RAZORPAY_WEBHOOK_SECRET)
    .update(body)
    .digest("hex");

  if (expected !== sig) {
    logger.warn("Webhook signature mismatch");
    return res.status(400).send("Invalid signature");
  }

  const event = JSON.parse(body);
  if (event.event === "payment.captured") {
    const notes = event.payload.payment.entity.notes || {};
    if (notes.jobId) {
      await Job.findOneAndUpdate({ jobId: notes.jobId }, { paid: true });
      logger.info(`Webhook: payment captured for job ${notes.jobId}`);
    }
  }

  res.json({ status: "ok" });
});

module.exports = router;
