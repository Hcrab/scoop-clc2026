"""Runtime settings read from the environment."""

from __future__ import annotations

import os
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
    reports_dir: Path = ROOT / "reports"
    seed: int = int(os.getenv("SCOOP_SEED", "42"))


settings = Settings()
