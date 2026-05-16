#!/usr/bin/env python3
"""
Pre-download AI models so they're cached before first job.
Run once after initial deploy: python scripts/download_models.py
"""
import os

WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base")

print(f"📥 Downloading Whisper model: {WHISPER_MODEL}")
import whisper
whisper.load_model(WHISPER_MODEL)
print("✅ Whisper ready")

print("📥 Downloading CLIP model: ViT-B-32")
import open_clip
open_clip.create_model_and_transforms("ViT-B-32", pretrained="openai")
print("✅ CLIP ready")

print("\n🎉 All models downloaded. You're good to go!")
