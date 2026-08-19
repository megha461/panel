"""Runtime settings. Demo mode is the default when no key is present."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"


@dataclass(frozen=True)
class Settings:
    api_key: str | None
    model: str
    max_tokens: int
    db_path: Path

    @property
    def demo_mode(self) -> bool:
        """No key means the heuristic reasoner runs. Everything still works."""
        return not self.api_key


def load_settings() -> Settings:
    return Settings(
        api_key=os.environ.get("ANTHROPIC_API_KEY") or None,
        model=os.environ.get("PANEL_MODEL", "claude-opus-5"),
        # Thinking is on by default on Opus 5 and max_tokens caps thinking *plus*
        # output, so this needs real headroom — a tight budget truncates the answer.
        max_tokens=int(os.environ.get("PANEL_MAX_TOKENS", "8000")),
        db_path=Path(os.environ.get("PANEL_DB", DATA_DIR / "panel.db")),
    )
