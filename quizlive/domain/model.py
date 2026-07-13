# File: quizlive/domain/model.py
"""Coeur du domaine.

Agregat Quiz. Seule autorite de l'etat. Les telephones sont des ecrans passifs.
La machine a etats vit ici, pas dans le client. Toute regle de vote, de score
et de statistique passe par cet objet.

Machine a etats :
    LOBBY --open_next--> QUESTION_OPEN(n) --close_question--> QUESTION_CLOSED(n)
    QUESTION_CLOSED(n) --open_next--> QUESTION_OPEN(n+1)
    QUESTION_CLOSED(n) --finish--> FINISHED

Aucune I/O, aucun framework. Depend uniquement des ports Clock et ScoringPolicy,
injectes. Conforme a la purete du domaine.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto

from quizlive.domain.errors import (
    AlreadyAnswered,
    DuplicateParticipant,
    InvalidOption,
    InvalidTransition,
    LateVote,
    NoMoreQuestions,
    UnknownParticipant,
    UnknownQuestion,
    UnknownTeam,
    VotingClosed,
)
from quizlive.domain.events import (
    AnswerAccepted,
    DomainEvent,
    ParticipantJoined,
    QuestionClosed,
    QuestionOpened,
    QuizFinished,
    QuizReset,
)
from quizlive.domain.ports import Clock
from quizlive.domain.scoring import ScoringPolicy


class Phase(Enum):
    LOBBY = auto()
    QUESTION_OPEN = auto()
    QUESTION_CLOSED = auto()
    FINISHED = auto()


# --- Types passifs : configuration et lecture ------------------------------


@dataclass(frozen=True)
class Question:
    """Ce dont l'app a besoin pour une question. L'enonce et les figures vivent
    dans le PowerPoint, PAS ici. Seulement le nombre d'options, la bonne, et le
    temps limite."""

    id: str
    order: int
    n_options: int
    correct_option: int
    time_limit_s: float

    def __post_init__(self) -> None:
        if self.n_options < 2:
            raise ValueError("n_options doit etre >= 2")
        if not 0 <= self.correct_option < self.n_options:
            raise ValueError("correct_option hors intervalle")
        if self.time_limit_s <= 0:
            raise ValueError("time_limit_s doit etre > 0")


@dataclass(frozen=True)
class Team:
    id: str
    name: str


@dataclass(frozen=True)
class Participant:
    id: str
    team_id: str
    nickname: str
    token: str


@dataclass(frozen=True)
class Answer:
    question_id: str
    participant_id: str
    option: int
    submitted_at: datetime
    elapsed_s: float
    correct: bool
    score: int


@dataclass(frozen=True)
class TeamScore:
    team_id: str
    name: str
    avg_score: float
    members: int


@dataclass(frozen=True)
class QuestionStats:
    """Distribution des votes d'une question. Sert au global ET au par-equipe."""

    question_id: str
    counts: dict[int, int]  # option -> nombre de votes
    correct: int
    total: int


# --- Agregat ---------------------------------------------------------------


