#!/usr/bin/env bash
# Build the GPU Docker image and push to Docker Hub.
# Run this once, then use the image tag in spin_up_gpu.py.
#
# Usage:
#   export DOCKERHUB_USER=yourname
#   bash build_and_push.sh

set -e

DOCKERHUB_USER="${DOCKERHUB_USER:?Set DOCKERHUB_USER}"
IMAGE="${DOCKERHUB_USER}/reel-ai-gpu:latest"
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

echo "📦 Building GPU image: $IMAGE"
docker build \
  -f "$REPO_ROOT/infra/vast-ai/Dockerfile.gpu" \
  --build-arg WHISPER_MODEL=base \
  -t "$IMAGE" \
  "$REPO_ROOT"

echo "🚀 Pushing to Docker Hub..."
docker push "$IMAGE"

echo "✅ Done: $IMAGE"
echo ""
echo "Next step — launch a Vast.ai GPU worker:"
echo "  export VAST_API_KEY=your_key"
echo "  export REDIS_URL=your_render_redis_url"
echo "  export DOCKER_IMAGE=$IMAGE"
echo "  python infra/vast-ai/spin_up_gpu.py up"
