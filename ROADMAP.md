# ReelAI — Strategic Roadmap & Engineering Notes

---

## 1. Scalability Improvements

**Phase 1 (0 → 1,000 users/month)**
- Single Docker Compose on a ₹600/mo Hetzner CX21 (4 vCPU, 8 GB) handles ~50 concurrent render jobs.
- MongoDB Atlas Free Tier (512 MB) is sufficient for job metadata. Upgrade to M10 (₹3,500/mo) at 5,000 jobs.
- Use Cloudflare R2 instead of local disk the moment you hit 10 GB of output storage. R2 is free for egress — critical for video delivery.

**Phase 2 (1,000 → 50,000 users/month)**
- Separate gateway (Node.js, 2× replicas behind Cloudflare) from AI workers (GPU pods, auto-scaled via Railway or Vast.ai spot instances).
- Bull queues split: `analyze` (CPU-only workers) and `render` (GPU workers). Route via separate Redis queues.
- MongoDB Atlas M10 with sharding on `userId`. Add Redis cache for `GET /jobs/:id` with 3s TTL to cut DB reads by 80%.
- Add CDN in front of `/outputs/` using Cloudflare Workers or BunnyCDN (cheapest video CDN).

**Phase 3 (50,000+ users/month)**
- Migrate rendering to Kubernetes (K8s) with KEDA auto-scaling based on Bull queue depth.
- Separate read/write DB replicas. Move blobs to Cloudflare R2 with signed URLs expiring in 24h.
- Event-driven architecture: Kafka (or Redpanda) for job state events — enables real-time dashboard, analytics, webhooks.

---

## 2. GPU Optimization Ideas

- **CPU-first, GPU-optional**: Whisper `base` model runs well on CPU (2–4s for 60s video). CLIP classification takes ~200ms on CPU per frame batch. Only the FFmpeg render step benefits significantly from GPU (NVENC encoder, 3× faster).
- **NVENC encoding**: Add `-c:v h264_nvenc -preset p4` to FFmpeg commands when GPU is detected. No model weight — pure hardware speedup.
- **Model quantization**: Use `whisper.cpp` (GGML int8 quantized) for 4× faster CPU transcription. Drop-in replacement via the `whisperx` Python wrapper.
- **Batched CLIP inference**: Queue 8 frames together and run a single `model.encode_image` call instead of 8 separate calls. Saves 70% of GPU time on CLIP.
- **Spot instance strategy**: Vast.ai RTX 3080 at ~₹35/hr. A 30-second reel renders in ~20s on GPU. At ₹20/export you need <2 minutes of GPU time to be profitable.
- **Preload models to shared memory**: Use `torch.multiprocessing.set_start_method('spawn')` with pre-warmed workers so models stay resident. Eliminates cold-start delay (8–12s per worker boot).

---

## 3. Future AI Upgrades

| Feature | Model/Tool | Cost | Timeline |
|---|---|---|---|
| Dance beat-sync with motion | MediaPipe Pose + librosa | Free (CPU) | V2 |
| Better scene scoring | Fine-tuned CLIP on reel dataset | Free after fine-tuning | V2 |
| Auto hook text generation | LLaMA 3 8B (Ollama, local) | Free | V2 |
| Face/expression detection | OpenCV Haar + MediaPipe | Free | V2 |
| Auto colour grading per shot | DeepWB (open-source) | Free | V3 |
| Motion interpolation (slow-mo) | RIFE (open-source) | Free (GPU) | V3 |
| Background music generation | MusicGen (Meta, open-source) | Free (GPU) | V3 |
| Voiceover generation | Coqui TTS / Piper TTS | Free | V3 |
| Generative B-roll | CogVideoX (open-source) | GPU needed | V4 |
| Viral score prediction | Custom XGBoost on engagement data | Build after 10K exports | V4 |

---

## 4. Viral Reel Enhancement Ideas

