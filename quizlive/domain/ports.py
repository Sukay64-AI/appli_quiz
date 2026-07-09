# File: quizlive/domain/ports.py
"""Ports. Contrats que les couches externes implementent.

Regle hexagonale : le domaine definit l'interface, l'infrastructure fournit
le concret. Le domaine ne depend jamais d'une techno.

- Clock : injecte dans l'agregat pour un horodatage SERVEUR, testable. Jamais
  d'horloge client, sinon le scoring a la vitesse est faussable.
- EventPublisher et QuizRepository : consommes par la couche application et
  l'infrastructure, pas par l'agregat. Definis ici pour que le contrat vive
  avec le domaine.
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from quizlive.domain.events import DomainEvent
    from quizlive.domain.model import Quiz


@runtime_checkable
class Clock(Protocol):
    """Source unique du temps serveur."""

    def now(self) -> datetime: ...


@runtime_checkable
class EventPublisher(Protocol):
    """Diffuse un evenement de domaine vers les abonnes, ex. WebSocket."""

    def publish(self, event: "DomainEvent") -> None: ...


@runtime_checkable
class QuizRepository(Protocol):
    """Persistance de l'agregat. Reprise apres crash."""

    def load(self, quiz_id: str) -> "Quiz": ...

    def save(self, quiz: "Quiz") -> None: ...
