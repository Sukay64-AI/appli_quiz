# File: tests/test_reset.py
"""Reset : retour LOBBY, tout efface, depuis n'importe quelle phase, et
utilisable de bout en bout via la route host protegee."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from quizlive.application.service import QuizService
from quizlive.domain.events import QuizReset
from quizlive.domain.model import Phase, Quiz
from quizlive.domain.scoring import DecliningSpeedScore
from quizlive.infra.config_loader import load_config
from quizlive.infra.hub import Hub
from quizlive.web.app import create_app
from tests.conftest import FakeClock

HOST_KEY = "test-host-key"


def test_reset_domaine_remet_a_zero(quiz: Quiz) -> None:
    quiz.join("r1", "rouge", "Alice", "t1")
    quiz.open_next()
    quiz.submit_answer("r1", 1)
    quiz.close_question()
    quiz.collect_events()

    quiz.reset()

    assert quiz.phase is Phase.LOBBY
    assert quiz.current_index is None
    assert quiz.opened_at is None
    assert quiz.participants_count() == 0
    assert quiz.votes_count("q0") == 0
    assert quiz.leaderboard()[0].avg_score == 0.0
    assert any(isinstance(e, QuizReset) for e in quiz.collect_events())


def test_reset_depuis_finished(quiz: Quiz) -> None:
    quiz.open_next(); quiz.close_question()
    quiz.open_next(); quiz.close_question()
    quiz.open_next(); quiz.close_question()
    quiz.finish()
    assert quiz.phase is Phase.FINISHED
    quiz.reset()
    assert quiz.phase is Phase.LOBBY


def test_reset_puis_rejouer(quiz: Quiz) -> None:
    quiz.join("r1", "rouge", "Alice", "t1")
    quiz.open_next()
    quiz.reset()
    # on peut refaire un cycle complet apres reset
    quiz.join("b1", "bleu", "Bob", "t2")
    quiz.open_next()
    assert quiz.current_question().id == "q0"
    ans = quiz.submit_answer("b1", 1)
    assert ans.correct is True


@pytest.fixture
def client(tmp_path) -> TestClient:
    cfg = {
        "quiz_id": "t",
        "teams": [{"id": "rotor", "name": "Rotor"}],
        "questions": [
            {"id": "q0", "order": 0, "labels": ["A", "B"],
             "correct_option": 1, "time_limit_s": 20},
        ],
    }
    path = tmp_path / "cfg.json"
    path.write_text(json.dumps(cfg), encoding="utf-8")
    config = load_config(path)
    clock = FakeClock()
    quiz = Quiz(config.quiz_id, config.questions, config.teams, clock, DecliningSpeedScore())
    hub = Hub()
    service = QuizService(quiz, clock, hub, config.labels)
    return TestClient(create_app(service, hub, secret_key="s", host_key=HOST_KEY))


def test_route_reset_sans_cle_403(client: TestClient) -> None:
    assert client.post("/api/host/reset").status_code == 403
    assert client.post("/api/host/reset?key=faux").status_code == 403


def test_route_reset_flux_complet(client: TestClient) -> None:
    client.post("/api/join", json={"nickname": "Alice", "team_id": "rotor"})
    client.post(f"/api/host/open?key={HOST_KEY}")
    client.post("/api/vote", json={"option": 1})
    client.post(f"/api/host/close?key={HOST_KEY}")

    p = client.get("/api/present-state").json()
    assert p["participants"] == 1

    r = client.post(f"/api/host/reset?key={HOST_KEY}")
    assert r.status_code == 200 and r.json()["status"] == "ok"

    p = client.get("/api/present-state").json()
    assert p["phase"] == "LOBBY"
    assert p["participants"] == 0

    # l'ancien cookie n'est plus reconnu comme inscrit apres reset
    s = client.get("/api/state").json()
    assert s["registered"] is False


def test_present_state_expose_is_last(client: TestClient) -> None:
    # un seul question : des qu'elle est ouverte, is_last vrai
    client.post(f"/api/host/open?key={HOST_KEY}")
    p = client.get("/api/present-state").json()
    assert p["is_last"] is True