- **Hook-first editing**: Always put the highest-energy 1.5s frame within the first 0.5s of the reel. Tested by analyzing top-performing TikToks — reduces swipe-away by ~30%.
- **Dynamic text animations**: Replace static `drawtext` with Python-animated subtitle overlays (using MoviePy TextClip with easing). Implement: word-by-word reveal, bounce-in, glow pulse.
- **Auto-trend detection**: Scrape trending audio from RapidAPI (TikTok unofficial API, ~₹0) weekly. Map trending BPM to content types. Suggest "trending beat" as default.
- **Colour pop effect**: Desaturate background, keep food/product in full colour (chroma-key approach with OpenCV). Extremely viral for food reels.
- **Speed ramps**: On beat drops, insert 0.3s of 2× slow-mo → snap to 1× speed. Creates dopamine hit. Implement via FFmpeg `setpts` filter with dynamic timestamps.
- **Auto subtitles as branding**: Generate subtitles in content creator's brand colours. Offer customization in V2 with colour picker.
- **Vertical pan on landscape clips**: If input is 16:9, AI detects the subject (via YOLO) and pans vertically within the frame to follow action rather than static centre crop.
- **Series format**: Auto-generate "Part 1 of 3" reels from long-form content (>5 min). Each part gets its own hook. Increases return visits.

---

## 5. Rendering Optimization

- **Segment cache**: Store pre-processed clip segments (trimmed, graded, 9:16 converted) per scene. When user re-renders with a different template, only re-composite — skip per-clip FFmpeg re-encode (saves 60% of render time).
- **Two-pass encode only on paid exports**: Use faster `-crf 28 -preset ultrafast` for the watermarked preview. Reserve `-crf 18 -preset slow` for the paid HD output. Saves 3× encoding time for preview.
- **Parallel FFmpeg**: Process independent clips concurrently using Python `asyncio.gather` with `asyncio.create_subprocess_exec`. On a 4-core CPU: 3× speedup for 3-clip reels.
- **Resolution tiering**: Generate 720p preview in <10s for immediate playback. Render 1080p HD in background. Only deliver 1080p after payment.
- **Redis-cached analysis**: Store full analysis result (segments, captions, beats, dominant_colors) in Redis with 24h TTL. Re-renders skip analysis completely.
- **Input pre-processing pipeline**: Always compress/transcode input to H.264 720p before AI processing. Faster OpenCV frame reads + 5× smaller file for multiple passes.

---

## 6. Monetization Expansion

**Current**: ₹20/export (pay-per-use)

**V2 additions**:
- **Monthly Creator Pass**: ₹199/mo — unlimited exports, no watermark, priority rendering. Target: serious content creators posting 15+ reels/month.
- **Agency Plan**: ₹999/mo — 5 team seats, API access, white-label watermark, custom templates. Target: social media agencies.
- **Brand Kits**: ₹499 one-time — upload logo, brand colours, custom fonts. Applied to all future reels. High perceived value, low dev cost.
- **Affiliate program**: Give creators 20% commission per referred paying user. Viral loop within creator communities.
- **Template marketplace**: Sell premium templates at ₹99–₹299 each. Community-created templates with 70/30 revenue split.
- **API access**: ₹5/API render call (min 100 calls prepaid). Target: video SaaS builders, agencies, e-commerce platforms (auto-product-reel generation).
- **White-label**: ₹4,999/mo — rebrand the entire platform. Target: real estate agencies, food chains, e-commerce platforms.

**Estimated revenue at 1,000 MAU**:
- 300 pay-per-use @ ₹20 = ₹6,000
- 50 Creator Pass @ ₹199 = ₹9,950
- 5 Agency @ ₹999 = ₹4,995
- Total MRR: ~₹21,000 (~$250)

---

## 7. Mobile App Roadmap

