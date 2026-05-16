.PHONY: dev prod build stop logs clean seed

# ── Development ──────────────────────────────────────────────────────
dev:
	@echo "🚀 Starting dev stack..."
	cp -n .env.example .env || true
	docker compose up --build

dev-bg:
	docker compose up -d --build

# ── Production ───────────────────────────────────────────────────────
prod:
	docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

# ── Individual services ───────────────────────────────────────────────
gateway:
	cd backend/gateway && npm run dev

ai:
	cd backend/ai-service && uvicorn main:app --reload --port 8000

worker:
	cd backend/ai-service && celery -A workers.celery_app worker --loglevel=info

frontend:
	cd frontend && npm run dev

# ── Ops ───────────────────────────────────────────────────────────────
stop:
	docker compose down

logs:
	docker compose logs -f

logs-ai:
	docker compose logs -f ai-service celery-worker

clean:
	docker compose down -v --remove-orphans
	docker system prune -f

# ── Setup ─────────────────────────────────────────────────────────────
install:
	cd backend/gateway && npm install
	cd frontend && npm install
	cd backend/ai-service && pip install -r requirements.txt --break-system-packages

models:
	@echo "📥 Downloading AI models (first run only)..."
	cd backend/ai-service && python scripts/download_models.py

# ── Lint / Format ─────────────────────────────────────────────────────
lint:
	cd frontend && npm run lint
	cd backend/gateway && npm run lint
	cd backend/ai-service && ruff check .

format:
	cd backend/ai-service && black . && ruff check --fix .

# ── DB ────────────────────────────────────────────────────────────────
mongo-shell:
	docker exec -it reel_mongo mongosh -u reel -p reelpass reeldb
