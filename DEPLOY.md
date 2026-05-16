# ReelAI — Production Deployment Guide

Stack: **Render** (backend) · **Cloudflare Pages** (frontend) · **MongoDB Atlas** (DB) · **Vast.ai** (GPU on demand)

---

## Prerequisites checklist

- [ ] GitHub repo created and code pushed to `main`
- [ ] [Render account](https://render.com) (free signup)
- [ ] [Cloudflare account](https://cloudflare.com) (free signup)
- [ ] [MongoDB Atlas account](https://cloud.mongodb.com) (free tier)
- [ ] [Razorpay live keys](https://dashboard.razorpay.com) (`rzp_live_...`)
- [ ] [Vast.ai account](https://vast.ai) + API key (for GPU renders)
- [ ] [Docker Hub account](https://hub.docker.com) (for the GPU image)

---

## Step 1 — MongoDB Atlas (database)

1. Go to **cloud.mongodb.com** → Create a free M0 cluster (region: Mumbai / Singapore)
2. **Database Access** → Add user → username `reel` → auto-generate password → copy it
3. **Network Access** → Add IP → `0.0.0.0/0` (allows Render + Vast.ai)
4. **Connect** → Drivers → copy the connection string:
   ```
   mongodb+srv://reel:<password>@cluster0.xxxxx.mongodb.net/reeldb?retryWrites=true&w=majority
   ```
   Save this as `MONGO_URI` — you'll need it in Step 2.

---

## Step 2 — Render (backend)

### 2a. Deploy via Blueprint (easiest)

1. Go to **dashboard.render.com** → **Blueprints** → **New Blueprint Instance**
2. Connect your GitHub repo → select `main` branch
3. Render reads `render.yaml` and creates all services automatically
4. After services appear, set the **secret env vars** manually (Blueprint can't commit secrets):

| Service | Key | Value |
|---|---|---|
| `reel-gateway` | `MONGO_URI` | Your Atlas connection string |
| `reel-gateway` | `RAZORPAY_KEY_ID` | `rzp_live_xxxxx` |
| `reel-gateway` | `RAZORPAY_KEY_SECRET` | your secret |
| `reel-gateway` | `RAZORPAY_WEBHOOK_SECRET` | create one in Razorpay dashboard |
| `reel-gateway` | `FRONTEND_URL` | `https://reel-ai.pages.dev` (your CF Pages URL) |
| `reel-gateway` | `CLOUDFLARE_R2_ENDPOINT` | (see Step 3) |
| `reel-gateway` | `S3_BUCKET` | your R2 bucket name |
| `reel-gateway` | `AWS_ACCESS_KEY_ID` | R2 access key ID |
| `reel-gateway` | `AWS_SECRET_ACCESS_KEY` | R2 secret key |
| All services | same R2/storage vars | copy from gateway |

### 2b. Get your service URLs

After first deploy, grab these from the Render dashboard:
- Gateway: `https://reel-gateway.onrender.com`
- AI Service: `https://reel-ai-service.onrender.com`

### 2c. Get deploy hook URLs (for GitHub Actions)

For each service: **Settings** → **Deploy Hook** → copy the URL.
Save these as GitHub secrets (Step 4).

### 2d. Razorpay webhook

In Razorpay Dashboard → **Webhooks** → Add webhook:
- URL: `https://reel-gateway.onrender.com/api/payment/webhook`
- Events: `payment.captured`
- Secret: same as `RAZORPAY_WEBHOOK_SECRET`

---

## Step 3 — Cloudflare R2 (video storage)

Render's disk is ephemeral across deploys. Use R2 for permanent storage.

1. Cloudflare Dashboard → **R2** → **Create bucket** → name: `reel-videos`
2. **Manage R2 API Tokens** → Create token (Object Read & Write on your bucket)
3. Copy: **Access Key ID**, **Secret Access Key**, **Endpoint URL**
   - Endpoint format: `https://<account-id>.r2.cloudflarestorage.com`
4. Add these to all Render services (gateway, ai-service, celery-worker):
   ```
   STORAGE_TYPE=r2
   CLOUDFLARE_R2_ENDPOINT=https://<account-id>.r2.cloudflarestorage.com
   S3_BUCKET=reel-videos
   AWS_ACCESS_KEY_ID=<r2-access-key>
   AWS_SECRET_ACCESS_KEY=<r2-secret-key>
   ```

> **Note:** The app uses boto3-compatible S3 calls, which work identically with R2.
> You'll need to add `boto3` to `requirements.txt` and a storage service adapter — see Step 3b.

### 3b. Add R2 storage adapter to AI service

Add to `backend/ai-service/requirements.txt`:
```
boto3==1.34.101
```

The renderer already writes to `OUTPUTS_DIR`. For prod, add an upload step after render completes in `workers/tasks.py`:
```python
# After render completes, upload to R2
if os.getenv("STORAGE_TYPE") == "r2":
    _upload_to_r2(output_file, watermarked_file, thumbnail_file)
```

---

## Step 4 — GitHub Actions secrets

In your GitHub repo → **Settings** → **Secrets and variables** → **Actions** → add:

| Secret name | Value |
|---|---|
| `NEXT_PUBLIC_API_URL` | `https://reel-gateway.onrender.com` |
| `NEXT_PUBLIC_RAZORPAY_KEY` | `rzp_live_xxxxx` |
| `AI_SERVICE_URL` | `https://reel-ai-service.onrender.com` |
| `CLOUDFLARE_API_TOKEN` | Create in CF dashboard → My Profile → API Tokens → "Edit Cloudflare Workers" template |
| `CLOUDFLARE_ACCOUNT_ID` | CF Dashboard → right sidebar |
| `RENDER_DEPLOY_HOOK_GATEWAY` | From Render dashboard → gateway service |
| `RENDER_DEPLOY_HOOK_AI_SERVICE` | From Render dashboard → ai-service |
| `RENDER_DEPLOY_HOOK_CELERY` | From Render dashboard → celery-worker |

---

## Step 5 — Cloudflare Pages (frontend)

### 5a. Connect repo

1. Cloudflare Dashboard → **Pages** → **Create a project** → **Connect to Git**
2. Select your GitHub repo → **Begin setup**
3. Settings:
   - **Framework preset**: Next.js (Static HTML Export)
   - **Build command**: `cd frontend && npm ci && npm run build`
   - **Build output directory**: `frontend/out`
   - **Root directory**: `/` (monorepo root)

### 5b. Set environment variables

In the Pages project → **Settings** → **Environment variables** → **Production**:

| Variable | Value |
|---|---|
| `NEXT_PUBLIC_API_URL` | `https://reel-gateway.onrender.com` |
| `NEXT_PUBLIC_RAZORPAY_KEY` | `rzp_live_xxxxx` |
| `NODE_ENV` | `production` |

### 5c. Custom domain (optional)

Pages → **Custom domains** → add your domain (e.g. `reelai.in`) → Cloudflare auto-provisions SSL.

---

## Step 6 — First deploy & smoke test

```bash
# Push to main — this triggers GitHub Actions automatically
git add .
git commit -m "feat: production deployment config"
git push origin main
```

Watch the Actions tab. Expected timeline:
- Frontend build + CF Pages deploy: ~3 minutes
- Render services deploy: ~5–8 minutes (Docker build)

Smoke test manually:
```bash
# Gateway health
curl https://reel-gateway.onrender.com/health

# AI service health
curl https://reel-ai-service.onrender.com/health

# Templates
curl https://reel-gateway.onrender.com/api/templates | python3 -m json.tool
```

---

## Step 7 — Vast.ai GPU worker (on-demand)

The Celery worker on Render handles analysis and renders on CPU (~60–90s per reel).
For faster GPU renders (~15–20s), spin up a Vast.ai instance only when needed.

### 7a. Build & push the GPU Docker image (one-time)

```bash
export DOCKERHUB_USER=your-dockerhub-username
bash infra/vast-ai/build_and_push.sh
# Pushes: your-dockerhub-username/reel-ai-gpu:latest
```

### 7b. Spin up a GPU worker

```bash
export VAST_API_KEY=your_vastai_api_key
export REDIS_URL=your_render_redis_url          # from Render Redis service
export CELERY_BROKER_URL="${REDIS_URL}/1"
export CELERY_RESULT_BACKEND="${REDIS_URL/\/1//2}"
export DOCKER_IMAGE=your-dockerhub-username/reel-ai-gpu:latest

python infra/vast-ai/spin_up_gpu.py up
```

The GPU worker connects to the same Redis as Render and picks up `render` queue jobs automatically. Render's CPU worker handles `default` (analysis) queue.

### 7c. Monitor & teardown

```bash
python infra/vast-ai/spin_up_gpu.py list   # see running instances
python infra/vast-ai/spin_up_gpu.py down   # destroy when done (stops billing)
```

> **Cost**: RTX 3060 ≈ ₹25/hr. For 30 renders/day × 30s each = ~15 min GPU time = ₹6/day.

---

## Step 8 — Production monitoring

### Render logs
```bash
# Install Render CLI
npm i -g @render-cli/cli
rndr login
rndr logs --service reel-gateway --tail
rndr logs --service reel-celery-worker --tail
```

### Celery monitoring (Flower)
Add this to `render.yaml` worker section to enable Flower dashboard:
```yaml
dockerCommand: celery -A workers.celery_app flower --port=5555
```
Then access `https://reel-celery-worker.onrender.com:5555`

### MongoDB Atlas monitoring
Atlas Dashboard → **Metrics** — watch connections and storage.

---

## Cost summary at launch

| Service | Plan | Cost/mo |
|---|---|---|
| Render Gateway | Starter | $7 |
| Render AI Service | Standard | $25 |
| Render Celery Worker | Standard | $25 |
| Render Redis | Free | $0 |
| MongoDB Atlas | Free M0 | $0 |
| Cloudflare Pages | Free | $0 |
| Cloudflare R2 | Free (10 GB) | $0 |
| Vast.ai GPU | On-demand | ~₹150/mo (est.) |
| **Total** | | **~$57/mo + GPU** |

**Break-even**: 57 × 83 ÷ 20 = **≈ 237 exports/month** (~8/day).

---

## Quick reference — all env vars

```bash
# Gateway (Render)
NODE_ENV=production
PORT=4000
MONGO_URI=mongodb+srv://...
JWT_SECRET=<auto-generated by Render>
RAZORPAY_KEY_ID=rzp_live_...
RAZORPAY_KEY_SECRET=...
RAZORPAY_WEBHOOK_SECRET=...
EXPORT_PRICE_INR=2000
FRONTEND_URL=https://reel-ai.pages.dev
STORAGE_TYPE=r2
CLOUDFLARE_R2_ENDPOINT=https://<account>.r2.cloudflarestorage.com
S3_BUCKET=reel-videos
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...

# AI Service + Celery (Render)
WHISPER_MODEL=base
UPLOADS_DIR=/app/uploads
OUTPUTS_DIR=/app/outputs
STORAGE_TYPE=r2
# (same R2 vars as above)

# Frontend (Cloudflare Pages)
NEXT_PUBLIC_API_URL=https://reel-gateway.onrender.com
NEXT_PUBLIC_RAZORPAY_KEY=rzp_live_...

# Vast.ai GPU (local script)
VAST_API_KEY=...
DOCKER_IMAGE=yourdockerhub/reel-ai-gpu:latest
```
