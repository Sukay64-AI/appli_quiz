# File: tests/test_leaderboard.py
"""Classement inter-equipe. Le score d'equipe est la MOYENNE des totaux de ses
membres, pas la somme, pour ne pas favoriser la grosse equipe."""
from __future__ import annotations

from quizlive.domain.model import Quiz
from tests.conftest import FakeClock


def test_moyenne_par_membre_pas_somme(quiz: Quiz, clock: FakeClock) -> None:
    # Rouge : 2 membres. Bleu : 1 membre. Tailles heterogenes voulues.
    quiz.join("r1", "rouge", "R1", "t1")
    quiz.join("r2", "rouge", "R2", "t2")
    quiz.join("b1", "bleu", "B1", "t3")

    quiz.open_next()  # q0, correct == 1
    # Rouge : un juste instantane (1000), un faux (0). Moyenne 500.
    quiz.submit_answer("r1", 1)  # 1000
    quiz.submit_answer("r2", 3)  # 0
    # Bleu : un juste instantane (1000). Moyenne 1000.
    quiz.submit_answer("b1", 1)  # 1000
    quiz.close_question()

    board = quiz.leaderboard()
    scores = {ts.team_id: ts.avg_score for ts in board}

    assert scores["rouge"] == 500.0  # (1000 + 0) / 2, la somme aurait donne 1000
    assert scores["bleu"] == 1000.0
    # Bleu devant malgre moins de membres et moins de points cumules.
    assert board[0].team_id == "bleu"


def test_equipe_sans_membre_vaut_zero(quiz: Quiz) -> None:
    quiz.join("r1", "rouge", "R1", "t1")
    quiz.open_next()
    quiz.submit_answer("r1", 1)
    quiz.close_question()

    scores = {ts.team_id: ts.avg_score for ts in quiz.leaderboard()}
    assert scores["bleu"] == 0.0
    assert {ts.team_id for ts in quiz.leaderboard()} == {"rouge", "bleu"}


def test_membre_present_mais_sans_reponse_compte_comme_zero(quiz: Quiz) -> None:
    quiz.join("r1", "rouge", "R1", "t1")
    quiz.join("r2", "rouge", "R2", "t2")  # inscrit, ne vote jamais
    quiz.open_next()
    quiz.submit_answer("r1", 1)  # 1000
    quiz.close_question()

    scores = {ts.team_id: ts.avg_score for ts in quiz.leaderboard()}
    assert scores["rouge"] == 500.0  # (1000 + 0) / 2 membres inscrits


def test_totaux_cumules_sur_plusieurs_questions(quiz: Quiz) -> None:
    quiz.join("r1", "rouge", "R1", "t1")
    quiz.open_next()  # q0 correct 1
    quiz.submit_answer("r1", 1)  # 1000
    quiz.close_question()
    quiz.open_next()  # q1 correct 2
    quiz.submit_answer("r1", 2)  # 1000
    quiz.close_question()

    scores = {ts.team_id: ts.avg_score for ts in quiz.leaderboard()}
    assert scores["rouge"] == 2000.0  # cumul sur 2 questions, 1 membre
