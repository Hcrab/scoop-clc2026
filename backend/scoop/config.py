"""Runtime settings read from the environment."""

from __future__ import annotations

import os
from .demo_config import DEMO_SEED
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv(
        "DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/scoop"
    )
    llm_provider: str = os.getenv("SCOOP_LLM_PROVIDER", "scripted")
    gemini_model: str = os.getenv("SCOOP_GEMINI_MODEL", "gemini-3.8-flash")
    llm_budget_usd: float = float(os.getenv("SCOOP_LLM_BUDGET_USD", "3"))
    llm_max_calls: int = int(os.getenv("SCOOP_LLM_MAX_CALLS", "120"))
    llm_timeout_seconds: float = float(os.getenv("SCOOP_LLM_TIMEOUT_SECONDS", "75"))
    reports_dir: Path = ROOT / "reports"
    seed: int = int(os.getenv("SCOOP_SEED", str(DEMO_SEED)))


settings = Settings()
