# File: tests/test_binary_scoring.py
"""Score binaire et classement en pourcentage de reussite par membre."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from quizlive.application.service import QuizService
from quizlive.domain.model import Quiz
from quizlive.domain.scoring import BinaryScore
from quizlive.infra.config_loader import load_config
from quizlive.infra.hub import Hub
from quizlive.web.app import create_app
from tests.conftest import FakeClock

HOST_KEY = "k"


def test_binary_score_valeurs() -> None:
    b = BinaryScore()
    assert b.score(correct=True, elapsed_s=0.0, time_limit_s=30.0) == 1
    assert b.score(correct=True, elapsed_s=29.9, time_limit_s=30.0) == 1  # vitesse ignoree
    assert b.score(correct=False, elapsed_s=0.0, time_limit_s=30.0) == 0


@pytest.fixture
def client(tmp_path) -> TestClient:
    cfg = {
        "quiz_id": "t",
        "teams": [{"id": "rotor", "name": "Rotor"}, {"id": "stator", "name": "Stator"}],
        "questions": [
            {"id": "q0", "order": 0, "labels": ["A", "B", "Les deux", "Aucun"],
             "correct_option": 3, "time_limit_s": 30},
            {"id": "q1", "order": 1, "labels": ["A", "B"], "correct_option": 0,
             "time_limit_s": 30},
        ],
    }
    path = tmp_path / "c.json"
    path.write_text(json.dumps(cfg), encoding="utf-8")
    config = load_config(path)
    clock = FakeClock()
    quiz = Quiz(config.quiz_id, config.questions, config.teams, clock, BinaryScore())
    return TestClient(create_app(QuizService(quiz, clock, Hub(), config.labels),
                                 Hub(), secret_key="s", host_key=HOST_KEY))


def _join(c, team):
    r = c.post("/api/join", json={"team_id": team})
    assert r.status_code == 200
    return c


def test_pourcentage_sur_questions_jouees(client) -> None:
    a = _join(client, "rotor")
    b = _join(TestClient(client.app), "rotor")

    # Q0 : a correct, b faux -> Rotor 50% (1 bonne sur 2 membres, 1 question)
    client.post(f"/api/host/open?key={HOST_KEY}")
    a.post("/api/vote", json={"option": 3})
    b.post("/api/vote", json={"option": 0})
    client.post(f"/api/host/close?key={HOST_KEY}")
    lb = {t["name"]: t for t in client.get("/api/present-state").json()["leaderboard"]}
    assert lb["Rotor"]["pct"] == 50.0

    # Q1 : a correct encore -> Rotor : a=2/2, b=0/2, moyenne (100+0)/2 = 50%
    client.post(f"/api/host/open?key={HOST_KEY}")
    a.post("/api/vote", json={"option": 0})
    client.post(f"/api/host/close?key={HOST_KEY}")
    lb = {t["name"]: t for t in client.get("/api/present-state").json()["leaderboard"]}
    assert lb["Rotor"]["pct"] == 50.0


def test_distribution_par_equipe_par_option(client) -> None:
    a = _join(client, "rotor")
    b = _join(TestClient(client.app), "rotor")
    c = _join(TestClient(client.app), "stator")

    client.post(f"/api/host/open?key={HOST_KEY}")
    a.post("/api/vote", json={"option": 3})  # bon
    b.post("/api/vote", json={"option": 0})  # A
    c.post("/api/vote", json={"option": 3})  # bon
    client.post(f"/api/host/close?key={HOST_KEY}")

    d = client.get("/api/present-state").json()["distribution"]
    assert d["labels"] == ["A", "B", "Les deux", "Aucun"]
    assert d["correct_index"] == 3
    rotor = next(t for t in d["teams"] if t["name"] == "Rotor")
    assert rotor["total"] == 2
    assert rotor["pcts"] == [50.0, 0.0, 0.0, 50.0]  # A 50%, Aucun 50%
    stator = next(t for t in d["teams"] if t["name"] == "Stator")
    assert stator["pcts"] == [0.0, 0.0, 0.0, 100.0]
    assert d["global"] == [33.3, 0.0, 0.0, 66.7]


def test_present_page_contient_distblock(client) -> None:
    # la page present embarque bien la fonction de rendu distribution
    html = client.get("/present").text
    assert "distBlock" in html
    assert "distColor" in html
