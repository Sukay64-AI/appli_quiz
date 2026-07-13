# File: quizlive/domain/events.py
"""Evenements du domaine. Structures passives, immuables, sans logique.

L'agregat les accumule quand son etat change. Une couche externe les draine
via Quiz.collect_events() et les pousse vers les telephones par WebSocket.
Le domaine ne connait pas le transport.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class DomainEvent:
    """Base commune. Permet un typage unique cote publisher."""


@dataclass(frozen=True)
class ParticipantJoined(DomainEvent):
    participant_id: str
    team_id: str


@dataclass(frozen=True)
class QuestionOpened(DomainEvent):
    question_id: str
    order: int
    opened_at: datetime
    time_limit_s: float


@dataclass(frozen=True)
class AnswerAccepted(DomainEvent):
    question_id: str
    participant_id: str
    correct: bool
    score: int


@dataclass(frozen=True)
class QuestionClosed(DomainEvent):
    question_id: str
    order: int


@dataclass(frozen=True)
class QuizFinished(DomainEvent):
    pass


@dataclass(frozen=True)
class QuizReset(DomainEvent):
    pass