**Phase 1: PWA (current)**
- `manifest.json` + service worker for offline caching of UI assets.
- Add-to-home-screen prompt via `beforeinstallprompt` event.
- Push notifications via Web Push API (job completion alerts).

**Phase 2: React Native (V2)**
- Single codebase via Expo for iOS + Android.
- Native share sheet: export directly to Instagram Reels, TikTok, YouTube Shorts.
- Camera roll access: pick from device gallery without leaving app.
- Background download: download reel to camera roll natively.

**Phase 3: Native features (V3)**
- Live capture: record directly in-app, instantly queued for AI processing.
- On-device preview rendering (simplified): use WebAssembly FFmpeg.wasm for instant preview without server roundtrip.
- Offline mode: cache templates & presets locally, sync to cloud when connected.

**App Store strategy**: Launch on TestFlight/Google Play Internal Testing at 500 users. Submit for review at 2,000 users. Keep free tier to maximize installs; convert to paid inside app.

---

## 8. Operational Risks

| Risk | Impact | Mitigation |
|---|---|---|
| FFmpeg OOM crash on large videos | High | Set `-t 600` (10 min cap) on all inputs. Pre-compress to 720p before processing. Add memory limit on Docker containers. |
| Celery task stuck/lost | High | `task_acks_late=True` + `visibility_timeout=3600`. Add Flower monitoring dashboard. Dead-letter queue for failed tasks. |
| Storage bloat | Medium | Auto-delete raw uploads after 48h via cron. Auto-delete outputs after 7 days for unpaid jobs. |
| GPU spot instance eviction | Medium | Checkpoint Celery state to Redis before each FFmpeg step. Resume from last completed step on re-queue. |
| Razorpay webhook replay attack | High | Store processed payment IDs in MongoDB with unique index. Idempotent handler rejects duplicates. |
| Copyright music claims | Medium | Only use Creative Commons / royalty-free presets. Add terms of service requiring user-uploaded audio to be user-licensed. |
| Model cold-start latency | Low | Pre-download models in Dockerfile build step. Keep one warm Celery worker always alive (min 1 pod). |
| MongoDB free tier 512MB limit | Medium | Monitor with Atlas alerts. Prune old jobs aggressively. Upgrade at $40 MRR (pays for M10 in INR). |

---

## 9. Cheapest Deployment Strategy

### Zero-to-launch stack (target: <$10/month)

| Service | Provider | Cost |
|---|---|---|
| Frontend (Next.js) | Vercel Free Tier | $0 |
| API Gateway (Node.js) | Railway Starter | $5/mo |
| AI Service + Celery | Railway Starter | $5/mo |
| MongoDB | Atlas Free (512 MB) | $0 |
| Redis | Railway Redis | Included |
| Video Storage | Cloudflare R2 | $0 (10 GB free) |
| CDN | Cloudflare Free | $0 |
| GPU (on demand) | Vast.ai RTX 3060 | ~₹25/hr, use only for bursts |
| **Total** | | **~$10/mo + Vast.ai on demand** |

### Cost at 500 exports/month:
- Vast.ai: 500 renders × 30s each = 250 min = 4.2 hrs × ₹25 = ~₹105/mo (~$1.30)
- Railway: $10/mo
- R2: 500 × 30 MB = 15 GB. First 10 GB free, extra 5 GB = $0.08
- **Total infra: ~$12/month**
- **Revenue: 500 × ₹20 = ₹10,000 (~$120)**
- **Gross margin: ~90%**

### Scale-up trigger points:
- Hit Railway limits → Move to a Hetzner CPX31 (4 vCPU, 8 GB, €13/mo). Self-managed, no vendor lock-in.
- Storage > 50 GB → R2 is still cheaper than S3 (no egress fees = crucial for video).
- GPU demand consistent → Reserve a Vast.ai machine at monthly rate (50% cheaper than on-demand).

---

*ReelAI · Built with FFmpeg, Whisper, CLIP, FastAPI, Next.js · Open-source stack.*
