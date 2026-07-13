# File: tests/test_web.py
"""Couche web. Points critiques :
- cookie pose au join, reconnu ensuite ;
- la bonne reponse ne fuit JAMAIS pendant OPEN ;
- AlreadyAnswered repond 200 already, idempotence du retry client ;
- actions host refusees sans cle ;
- flux complet jusqu'a FINISHED avec stats et classement.
"""
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

HOST_KEY = "test-host-key"


@pytest.fixture
def client(tmp_path) -> TestClient:
    cfg = {
        "quiz_id": "t",
        "teams": [
            {"id": "rotor", "name": "Rotor"},
            {"id": "stator", "name": "Stator"},
        ],
        "questions": [
            {"id": "q0", "order": 0, "labels": ["A", "B", "C"],
             "correct_option": 1, "time_limit_s": 20},
            {"id": "q1", "order": 1, "labels": ["OUI", "NON"],
             "correct_option": 1, "time_limit_s": 20},
        ],
    }
    path = tmp_path / "cfg.json"
    path.write_text(json.dumps(cfg), encoding="utf-8")
    config = load_config(path)
    clock = FakeClock()
    quiz = Quiz(config.quiz_id, config.questions, config.teams, clock, BinaryScore())
    hub = Hub()
    service = QuizService(quiz, clock, hub, config.labels)
    app = create_app(service, hub, secret_key="s3cret", host_key=HOST_KEY)
    return TestClient(app)


def _join(client: TestClient, nick: str, team: str) -> None:
    # jonction anonyme : seul team_id compte, nick conserve en parametre
    # pour la lisibilite des tests mais non transmis
    r = client.post("/api/join", json={"team_id": team})
    assert r.status_code == 200, r.text


def _host(client: TestClient, action: str, key: str = HOST_KEY):
    return client.post(f"/api/host/{action}?key={key}")


def test_pages_servies(client: TestClient) -> None:
    for path in ("/", "/play", "/present", "/host", "/healthz"):
        assert client.get(path).status_code == 200


def test_join_pose_cookie_et_state_personnalise(client: TestClient) -> None:
    r = client.get("/api/state")
    assert r.json()["registered"] is False

    _join(client, "Alice", "rotor")
    s = client.get("/api/state").json()
    assert s["registered"] is True
    assert s["me"]["nickname"] == ""
    assert s["me"]["team"] == "Rotor"


def test_join_anonyme_accepte(client: TestClient) -> None:
    r = client.post("/api/join", json={"team_id": "rotor"})
    assert r.status_code == 200


def test_join_equipe_inconnue(client: TestClient) -> None:
    r = client.post("/api/join", json={"nickname": "Alice", "team_id": "xxx"})
    assert r.status_code == 400


def test_vote_sans_cookie_401(client: TestClient) -> None:
    r = client.post("/api/vote", json={"option": 0})
    assert r.status_code == 401


def test_reponse_ne_fuit_pas_pendant_open(client: TestClient) -> None:
    _join(client, "Alice", "rotor")
    _host(client, "open")
    s = client.get("/api/state").json()
    assert s["phase"] == "OPEN"
    dump = json.dumps(s)
    assert "correct_label" not in dump
    assert "correct_option" not in dump
    p = client.get("/api/present-state").json()
    assert "correct_label" not in json.dumps(p)


def test_vote_ok_puis_already(client: TestClient) -> None:
    _join(client, "Alice", "rotor")
    _host(client, "open")
    r1 = client.post("/api/vote", json={"option": 1})
    assert r1.status_code == 200 and r1.json()["status"] == "ok"
    r2 = client.post("/api/vote", json={"option": 2})
    assert r2.status_code == 200 and r2.json()["status"] == "already"
    s = client.get("/api/state").json()
    assert s["voted"] is True


def test_vote_apres_fermeture_409(client: TestClient) -> None:
    _join(client, "Alice", "rotor")
    _host(client, "open")
    _host(client, "close")
    r = client.post("/api/vote", json={"option": 0})
    assert r.status_code == 409 and r.json()["status"] == "closed"