class Quiz:
    def __init__(
        self,
        quiz_id: str,
        questions: list[Question],
        teams: list[Team],
        clock: Clock,
        scoring: ScoringPolicy,
    ) -> None:
        if not questions:
            raise ValueError("au moins une question")
        if not teams:
            raise ValueError("au moins une equipe")

        ordered = sorted(questions, key=lambda q: q.order)
        if [q.order for q in ordered] != list(range(len(ordered))):
            raise ValueError("les orders des questions doivent etre 0..n-1 sans trou")
        if len({q.id for q in ordered}) != len(ordered):
            raise ValueError("identifiants de question dupliques")
        if len({t.id for t in teams}) != len(teams):
            raise ValueError("identifiants d'equipe dupliques")

        self._id = quiz_id
        self._questions: tuple[Question, ...] = tuple(ordered)
        self._teams: dict[str, Team] = {t.id: t for t in teams}
        self._clock = clock
        self._scoring = scoring

        self._phase: Phase = Phase.LOBBY
        self._current_index: int | None = None
        self._opened_at: datetime | None = None
        self._participants: dict[str, Participant] = {}
        self._answers: dict[tuple[str, str], Answer] = {}
        self._events: list[DomainEvent] = []

    # --- lecture d'etat ---

    @property
    def id(self) -> str:
        return self._id

    @property
    def phase(self) -> Phase:
        return self._phase

    @property
    def teams(self) -> tuple[Team, ...]:
        return tuple(self._teams.values())

    @property
    def questions(self) -> tuple[Question, ...]:
        return self._questions

    def current_question(self) -> Question | None:
        if self._current_index is None:
            return None
        return self._questions[self._current_index]

    @property
    def current_index(self) -> int | None:
        return self._current_index

    @property
    def opened_at(self) -> datetime | None:
        return self._opened_at

    def get_participant(self, participant_id: str) -> Participant | None:
        return self._participants.get(participant_id)

    def participants_count(self) -> int:
        return len(self._participants)

    def participants_by_team(self) -> dict[str, int]:
        counts = {tid: 0 for tid in self._teams}
        for participant in self._participants.values():
            counts[participant.team_id] += 1
        return counts

    def votes_count(self, question_id: str) -> int:
        return sum(1 for (qid, _pid) in self._answers if qid == question_id)

    def answer_of(self, participant_id: str, question_id: str) -> Answer | None:
        return self._answers.get((question_id, participant_id))

    def participant_total(self, participant_id: str) -> int:
        return sum(
            answer.score
            for (_qid, pid), answer in self._answers.items()
            if pid == participant_id
        )

    # --- evenements ---

    def collect_events(self) -> list[DomainEvent]:
        """Draine et vide la file d'evenements. La couche application les publie."""
        drained = self._events
        self._events = []
        return drained

    def _emit(self, event: DomainEvent) -> None:
        self._events.append(event)

    # --- inscriptions ---

    def join(self, participant_id: str, team_id: str, nickname: str, token: str) -> Participant:
        if self._phase is Phase.FINISHED:
            raise InvalidTransition("quiz termine, inscription fermee")
        if team_id not in self._teams:
            raise UnknownTeam(team_id)
        if participant_id in self._participants:
            raise DuplicateParticipant(participant_id)
        participant = Participant(participant_id, team_id, nickname, token)
        self._participants[participant_id] = participant
        self._emit(ParticipantJoined(participant_id, team_id))
        return participant

    # --- machine a etats ---

    def open_next(self) -> Question:
        if self._phase is Phase.LOBBY:
            index = 0
        elif self._phase is Phase.QUESTION_CLOSED:
            assert self._current_index is not None
            index = self._current_index + 1
        else:
            raise InvalidTransition(f"open_next interdit depuis {self._phase.name}")

        if index >= len(self._questions):
            raise NoMoreQuestions()

        self._current_index = index
        self._opened_at = self._clock.now()
        self._phase = Phase.QUESTION_OPEN
        question = self._questions[index]
        self._emit(
            QuestionOpened(question.id, question.order, self._opened_at, question.time_limit_s)
        )
        return question

    def close_question(self) -> None:
        if self._phase is not Phase.QUESTION_OPEN:
            raise InvalidTransition(f"close_question interdit depuis {self._phase.name}")
        question = self._questions[self._current_index]  # type: ignore[index]
        self._phase = Phase.QUESTION_CLOSED
        self._emit(QuestionClosed(question.id, question.order))

    def finish(self) -> None:
        if self._phase is not Phase.QUESTION_CLOSED:
            raise InvalidTransition(f"finish interdit depuis {self._phase.name}")
        self._phase = Phase.FINISHED
        self._emit(QuizFinished())

    def reset(self) -> None:
        """Remet le quiz a zero : retour en LOBBY, participants, votes et scores
        effaces. Autorise depuis n'importe quelle phase. Sert entre la
        repetition et la vraie session, ou pour repartir proprement."""
        self._phase = Phase.LOBBY
        self._current_index = None
        self._opened_at = None
        self._participants.clear()
        self._answers.clear()
        self._emit(QuizReset())

    # --- vote ---

    def submit_answer(self, participant_id: str, option: int) -> Answer:
        if self._phase is not Phase.QUESTION_OPEN:
            raise VotingClosed()
        participant = self._participants.get(participant_id)
        if participant is None:
            raise UnknownParticipant(participant_id)

        question = self._questions[self._current_index]  # type: ignore[index]
        if not 0 <= option < question.n_options:
            raise InvalidOption(option)

        key = (question.id, participant_id)
        if key in self._answers:
            raise AlreadyAnswered()

        assert self._opened_at is not None
        now = self._clock.now()
        elapsed_s = (now - self._opened_at).total_seconds()
        if elapsed_s > question.time_limit_s:
            raise LateVote()

        correct = option == question.correct_option
        score = self._scoring.score(
            correct=correct, elapsed_s=elapsed_s, time_limit_s=question.time_limit_s
        )
        answer = Answer(question.id, participant_id, option, now, elapsed_s, correct, score)
        self._answers[key] = answer
        self._emit(AnswerAccepted(question.id, participant_id, correct, score))
        return answer

    # --- classement et statistiques ---

    def leaderboard(self) -> list[TeamScore]:
        """Classement inter-equipe. Score d'equipe = MOYENNE des totaux de ses
        membres inscrits. Choix impose par des tailles d'equipe heterogenes :
        la somme favoriserait mecaniquement la grosse equipe. Equipe sans
        membre inscrit -> 0."""
        totals: dict[str, int] = {pid: 0 for pid in self._participants}
        for (_qid, pid), answer in self._answers.items():
            totals[pid] += answer.score

        members_by_team: dict[str, list[int]] = {tid: [] for tid in self._teams}
        for pid, participant in self._participants.items():
            members_by_team[participant.team_id].append(totals[pid])

        board: list[TeamScore] = []
        for tid, team in self._teams.items():
            member_totals = members_by_team[tid]
            avg = sum(member_totals) / len(member_totals) if member_totals else 0.0
            board.append(TeamScore(tid, team.name, avg, len(member_totals)))

        board.sort(key=lambda ts: (-ts.avg_score, ts.name))
        return board

    def stats_global(self, question_id: str) -> QuestionStats:
        """Distribution globale des votes d'une question, toutes equipes."""
        question = self._question_by_id(question_id)
        counts = {i: 0 for i in range(question.n_options)}
        correct = 0
        total = 0
        for (qid, _pid), answer in self._answers.items():
            if qid != question_id:
                continue
            counts[answer.option] += 1
            total += 1
            if answer.correct:
                correct += 1
        return QuestionStats(question_id, counts, correct, total)

    def stats_by_team(self, question_id: str) -> dict[str, QuestionStats]:
        """Distribution d'une question ventilee par equipe. Combinee avec
        stats_global, ca couvre les trois besoins de stats."""
        question = self._question_by_id(question_id)
        counts: dict[str, dict[int, int]] = {
            tid: {i: 0 for i in range(question.n_options)} for tid in self._teams
        }
        correct: dict[str, int] = {tid: 0 for tid in self._teams}
        total: dict[str, int] = {tid: 0 for tid in self._teams}

        for (qid, pid), answer in self._answers.items():
            if qid != question_id:
                continue
            tid = self._participants[pid].team_id
            counts[tid][answer.option] += 1
            total[tid] += 1
            if answer.correct:
                correct[tid] += 1

        return {
            tid: QuestionStats(question_id, counts[tid], correct[tid], total[tid])
            for tid in self._teams
        }

    def _question_by_id(self, question_id: str) -> Question:
        for question in self._questions:
            if question.id == question_id:
                return question
        raise UnknownQuestion(question_id)
