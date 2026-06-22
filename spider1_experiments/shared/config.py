"""Project configuration."""

from __future__ import annotations

import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = Path(__file__).resolve().parents[1]
ROOT_ENV_PATH = PROJECT_ROOT / ".env"
LOCAL_ENV_PATH = PACKAGE_ROOT / ".env"


def load_env_file(path: Path) -> None:
    """Load simple KEY=VALUE pairs from .env without overriding real env vars."""
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


load_env_file(ROOT_ENV_PATH)
load_env_file(LOCAL_ENV_PATH)

DATA_DIR = PROJECT_ROOT / "data"
PROCESSED_DATA_DIR = DATA_DIR / "processed"
DATABASE_DIR = DATA_DIR / "databases"
RESULTS_DIR = PROJECT_ROOT / "results" / "spider1"
LOGS_DIR = PROJECT_ROOT / "logs" / "spider1"
PROMPTS_DIR = PACKAGE_ROOT / "prompts"

DEFAULT_DATASET_PATH = PROCESSED_DATA_DIR / "dev_questions.json"

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini")
MODEL = os.getenv("MODEL", "gemini-2.0-flash")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://localhost:8000/v1").rstrip("/")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
TEMPERATURE = float(os.getenv("TEMPERATURE", "0"))
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "1024"))
N_ATTEMPTS = 1

