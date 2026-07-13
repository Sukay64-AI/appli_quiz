# File: quizlive/infra/config_loader.py
"""Charge quiz_config.json et construit les objets du domaine.

Les labels des options sont de la presentation, pas du domaine : le domaine ne
connait que n_options. Les labels sont retournes a part pour la couche web.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from quizlive.domain.model import Question, Team


class SystemClock:
    """Adaptateur du port Clock. Temps serveur UTC."""

    def now(self) -> datetime:
        return datetime.now(timezone.utc)


@dataclass(frozen=True)
class QuizConfig:
    quiz_id: str
    questions: list[Question]
    teams: list[Team]
    labels: dict[str, list[str]]  # question_id -> labels des options
    texts: dict[str, str]  # question_id -> enonce court, optionnel


def load_config(path: str | Path) -> QuizConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))

    teams = [Team(id=t["id"], name=t["name"]) for t in raw["teams"]]

    questions: list[Question] = []
    labels: dict[str, list[str]] = {}
    texts: dict[str, str] = {}
    for q in raw["questions"]:
        qlabels = list(q["labels"])
        questions.append(
            Question(
                id=q["id"],
                order=int(q["order"]),
                n_options=len(qlabels),
                correct_option=int(q["correct_option"]),
                time_limit_s=float(q["time_limit_s"]),
            )
        )
        labels[q["id"]] = qlabels
        texts[q["id"]] = str(q.get("text", ""))

    return QuizConfig(
        quiz_id=raw["quiz_id"], questions=questions, teams=teams, labels=labels, texts=texts
    )
