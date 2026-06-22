"""Configuration for Spider2-Snow experiments."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = Path(__file__).resolve().parent
ROOT_ENV_PATH = PROJECT_ROOT / ".env"
LOCAL_ENV_PATH = PACKAGE_ROOT / ".env"

OFFICIAL_SPIDER2_ROOT = PROJECT_ROOT / "Spider2"
SPIDER2_SNOW_DIR = OFFICIAL_SPIDER2_ROOT / "spider2-snow"
SPIDER2_SNOW_DATASET = SPIDER2_SNOW_DIR / "spider2-snow.jsonl"
SPIDER2_SNOW_DATABASES = SPIDER2_SNOW_DIR / "resource" / "databases"
SPIDER2_SNOW_DOCUMENTS = SPIDER2_SNOW_DIR / "resource" / "documents"

DEFAULT_CREDENTIAL_PATH = (
    OFFICIAL_SPIDER2_ROOT
    / "methods"
    / "spider-agent-snow"
    / "snowflake_credential.json"
)

RESULTS_DIR = PROJECT_ROOT / "results" / "spider2_snow"
SUBMISSIONS_DIR = PROJECT_ROOT / "results" / "spider2_snow_submissions"
PROMPTS_DIR = PACKAGE_ROOT / "prompts"


def load_env_file(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


load_env_file(ROOT_ENV_PATH)
load_env_file(LOCAL_ENV_PATH)


@dataclass(frozen=True)
class Settings:
    dataset_path: Path = Path(os.getenv("SPIDER2_SNOW_DATASET", SPIDER2_SNOW_DATASET))
    databases_dir: Path = Path(os.getenv("SPIDER2_SNOW_DATABASES", SPIDER2_SNOW_DATABASES))
    documents_dir: Path = Path(os.getenv("SPIDER2_SNOW_DOCUMENTS", SPIDER2_SNOW_DOCUMENTS))
    credential_path: Path = Path(
        os.getenv("SPIDER2_SNOW_CREDENTIAL_PATH", DEFAULT_CREDENTIAL_PATH)
    )
    results_dir: Path = Path(os.getenv("SPIDER2_SNOW_RESULTS_DIR", RESULTS_DIR))
    submissions_dir: Path = Path(
        os.getenv("SPIDER2_SNOW_SUBMISSIONS_DIR", SUBMISSIONS_DIR)
    )

    llm_provider: str = os.getenv("LLM_PROVIDER", "openai_compatible")
    model: str = os.getenv("MODEL", "qwen2.5-coder:7b")
    llm_base_url: str = os.getenv("LLM_BASE_URL", "http://localhost:11434/v1").rstrip("/")
    llm_api_key: str = os.getenv("LLM_API_KEY", "ollama")
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    temperature: float = float(os.getenv("TEMPERATURE", "0"))
    max_tokens: int = int(os.getenv("MAX_TOKENS", "2048"))

    schema_max_chars: int = int(os.getenv("SPIDER2_SCHEMA_MAX_CHARS", "60000"))
    document_max_chars: int = int(os.getenv("SPIDER2_DOCUMENT_MAX_CHARS", "20000"))


def get_settings() -> Settings:
    return Settings()
