# File: main.py
"""Composition root. Seul endroit ou tout se branche.

Variables d'environnement :
  SECRET_KEY  signature des cookies participants. Generee par Render
              (render.yaml, generateValue) ou par defaut au boot.
  HOST_KEY    cle de la vue de controle : /host?key=HOST_KEY. Idem.
  QUIZ_CONFIG chemin du fichier de configuration, defaut quiz_config.json.

Si une cle manque, une valeur aleatoire est generee et LOGGEE au demarrage :
la lire dans les logs, ou fixer la variable d'environnement.

IMPORTANT : un seul worker uvicorn. L'etat du quiz vit en memoire du process.
Plusieurs workers fragmenteraient l'etat entre process et casseraient tout.
Le startCommand de render.yaml impose --workers 1.
"""
from __future__ import annotations

import os
import sys

from quizlive.application.service import QuizService
from quizlive.domain.model import Quiz
from quizlive.domain.scoring import DecliningSpeedScore
from quizlive.infra.config_loader import SystemClock, load_config
from quizlive.infra.hub import Hub
from quizlive.web.app import create_app, generate_key

CONFIG_PATH = os.environ.get("QUIZ_CONFIG", "quiz_config.json")

secret_key = os.environ.get("SECRET_KEY")
if not secret_key:
    secret_key = generate_key()
    print(f"[quizlive] SECRET_KEY absent, genere pour cette session.", file=sys.stderr)

host_key = os.environ.get("HOST_KEY")
if not host_key:
    host_key = generate_key()
    print(f"[quizlive] HOST_KEY absent, cle de session : {host_key}", file=sys.stderr)
    print(f"[quizlive] Vue de controle : /host?key={host_key}", file=sys.stderr)

config = load_config(CONFIG_PATH)
clock = SystemClock()
quiz = Quiz(
    quiz_id=config.quiz_id,
    questions=config.questions,
    teams=config.teams,
    clock=clock,
    scoring=DecliningSpeedScore(base=1000, floor=500),
)
hub = Hub()
service = QuizService(quiz, clock, hub, config.labels)
app = create_app(service, hub, secret_key=secret_key, host_key=host_key)
