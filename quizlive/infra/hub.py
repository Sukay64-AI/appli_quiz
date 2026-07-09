# File: quizlive/infra/hub.py
"""Hub WebSocket. Tient les connexions par role et diffuse des messages JSON.

Roles :
  player   telephones. Recoivent les changements de phase.
  present  ecran projete. Recoit en plus le compteur de votes en direct.
  host     vue de controle. Comme present.

Le compteur de votes n'est diffuse qu'a present et host : le vote d'un tiers
ne change pas l'etat d'un player, inutile de faire refetch 100 telephones a
chaque vote. Les transitions de phase, elles, vont a tout le monde.

Un send qui echoue marque la connexion morte et la retire. Aucune exception
ne remonte au metier.
"""
from __future__ import annotations

import asyncio
from typing import Iterable

from fastapi import WebSocket

ALL_ROLES = ("player", "present", "host")


class Hub:
    def __init__(self) -> None:
        self._conns: dict[str, set[WebSocket]] = {r: set() for r in ALL_ROLES}

    def register(self, role: str, ws: WebSocket) -> None:
        self._conns[role].add(ws)

    def unregister(self, role: str, ws: WebSocket) -> None:
        self._conns[role].discard(ws)

    def count(self, role: str) -> int:
        return len(self._conns[role])

    async def broadcast(self, message: dict, roles: Iterable[str] = ALL_ROLES) -> None:
        targets = [ws for role in roles for ws in list(self._conns[role])]
        if not targets:
            return
        results = await asyncio.gather(
            *(ws.send_json(message) for ws in targets), return_exceptions=True
        )
        for ws, result in zip(targets, results):
            if isinstance(result, Exception):
                for role in ALL_ROLES:
                    self._conns[role].discard(ws)
