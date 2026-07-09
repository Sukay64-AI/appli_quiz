# File: tests/test_state_machine.py
"""La machine a etats est la seule autorite. On verifie les transitions
valides et surtout le rejet des transitions interdites."""
from __future__ import annotations

import pytest

from quizlive.domain.errors import InvalidTransition, NoMoreQuestions
from quizlive.domain.events import QuestionClosed, QuestionOpened, QuizFinished
from quizlive.domain.model import Phase, Quiz


def test_cycle_nominal(quiz: Quiz) -> None:
    assert quiz.phase is Phase.LOBBY

    quiz.open_next()
    assert quiz.phase is Phase.QUESTION_OPEN
    assert quiz.current_question().id == "q0"

    quiz.close_question()
    assert quiz.phase is Phase.QUESTION_CLOSED

    quiz.open_next()
    assert quiz.current_question().id == "q1"

    quiz.close_question()
    quiz.finish()
    assert quiz.phase is Phase.FINISHED


def test_open_next_emet_question_opened(quiz: Quiz) -> None:
    quiz.open_next()
    events = quiz.collect_events()
    assert any(isinstance(e, QuestionOpened) and e.order == 0 for e in events)


def test_close_emet_question_closed(quiz: Quiz) -> None:
    quiz.open_next()
    quiz.collect_events()
    quiz.close_question()
    assert any(isinstance(e, QuestionClosed) for e in quiz.collect_events())


def test_finish_emet_quiz_finished(quiz: Quiz) -> None:
    quiz.open_next()
    quiz.close_question()
    quiz.collect_events()
    quiz.finish()
    assert any(isinstance(e, QuizFinished) for e in quiz.collect_events())


def test_open_next_interdit_si_deja_ouvert(quiz: Quiz) -> None:
    quiz.open_next()
    with pytest.raises(InvalidTransition):
        quiz.open_next()


def test_close_interdit_hors_open(quiz: Quiz) -> None:
    with pytest.raises(InvalidTransition):
        quiz.close_question()


def test_finish_interdit_hors_closed(quiz: Quiz) -> None:
    with pytest.raises(InvalidTransition):
        quiz.finish()
    quiz.open_next()
    with pytest.raises(InvalidTransition):
        quiz.finish()


def test_open_next_au_dela_de_la_derniere_leve_no_more(quiz: Quiz) -> None:
    for _ in range(3):
        quiz.open_next()
        quiz.close_question()
    with pytest.raises(NoMoreQuestions):
        quiz.open_next()


def test_collect_events_vide_la_file(quiz: Quiz) -> None:
    quiz.open_next()
    assert quiz.collect_events()  # non vide
    assert quiz.collect_events() == []  # drainee
