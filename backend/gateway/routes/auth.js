const express = require("express");
const router = express.Router();
const User = require("../models/User");
const { signToken } = require("../middleware/auth");

// Minimal anonymous/email auth — extend with OTP/Google OAuth later
router.post("/login", async (req, res) => {
  const { email } = req.body;
  if (!email) return res.status(400).json({ error: "email required" });

  let user = await User.findOne({ email });
  if (!user) user = await User.create({ email });

  const token = signToken({ id: user._id.toString(), email: user.email });
  res.json({ token, user: { id: user._id, email: user.email, plan: user.plan } });
});

// Anonymous session (no email required)
router.post("/anonymous", async (req, res) => {
  const token = signToken({ id: `anon_${Date.now()}`, anon: true });
  res.json({ token });
});

module.exports = router;
