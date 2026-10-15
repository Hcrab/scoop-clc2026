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


# Presentation-only intraday profile. The physical simulation still settles daily.
# Spread 10% uniformly from midnight to dispatch close, so overnight Play shows
# requests and cumulative dispatch never runs ahead of requests. Daily demand is unchanged.
INTRADAY_STEP_MINUTES = 10
DAYTIME_REQUEST_WEIGHTS = (0.0,) * 10 + (
    .04, .06, .08, .10, .14, .16, .14, .10, .07, .05, .04, .02,
) + (0.0,) * 2
DEMAND_HOURLY_WEIGHTS = tuple(.9 * weight + (.1 / 22 if hour < 22 else 0)
                              for hour, weight in enumerate(DAYTIME_REQUEST_WEIGHTS))
DISPATCH_HOURLY_WEIGHTS = (0.0,) * 18 + (.15, .30, .35, .20) + (0.0,) * 2
ORDER_CUTOFF_MINUTE = 14 * 60
SUPPLIER_WINDOWS = {
    'SUP01': (360, 480), 'SUP02': (390, 540), 'SUP03': (420, 540),
    'SUP04': (360, 600), 'SUP05': (420, 600), 'SUP06': (360, 540),
    'SUP07': (360, 600), 'SUP08': (420, 600),
}
DEFAULT_SUPPLIER_WINDOW = (360, 600)
