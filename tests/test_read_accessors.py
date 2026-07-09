# File: tests/test_read_accessors.py
"""Accesseurs de lecture ajoutes pour la couche application."""
from __future__ import annotations

from quizlive.domain.model import Quiz
from tests.conftest import FakeClock


def test_index_et_opened_at(quiz: Quiz, clock: FakeClock) -> None:
    assert quiz.current_index is None
    assert quiz.opened_at is None
    quiz.open_next()
    assert quiz.current_index == 0
    assert quiz.opened_at == clock.now()


def test_participants_et_par_equipe(quiz: Quiz) -> None:
    assert quiz.participants_count() == 0
    quiz.join("r1", "rouge", "R1", "t1")
    quiz.join("r2", "rouge", "R2", "t2")
    quiz.join("b1", "bleu", "B1", "t3")
    assert quiz.participants_count() == 3
    assert quiz.participants_by_team() == {"rouge": 2, "bleu": 1}


def test_votes_count_et_answer_of(quiz: Quiz) -> None:
    quiz.join("r1", "rouge", "R1", "t1")
    quiz.join("b1", "bleu", "B1", "t2")
    quiz.open_next()
    assert quiz.votes_count("q0") == 0
    quiz.submit_answer("r1", 1)
    assert quiz.votes_count("q0") == 1
    answer = quiz.answer_of("r1", "q0")
    assert answer is not None and answer.correct is True
    assert quiz.answer_of("b1", "q0") is None


def test_participant_total_cumule(quiz: Quiz) -> None:
    quiz.join("r1", "rouge", "R1", "t1")
    quiz.open_next()
    quiz.submit_answer("r1", 1)  # 1000
    quiz.close_question()
    quiz.open_next()
    quiz.submit_answer("r1", 0)  # faux, 0
    quiz.close_question()
    assert quiz.participant_total("r1") == 1000
    assert quiz.participant_total("inconnu") == 0


def test_get_participant(quiz: Quiz) -> None:
    quiz.join("r1", "rouge", "Alice", "t1")
    p = quiz.get_participant("r1")
    assert p is not None and p.nickname == "Alice" and p.team_id == "rouge"
    assert quiz.get_participant("x") is None