def test_host_sans_cle_403(client: TestClient) -> None:
    assert _host(client, "open", key="mauvaise").status_code == 403
    r = client.post("/api/host/open")  # aucune cle
    assert r.status_code == 403


def test_host_transitions_invalides_409(client: TestClient) -> None:
    assert _host(client, "close").status_code == 409  # rien d'ouvert
    assert _host(client, "finish").status_code == 409


def test_revelation_apres_close(client: TestClient) -> None:
    _join(client, "Alice", "rotor")
    _host(client, "open")
    client.post("/api/vote", json={"option": 1})  # bonne reponse
    _host(client, "close")

    s = client.get("/api/state").json()
    assert s["phase"] == "CLOSED"
    assert s["result"]["correct"] is True
    assert s["result"]["score"] == 1  # binaire
    assert s["result"]["correct_label"] == "B"
    assert s["stats"]["total"] == 1
    assert s["leaderboard"][0]["name"] == "Rotor"
    assert s["leaderboard"][0]["pct"] == 100.0  # 1 bonne / 1 question jouee

    p = client.get("/api/present-state").json()
    assert p["correct_label"] == "B"
    assert p["stats"]["counts"] == [0, 1, 0]
    d = p["distribution"]
    assert d["correct_index"] == 1
    rotor = next(t for t in d["teams"] if t["name"] == "Rotor")
    assert rotor["pcts"][1] == 100.0  # Rotor a mis 100% sur l'option B
    stator = next(t for t in d["teams"] if t["name"] == "Stator")
    assert stator["total"] == 0


def test_flux_complet_jusqu_a_finished(client: TestClient) -> None:
    # deux joueurs, deux clients pour deux cookies distincts
    alice = client
    _join(alice, "Alice", "rotor")

    bob = TestClient(alice.app)
    _join(bob, "Bob", "stator")

    # Q0
    _host(alice, "open")
    alice.post("/api/vote", json={"option": 1})   # correct
    bob.post("/api/vote", json={"option": 0})     # faux
    _host(alice, "close")

    # Q1
    _host(alice, "open")
    alice.post("/api/vote", json={"option": 1})   # correct
    bob.post("/api/vote", json={"option": 1})     # correct
    _host(alice, "close")

    # plus de question : open doit refuser proprement
    assert _host(alice, "open").status_code == 409

    _host(alice, "finish")
    p = alice.get("/api/present-state").json()
    assert p["phase"] == "FINISHED"
    assert p["leaderboard"][0]["name"] == "Rotor"  # 100% vs 50%
    assert p["leaderboard"][0]["pct"] == 100.0
    assert len(p["per_question"]) == 2
    assert len(p["per_question_dist"]) == 2
    assert p["per_question_dist"][0]["correct_index"] == 1
    assert p["per_question"][0]["teams"]["Rotor"] == 100.0
    assert p["per_question"][0]["teams"]["Stator"] == 0.0

    # export protege
    assert alice.get("/api/export").status_code == 403
    exp = alice.get(f"/api/export?key={HOST_KEY}").json()
    assert exp["phase"] == "FINISHED"
    assert len(exp["per_question"]) == 2


def test_join_apres_finished_refuse(client: TestClient) -> None:
    _host(client, "open"); _host(client, "close")
    _host(client, "open"); _host(client, "close")
    _host(client, "finish")
    r = client.post("/api/join", json={"nickname": "Tard", "team_id": "rotor"})
    assert r.status_code == 409


def test_qr_svg(client: TestClient) -> None:
    r = client.get("/api/qr.svg")
    assert r.status_code == 200
    assert "svg" in r.headers["content-type"]


def test_websocket_sonnette(client: TestClient) -> None:
    with client.websocket_connect("/ws/present") as ws:
        _host(client, "open")
        msg = ws.receive_json()
        assert msg["type"] in ("update", "votes", "hb")


def test_websocket_role_inconnu_refuse(client: TestClient) -> None:
    with pytest.raises(Exception):
        with client.websocket_connect("/ws/pirate"):
            pass
