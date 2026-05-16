#!/usr/bin/env python3
"""
Vast.ai GPU worker manager.

Usage:
  # Spin up a GPU worker (connects to your Render Redis automatically)
  python spin_up_gpu.py up

  # List running GPU workers
  python spin_up_gpu.py list

  # Destroy all reel-ai GPU workers
  python spin_up_gpu.py down

Requires:
  pip install vastai requests
  export VAST_API_KEY=your_vastai_api_key
  export REDIS_URL=redis://your-render-redis-url:6379/1
  export DOCKER_IMAGE=your-dockerhub-user/reel-ai-gpu:latest  (optional)
"""

import os
import sys
import json
import time
import subprocess
import requests

API_KEY = os.environ["VAST_API_KEY"]
REDIS_URL = os.environ["REDIS_URL"]
CELERY_BROKER = os.environ.get("CELERY_BROKER_URL", REDIS_URL)
CELERY_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", REDIS_URL.replace("/1", "/2"))
DOCKER_IMAGE = os.environ.get("DOCKER_IMAGE", "nithyanandam/reel-ai-gpu:latest")

BASE = "https://console.vast.ai/api/v0"
HEADERS = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}

LABEL = "reel-ai-gpu-worker"

# GPU requirements — cheapest RTX 3060/3080 that fits
SEARCH_QUERY = {
    "verified": {"eq": True},
    "external": {"eq": False},  # data-centre grade
    "rentable": {"eq": True},
    "num_gpus": {"gte": 1},
    "gpu_ram": {"gte": 8},      # 8 GB VRAM minimum for CLIP + Whisper
    "cpu_ram": {"gte": 16},
    "disk_space": {"gte": 30},
    "cuda_max_good": {"gte": 12.1},
    "order": [["dph_total", "asc"]],  # cheapest first
    "type": "on-demand",
    "limit": 5,
}


def find_cheapest():
    r = requests.post(f"{BASE}/bundles", headers=HEADERS, json=SEARCH_QUERY)
    r.raise_for_status()
    offers = r.json().get("offers", [])
    if not offers:
        raise RuntimeError("No suitable GPU instances found on Vast.ai right now. Try again later.")
    best = offers[0]
    print(f"  Best offer: {best['gpu_name']} × {best['num_gpus']} — "
          f"${best['dph_total']:.3f}/hr — ID {best['id']}")
    return best


def launch(offer: dict) -> dict:
    env = {
        "REDIS_URL": REDIS_URL,
        "CELERY_BROKER_URL": CELERY_BROKER,
        "CELERY_RESULT_BACKEND": CELERY_BACKEND,
        "UPLOADS_DIR": "/app/uploads",
        "OUTPUTS_DIR": "/app/outputs",
        "WHISPER_MODEL": "base",
    }
    payload = {
        "client_id": "me",
        "image": DOCKER_IMAGE,
        "env": env,
        "disk": 30,
        "onstart": "",
        "runtype": "args",
        "image_login": None,
        "label": LABEL,
        "extra": "",
        "use_jupyter_lab": False,
        "jupyter_dir": None,
        "create_from": None,
        "force": False,
    }
    r = requests.put(f"{BASE}/asks/{offer['id']}/", headers=HEADERS, json=payload)
    r.raise_for_status()
    instance = r.json()
    print(f"  ✅ Instance created: ID {instance.get('new_contract')}")
    return instance


def list_instances():
    r = requests.get(f"{BASE}/instances", headers=HEADERS, params={"owner": "me"})
    r.raise_for_status()
    instances = [i for i in r.json().get("instances", []) if i.get("label") == LABEL]
    return instances


def destroy(instance_id: int):
    r = requests.delete(f"{BASE}/instances/{instance_id}/", headers=HEADERS)
    r.raise_for_status()
    print(f"  🗑  Destroyed instance {instance_id}")


def cmd_up():
    print("🔍 Finding cheapest GPU on Vast.ai...")
    offer = find_cheapest()
    print("🚀 Launching GPU worker...")
    launch(offer)
    print("\nWorker will appear in Redis queue within ~3 minutes (Docker pull + model load).")
    print("Monitor: https://cloud.vast.ai/instances/")


def cmd_list():
    instances = list_instances()
    if not instances:
        print("No reel-ai GPU workers running.")
        return
    print(f"{len(instances)} GPU worker(s) running:")
    for i in instances:
        print(f"  ID {i['id']} — {i.get('gpu_name','?')} — "
              f"status={i.get('actual_status','?')} — "
              f"${i.get('dph_total',0):.3f}/hr")


def cmd_down():
    instances = list_instances()
    if not instances:
        print("No reel-ai GPU workers to destroy.")
        return
    print(f"Destroying {len(instances)} instance(s)...")
    for i in instances:
        destroy(i["id"])
    print("✅ All GPU workers terminated.")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "list"
    {"up": cmd_up, "list": cmd_list, "down": cmd_down}.get(cmd, cmd_list)()
