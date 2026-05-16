const mongoose = require("mongoose");

const userSchema = new mongoose.Schema(
  {
    email: { type: String, unique: true, sparse: true },
    phone: { type: String, unique: true, sparse: true },
    name: String,
    plan: { type: String, enum: ["free", "pro"], default: "free" },
    exportsUsed: { type: Number, default: 0 },
    totalPaid: { type: Number, default: 0 }, // in paise
    razorpayCustomerId: String,
    avatarUrl: String,
    isActive: { type: Boolean, default: true },
  },
  { timestamps: true }
);

module.exports = mongoose.model("User", userSchema);
