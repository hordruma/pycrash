"""Platform configuration."""
from __future__ import annotations

import os
from pydantic import BaseModel


class Settings(BaseModel):
    """Application settings loaded from environment."""
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    reports_dir: str = os.getenv("REPORTS_DIR", "/app/reports")
    env: str = os.getenv("PYCRASH_ENV", "development")

    # Simulation defaults
    default_dt_motion: float = 0.01
    default_mu_max: float = 0.8
    default_alpha_max: float = 0.174533

    # Monte Carlo defaults
    default_mc_runs: int = 1000
    max_mc_runs: int = 50000

    # API key authentication (empty = no auth required)
    api_key: str = os.getenv("PYCRASH_API_KEY", "")

    # Claude model
    claude_model: str = "claude-sonnet-4-20250514"


settings = Settings()
