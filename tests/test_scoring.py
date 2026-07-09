# File: tests/test_scoring.py
"""Politique de score par defaut. Juste et rapide vaut plus que juste et lent,
faux vaut zero, et une reponse juste ne descend jamais sous le plancher."""
from __future__ import annotations

import pytest

from quizlive.domain.scoring import DecliningSpeedScore


@pytest.fixture
def policy() -> DecliningSpeedScore:
    return DecliningSpeedScore(base=1000, floor=500)


def test_faux_vaut_zero(policy: DecliningSpeedScore) -> None:
    assert policy.score(correct=False, elapsed_s=0.0, time_limit_s=20.0) == 0


def test_juste_instantane_vaut_base(policy: DecliningSpeedScore) -> None:
    assert policy.score(correct=True, elapsed_s=0.0, time_limit_s=20.0) == 1000


def test_juste_au_buzzer_vaut_floor(policy: DecliningSpeedScore) -> None:
    assert policy.score(correct=True, elapsed_s=20.0, time_limit_s=20.0) == 500


def test_juste_a_mi_temps(policy: DecliningSpeedScore) -> None:
    assert policy.score(correct=True, elapsed_s=10.0, time_limit_s=20.0) == 750


def test_decroissance_monotone(policy: DecliningSpeedScore) -> None:
    scores = [
        policy.score(correct=True, elapsed_s=t, time_limit_s=20.0)
        for t in (0.0, 5.0, 10.0, 15.0, 20.0)
    ]
    assert scores == sorted(scores, reverse=True)
    assert all(500 <= s <= 1000 for s in scores)


def test_au_dela_de_la_limite_reste_au_floor(policy: DecliningSpeedScore) -> None:
    # depassement gere ailleurs par LateVote, mais la politique reste bornee
    assert policy.score(correct=True, elapsed_s=999.0, time_limit_s=20.0) == 500


def test_base_inferieure_a_floor_interdit() -> None:
    with pytest.raises(ValueError):
        DecliningSpeedScore(base=100, floor=500)
