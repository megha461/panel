"""Reasoner selection. Demo mode is a fallback, not a failure."""

from __future__ import annotations

from panel.config import Settings, load_settings
from panel.llm.base import AnswerAssessment, CoachingNote, Reasoner, ScoreVerdict
from panel.llm.heuristic import HeuristicReasoner

__all__ = [
    "AnswerAssessment",
    "CoachingNote",
    "Reasoner",
    "ScoreVerdict",
    "HeuristicReasoner",
    "get_reasoner",
]


def get_reasoner(settings: Settings | None = None) -> Reasoner:
    settings = settings or load_settings()
    if settings.demo_mode:
        return HeuristicReasoner()
    from panel.llm.anthropic import AnthropicReasoner

    return AnthropicReasoner(settings)
