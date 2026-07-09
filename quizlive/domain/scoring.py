# File: quizlive/domain/scoring.py
"""Politique de score. Port + une implementation par defaut.

Le score d'une question depend de la justesse ET de la vitesse, comme Kahoot.
La regle est isolee derriere un Protocol pour etre remplacable sans toucher a
l'agregat. Logique pure, aucune I/O, donc elle vit dans le domaine.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@runtime_checkable
class ScoringPolicy(Protocol):
    """Calcule les points d'une reponse."""

    def score(self, *, correct: bool, elapsed_s: float, time_limit_s: float) -> int: ...


@dataclass(frozen=True)
class DecliningSpeedScore:
    """Score decroissant avec le temps.

    Faux -> 0. Juste -> entre base (reponse instantanee) et floor (au buzzer).
    Decroissance lineaire de la fraction de temps ecoulee. Une reponse juste
    ne descend jamais sous floor, pour que la vitesse departage sans ecraser.
    """

    base: int = 1000
    floor: int = 500

    def __post_init__(self) -> None:
        if self.base < self.floor:
            raise ValueError("base doit etre >= floor")
        if self.floor < 0:
            raise ValueError("floor doit etre >= 0")

    def score(self, *, correct: bool, elapsed_s: float, time_limit_s: float) -> int:
        if not correct:
            return 0
        if time_limit_s <= 0:
            raise ValueError("time_limit_s doit etre > 0")
        frac = min(1.0, max(0.0, elapsed_s / time_limit_s))
        return round(self.floor + (self.base - self.floor) * (1.0 - frac))
