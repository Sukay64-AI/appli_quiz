# File: tests/test_stats.py
"""Trois besoins de stats : global par question, par equipe par question, et
la combinaison des deux."""
from __future__ import annotations

from quizlive.domain.model import Quiz


def _setup_votes(quiz: Quiz) -> None:
    quiz.join("r1", "rouge", "R1", "t1")
    quiz.join("r2", "rouge", "R2", "t2")
    quiz.join("b1", "bleu", "B1", "t3")
    quiz.open_next()  # q0, 4 options, correct == 1
    quiz.submit_answer("r1", 1)  # juste
    quiz.submit_answer("r2", 3)  # faux
    quiz.submit_answer("b1", 1)  # juste
    quiz.close_question()


def test_stats_global_distribution(quiz: Quiz) -> None:
    _setup_votes(quiz)
    stats = quiz.stats_global("q0")
    assert stats.total == 3
    assert stats.correct == 2
    assert stats.counts[1] == 2  # deux ont choisi l'option 1
    assert stats.counts[3] == 1
    assert stats.counts[0] == 0
    assert stats.counts[2] == 0


def test_stats_par_equipe(quiz: Quiz) -> None:
    _setup_votes(quiz)
    by_team = quiz.stats_by_team("q0")

    assert set(by_team) == {"rouge", "bleu"}

    rouge = by_team["rouge"]
    assert rouge.total == 2
    assert rouge.correct == 1
    assert rouge.counts[1] == 1
    assert rouge.counts[3] == 1

    bleu = by_team["bleu"]
    assert bleu.total == 1
    assert bleu.correct == 1
    assert bleu.counts[1] == 1


def test_global_est_la_somme_des_equipes(quiz: Quiz) -> None:
    """La combinaison : le global doit egaler la somme des ventilations."""
    _setup_votes(quiz)
    glob = quiz.stats_global("q0")
    by_team = quiz.stats_by_team("q0")

    assert glob.total == sum(s.total for s in by_team.values())
    assert glob.correct == sum(s.correct for s in by_team.values())
    for option in range(4):
        assert glob.counts[option] == sum(s.counts[option] for s in by_team.values())


def test_stats_question_sans_vote(quiz: Quiz) -> None:
    quiz.join("r1", "rouge", "R1", "t1")
    quiz.open_next()
    quiz.close_question()
    stats = quiz.stats_global("q0")
    assert stats.total == 0
    assert stats.correct == 0
    assert all(c == 0 for c in stats.counts.values())
