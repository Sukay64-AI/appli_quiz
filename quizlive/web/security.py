# File: quizlive/web/security.py
"""Identite participant par cookie signe, et cle host.

Cookie strictement necessaire au service demande : retrouver la session apres
une deconnexion (wifi instable, veille du telephone). La page de jonction
affiche un avis explicite avant depot. Contenu : uuid opaque + signature HMAC.
Aucun suivi, aucune donnee personnelle dedans.

Signature HMAC-SHA256 tronquee, cle SECRET_KEY. Un cookie forge sans la cle
est rejete. Apres redemarrage serveur l'etat memoire est vide : un cookie
valide mais inconnu du quiz est traite comme non inscrit, le front repropose
la jonction.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets

COOKIE_NAME = "quiz_pid"
COOKIE_MAX_AGE_S = 12 * 3600


def new_participant_id() -> str:
    return secrets.token_urlsafe(12)


def sign(secret: str, participant_id: str) -> str:
    mac = hmac.new(secret.encode(), participant_id.encode(), hashlib.sha256)
    return f"{participant_id}.{mac.hexdigest()[:32]}"


def verify(secret: str, cookie_value: str | None) -> str | None:
    """Retourne participant_id si la signature est valide, sinon None."""
    if not cookie_value or "." not in cookie_value:
        return None
    participant_id, _sig = cookie_value.rsplit(".", 1)
    expected = sign(secret, participant_id)
    if hmac.compare_digest(expected, cookie_value):
        return participant_id
    return None


def check_host_key(expected: str, provided: str | None) -> bool:
    if not provided:
        return False
    return hmac.compare_digest(expected, provided)
