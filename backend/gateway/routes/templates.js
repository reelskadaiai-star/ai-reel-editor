const express = require("express");
const router = express.Router();

// Static template registry — extend with DB persistence later
const TEMPLATES = [
  {
    id: "real_estate_luxury",
    name: "Luxury Real Estate",
    contentType: "real_estate",
    description: "Cinematic smooth zooms, elegant transitions, luxury caption style",
    previewUrl: "/assets/templates/real_estate_luxury.jpg",
    tags: ["cinematic", "zoom", "smooth", "luxury"],
    captionStyle: "luxury",
    transitionStyle: "smooth_zoom",
    targetDurationSec: 30,
    musicSuggestion: "cinematic_ambient",
  },
  {
    id: "real_estate_modern",
    name: "Modern Property Tour",
    contentType: "real_estate",
    description: "Clean cuts, minimal text overlays, professional feel",
    previewUrl: "/assets/templates/real_estate_modern.jpg",
    tags: ["clean", "minimal", "professional"],
    captionStyle: "minimal",
    transitionStyle: "cross_dissolve",
    targetDurationSec: 45,
    musicSuggestion: "upbeat_corporate",
  },
  {
    id: "food_vibrant",
    name: "Viral Food Reel",
    contentType: "food",
    description: "Fast cuts, vibrant color grade, close-up emphasis, hunger-inducing",
    previewUrl: "/assets/templates/food_vibrant.jpg",
    tags: ["fast", "vibrant", "close-up"],
    captionStyle: "bold",
    transitionStyle: "fast_cut",
    targetDurationSec: 15,
    musicSuggestion: "trending_pop",
  },
  {
    id: "food_asmr",
    name: "ASMR Food",
    contentType: "food",
    description: "Slow cuts, satisfying sounds, macro shots",
    previewUrl: "/assets/templates/food_asmr.jpg",
    tags: ["slow", "asmr", "satisfying"],
    captionStyle: "minimal",
    transitionStyle: "slow_fade",
    targetDurationSec: 30,
    musicSuggestion: "calm_ambient",
  },
  {
    id: "product_showcase",
    name: "Product Showcase",
    contentType: "product",
    description: "360-degree highlight, feature callouts, clean background",
    previewUrl: "/assets/templates/product_showcase.jpg",
    tags: ["product", "360", "callout"],
    captionStyle: "feature_callout",
    transitionStyle: "slide_in",
    targetDurationSec: 20,
    musicSuggestion: "energetic_electronic",
  },
  {
    id: "product_unboxing",
    name: "Unboxing Hype",
    contentType: "product",
    description: "High energy, beat sync, reaction-style",
    previewUrl: "/assets/templates/product_unboxing.jpg",
    tags: ["hype", "beat", "energy"],
    captionStyle: "hype",
    transitionStyle: "beat_sync",
    targetDurationSec: 25,
    musicSuggestion: "trap_beat",
  },
];

// GET /api/templates — list all, optionally filter by contentType
router.get("/", (req, res) => {
  const { contentType } = req.query;
  const list = contentType
    ? TEMPLATES.filter((t) => t.contentType === contentType)
    : TEMPLATES;
  res.json(list);
});

// GET /api/templates/:id
router.get("/:id", (req, res) => {
  const t = TEMPLATES.find((t) => t.id === req.params.id);
  if (!t) return res.status(404).json({ error: "Template not found" });
  res.json(t);
});

module.exports = router;
