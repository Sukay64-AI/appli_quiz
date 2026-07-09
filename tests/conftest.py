# File: tests/conftest.py
"""Outils de test. FakeClock deterministe, constructeur de quiz standard.

FakeClock est l'adaptateur de test du port Clock. Il rend le scoring a la
vitesse reproductible : on avance le temps a la main, jamais l'horloge reelle.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from quizlive.domain.model import Question, Quiz, Team
from quizlive.domain.scoring import DecliningSpeedScore


class FakeClock:
    """Adaptateur de test du port Clock."""

    def __init__(self, start: datetime | None = None) -> None:
        self._t = start or datetime(2027, 4, 1, 9, 0, 0)

    def now(self) -> datetime:
        return self._t

    def advance(self, seconds: float) -> None:
        self._t = self._t + timedelta(seconds=seconds)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def scoring() -> DecliningSpeedScore:
    return DecliningSpeedScore(base=1000, floor=500)


def make_quiz(clock: FakeClock, scoring: DecliningSpeedScore) -> Quiz:
    """Quiz a 3 questions, 2 equipes. 4 options, temps limite 20 s."""
    questions = [
        Question(id="q0", order=0, n_options=4, correct_option=1, time_limit_s=20.0),
        Question(id="q1", order=1, n_options=4, correct_option=2, time_limit_s=20.0),
        Question(id="q2", order=2, n_options=4, correct_option=0, time_limit_s=20.0),
    ]
    teams = [Team(id="rouge", name="Rouge"), Team(id="bleu", name="Bleu")]
    return Quiz("xtra-game", questions, teams, clock, scoring)


@pytest.fixture
def quiz(clock: FakeClock, scoring: DecliningSpeedScore) -> Quiz:
    return make_quiz(clock, scoring)
