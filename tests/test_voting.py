# File: tests/test_voting.py
"""Regles de vote : un vote par personne par question, options valides,
participant connu, rejet des retardataires et des votes hors fenetre."""
from __future__ import annotations

import pytest

from quizlive.domain.errors import (
    AlreadyAnswered,
    InvalidOption,
    LateVote,
    UnknownParticipant,
    VotingClosed,
)
from quizlive.domain.model import Quiz
from tests.conftest import FakeClock


def _join_and_open(quiz: Quiz) -> None:
    quiz.join("p1", "rouge", "Alice", "tok-1")
    quiz.open_next()


def test_vote_valide_enregistre(quiz: Quiz) -> None:
    _join_and_open(quiz)
    answer = quiz.submit_answer("p1", 1)  # q0 correct_option == 1
    assert answer.correct is True
    assert answer.score > 0


def test_vote_faux_score_nul(quiz: Quiz) -> None:
    _join_and_open(quiz)
    answer = quiz.submit_answer("p1", 3)
    assert answer.correct is False
    assert answer.score == 0


def test_double_vote_rejete(quiz: Quiz) -> None:
    _join_and_open(quiz)
    quiz.submit_answer("p1", 1)
    with pytest.raises(AlreadyAnswered):
        quiz.submit_answer("p1", 2)


def test_option_hors_intervalle(quiz: Quiz) -> None:
    _join_and_open(quiz)
    with pytest.raises(InvalidOption):
        quiz.submit_answer("p1", 4)  # options 0..3
    with pytest.raises(InvalidOption):
        quiz.submit_answer("p1", -1)


def test_participant_inconnu(quiz: Quiz) -> None:
    quiz.open_next()
    with pytest.raises(UnknownParticipant):
        quiz.submit_answer("fantome", 1)


def test_vote_avant_ouverture_rejete(quiz: Quiz) -> None:
    quiz.join("p1", "rouge", "Alice", "tok-1")
    with pytest.raises(VotingClosed):
        quiz.submit_answer("p1", 1)


def test_vote_apres_fermeture_rejete(quiz: Quiz) -> None:
    _join_and_open(quiz)
    quiz.close_question()
    with pytest.raises(VotingClosed):
        quiz.submit_answer("p1", 1)


def test_vote_en_retard_rejete(quiz: Quiz, clock: FakeClock) -> None:
    _join_and_open(quiz)
    clock.advance(20.5)  # temps limite 20 s
    with pytest.raises(LateVote):
        quiz.submit_answer("p1", 1)


def test_vote_au_ras_de_la_limite_accepte(quiz: Quiz, clock: FakeClock) -> None:
    _join_and_open(quiz)
    clock.advance(20.0)  # exactement la limite, pas au-dela
    answer = quiz.submit_answer("p1", 1)
    assert answer.correct is True
