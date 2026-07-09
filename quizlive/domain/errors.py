# File: quizlive/domain/errors.py
"""Erreurs du domaine. Aucune dependance externe.

Toutes heritent de DomainError, pour que la couche application puisse les
attraper d'un bloc et les traduire en reponses HTTP ou en messages WebSocket
sans connaitre le detail.
"""
from __future__ import annotations


class DomainError(Exception):
    """Racine de toutes les erreurs metier."""


class InvalidTransition(DomainError):
    """Transition de la machine a etats interdite depuis la phase courante."""


class VotingClosed(DomainError):
    """Vote soumis alors que la question n'est pas ouverte."""


class LateVote(DomainError):
    """Vote arrive apres le temps limite de la question."""


class AlreadyAnswered(DomainError):
    """Un participant a deja repondu a cette question. Un vote par question."""


class UnknownParticipant(DomainError):
    """Participant inconnu, jamais inscrit."""


class UnknownTeam(DomainError):
    """Equipe inconnue. Les equipes sont predefinies a la construction."""


class UnknownQuestion(DomainError):
    """Question inconnue."""


class InvalidOption(DomainError):
    """Option hors de l'intervalle [0, n_options)."""


class NoMoreQuestions(DomainError):
    """Plus aucune question a ouvrir."""


class DuplicateParticipant(DomainError):
    """Identifiant de participant deja utilise."""
