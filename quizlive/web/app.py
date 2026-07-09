# File: quizlive/web/app.py
"""Couche web FastAPI. Adaptateur entrant : routes HTTP, endpoint WebSocket,
traduction des erreurs domaine en reponses HTTP. Aucune regle metier ici.

Robustesse reseau, decisions issues du test de sonde sur le reseau LTS :
- le vote monte en POST HTTP, pas par WebSocket : un gel de socket ne bloque
  pas le vote, une nouvelle connexion HTTP suffit ;
- AlreadyAnswered repond 200 {status: already} : si le premier POST a abouti
  mais que la reponse s'est perdue dans un gel, le retry cote client passe
  pour un succes, l'utilisateur n'y voit que du feu ;
- heartbeat serveur toutes les 15 s vers toutes les connexions, ping client
  25 s : les proxys qui tuent l'inactif ne mordent pas.
"""
from __future__ import annotations

import asyncio
import contextlib
import secrets

import segno
from fastapi import FastAPI, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse

from quizlive.application.service import QuizService
from quizlive.domain.errors import (
    AlreadyAnswered,
    DomainError,
    InvalidOption,
    InvalidTransition,
    LateVote,
    NoMoreQuestions,
    UnknownTeam,
    VotingClosed,
)
from quizlive.infra.hub import ALL_ROLES, Hub
from quizlive.web import security
from quizlive.web.pages import host_page, play_page, present_page

HEARTBEAT_EVERY_S = 15.0


def create_app(service: QuizService, hub: Hub, secret_key: str, host_key: str) -> FastAPI:
    heartbeat_task: dict = {}

    @contextlib.asynccontextmanager
    async def lifespan(_app: FastAPI):
        async def beat() -> None:
            while True:
                await asyncio.sleep(HEARTBEAT_EVERY_S)
                await hub.broadcast({"type": "hb"})

        heartbeat_task["t"] = asyncio.create_task(beat())
        yield
        heartbeat_task["t"].cancel()

    app = FastAPI(lifespan=lifespan)

    # --- pages ---

    @app.get("/", response_class=HTMLResponse)
    async def root() -> str:
        return play_page()

    @app.get("/play", response_class=HTMLResponse)
    async def play() -> str:
        return play_page()

    @app.get("/present", response_class=HTMLResponse)
    async def present() -> str:
        return present_page()

    @app.get("/host", response_class=HTMLResponse)
    async def host() -> str:
        return host_page()

    # --- helpers ---

    def _pid(request: Request) -> str | None:
        return security.verify(secret_key, request.cookies.get(security.COOKIE_NAME))

    def _join_url(request: Request) -> str:
        base = str(request.base_url).rstrip("/")
        return f"{base}/play"

    # --- API participants ---

    @app.post("/api/join")
    async def join(request: Request, response: Response) -> dict:
        body = await request.json()
        nickname = str(body.get("nickname", "")).strip()[:20]
        team_id = str(body.get("team_id", ""))
        if len(nickname) < 2:
            return JSONResponse({"detail": "pseudo trop court"}, status_code=400)

        existing = _pid(request)
        if existing and service.player_state(existing)["registered"]:
            return {"status": "already-registered"}

        participant_id = security.new_participant_id()
        try:
            service.join(participant_id, team_id, nickname, token="cookie")
        except UnknownTeam:
            return JSONResponse({"detail": "equipe inconnue"}, status_code=400)
        except InvalidTransition:
            return JSONResponse({"detail": "quiz termine"}, status_code=409)

        response.set_cookie(
            security.COOKIE_NAME,
            security.sign(secret_key, participant_id),
            max_age=security.COOKIE_MAX_AGE_S,
            httponly=True,
            samesite="lax",
            secure=(request.url.scheme == "https"),
        )
        await service.notify_vote()  # met a jour le compteur de participants
        return {"status": "ok"}

    @app.get("/api/state")
    async def state(request: Request) -> dict:
        return service.player_state(_pid(request))

    @app.post("/api/vote")
    async def vote(request: Request) -> dict:
        pid = _pid(request)
        if pid is None:
            return JSONResponse({"status": "unknown", "detail": "non inscrit"}, status_code=401)
        body = await request.json()
        try:
            option = int(body.get("option"))
        except (TypeError, ValueError):
            return JSONResponse({"detail": "option invalide"}, status_code=400)

        try:
            service.submit_vote(pid, option)
        except AlreadyAnswered:
            return {"status": "already"}
        except (VotingClosed, LateVote):
            return JSONResponse({"status": "closed"}, status_code=409)
        except InvalidOption:
            return JSONResponse({"detail": "option invalide"}, status_code=400)
        except DomainError:
            return JSONResponse({"status": "unknown"}, status_code=401)

        await service.notify_vote()
        return {"status": "ok"}

    # --- API lecture publique (ecran, controle) ---

    @app.get("/api/present-state")
    async def present_state(request: Request) -> dict:
        return service.present_state(_join_url(request))

    @app.get("/api/qr.svg")
    async def qr(request: Request) -> Response:
        svg = segno.make(_join_url(request), error="m").svg_inline(scale=8)
        return Response(content=svg, media_type="image/svg+xml")

    # --- API host, protegee ---

    def _check_key(request: Request) -> bool:
        return security.check_host_key(host_key, request.query_params.get("key"))

    async def _host_action(request: Request, action) -> Response | dict:
        if not _check_key(request):
            return JSONResponse({"detail": "cle host invalide"}, status_code=403)
        try:
            action()
        except NoMoreQuestions:
            return JSONResponse(
                {"detail": "plus de question, utilisez Terminer"}, status_code=409
            )
        except InvalidTransition as exc:
            return JSONResponse({"detail": str(exc)}, status_code=409)
        await service.notify_update()
        return {"status": "ok"}

    @app.post("/api/host/open")
    async def host_open(request: Request):
        return await _host_action(request, service.open_next)

    @app.post("/api/host/close")
    async def host_close(request: Request):
        return await _host_action(request, service.close_question)

    @app.post("/api/host/finish")
    async def host_finish(request: Request):
        return await _host_action(request, service.finish)

    @app.get("/api/export")
    async def export(request: Request):
        if not _check_key(request):
            return JSONResponse({"detail": "cle host invalide"}, status_code=403)
        return service.export()

    @app.get("/healthz")
    async def healthz() -> dict:
        return {"ok": True}

    # --- WebSocket sonnette ---

    @app.websocket("/ws/{role}")
    async def ws_endpoint(ws: WebSocket, role: str) -> None:
        if role not in ALL_ROLES:
            await ws.close(code=4000)
            return
        await ws.accept()
        hub.register(role, ws)
        try:
            while True:
                await ws.receive_text()  # pings client, contenu ignore
        except WebSocketDisconnect:
            pass
        finally:
            hub.unregister(role, ws)

    return app


def generate_key() -> str:
    return secrets.token_urlsafe(16)
