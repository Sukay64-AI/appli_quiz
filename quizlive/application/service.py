# File: quizlive/application/service.py
"""Couche application. Orchestration entre le domaine, l'horloge et le hub.

INVARIANT DE CONCURRENCE. Un seul worker uvicorn, une seule boucle asyncio.
Toutes les mutations du domaine sont synchrones et sans await interne : elles
sont donc atomiques vis-a-vis de la boucle. Ne jamais introduire d'await au
milieu d'une sequence mutation puis lecture d'evenements. Le broadcast, lui,
est await apres coup, c'est sans danger.

Pattern temps reel : le WebSocket est une sonnette, HTTP est la source de
verite. Sur transition de phase, on diffuse {type: update} a tous, chaque
client refait GET de son etat. Sur vote, on diffuse seulement le compteur a
present et host. Un message perdu pendant un gel reseau est sans consequence,
le refetch au reveil recupere tout.
"""
from __future__ import annotations

from quizlive.domain.errors import DomainError
from quizlive.domain.model import Phase, Quiz
from quizlive.domain.ports import Clock
from quizlive.infra.hub import Hub

PHASE_NAMES = {
    Phase.LOBBY: "LOBBY",
    Phase.QUESTION_OPEN: "OPEN",
    Phase.QUESTION_CLOSED: "CLOSED",
    Phase.FINISHED: "FINISHED",
}


class QuizService:
    def __init__(self, quiz: Quiz, clock: Clock, hub: Hub, labels: dict[str, list[str]]) -> None:
        self._quiz = quiz
        self._clock = clock
        self._hub = hub
        self._labels = labels

    # --- commandes participants ---

    def join(self, participant_id: str, team_id: str, nickname: str, token: str) -> None:
        self._quiz.join(participant_id, team_id, nickname, token)
        self._quiz.collect_events()

    def submit_vote(self, participant_id: str, option: int) -> None:
        """Leve les DomainError du domaine, la couche web les traduit."""
        self._quiz.submit_answer(participant_id, option)
        self._quiz.collect_events()

    async def notify_vote(self) -> None:
        question = self._quiz.current_question()
        votes = self._quiz.votes_count(question.id) if question else 0
        await self._hub.broadcast(
            {"type": "votes", "votes": votes, "participants": self._quiz.participants_count()},
            roles=("present", "host"),
        )

    # --- commandes host ---

    def open_next(self) -> None:
        self._quiz.open_next()
        self._quiz.collect_events()

    def close_question(self) -> None:
        self._quiz.close_question()
        self._quiz.collect_events()

    def finish(self) -> None:
        self._quiz.finish()
        self._quiz.collect_events()

    def reset(self) -> None:
        self._quiz.reset()
        self._quiz.collect_events()

    async def notify_update(self) -> None:
        await self._hub.broadcast({"type": "update"})

    # --- lectures : DTOs ---

    def _question_block(self) -> dict | None:
        question = self._quiz.current_question()
        if question is None:
            return None
        remaining = None
        if self._quiz.phase is Phase.QUESTION_OPEN and self._quiz.opened_at is not None:
            elapsed = (self._clock.now() - self._quiz.opened_at).total_seconds()
            remaining = max(0.0, question.time_limit_s - elapsed)
        return {
            "index": question.order,
            "count": len(self._quiz.questions),
            "labels": self._labels[question.id],
            "time_limit_s": question.time_limit_s,
            "remaining_s": remaining,
        }

    def _questions_played(self) -> int:
        """Nombre de questions deja jouees, pour le denominateur du pourcentage.
        Une question ouverte non encore fermee ne compte pas."""
        idx = self._quiz.current_index
        if idx is None:
            return 0
        return idx if self._quiz.phase is Phase.QUESTION_OPEN else idx + 1

    def _leaderboard_block(self) -> list[dict]:
        played = self._questions_played()
        out = []
        for ts in self._quiz.leaderboard():
            pct = round(100.0 * ts.avg_score / played, 1) if played else 0.0
            out.append({"name": ts.name, "pct": pct, "members": ts.members})
        return out

    def _distribution_block(self, question_id: str) -> dict:
        """Repartition des votes par equipe et par option, en pourcentage.
        C'est le visuel : chaque equipe, quel pourcentage a choisi chaque option,
        la bonne option etant marquee."""
        labels = self._labels[question_id]
        question = next(q for q in self._quiz.questions if q.id == question_id)
        n = len(labels)

        def pcts(counts: dict[int, int], total: int) -> list[float]:
            return [round(100.0 * counts[i] / total, 1) if total else 0.0 for i in range(n)]

        glob = self._quiz.stats_global(question_id)
        by_team = self._quiz.stats_by_team(question_id)
        teams = []
        for team in self._quiz.teams:
            st = by_team[team.id]
            teams.append({"name": team.name, "total": st.total, "pcts": pcts(st.counts, st.total)})
        return {
            "index": question.order,
            "labels": labels,
            "correct_index": question.correct_option,
            "global": pcts(glob.counts, glob.total),
            "global_total": glob.total,
            "teams": teams,
        }

    def _stats_blocks(self, question_id: str) -> tuple[dict, list[dict]]:
        glob = self._quiz.stats_global(question_id)
        n = len(self._labels[question_id])
        global_block = {
            "counts": [glob.counts[i] for i in range(n)],
            "correct": glob.correct,
            "total": glob.total,
        }
        by_team = self._quiz.stats_by_team(question_id)
        teams_block = []
        for team in self._quiz.teams:
            st = by_team[team.id]
            pct = round(100.0 * st.correct / st.total, 1) if st.total else 0.0
            teams_block.append(
                {"name": team.name, "total": st.total, "correct": st.correct, "pct": pct}
            )
        return global_block, teams_block

    def player_state(self, participant_id: str | None) -> dict:
        participant = (
            self._quiz.get_participant(participant_id) if participant_id else None
        )
        phase = self._quiz.phase
        state: dict = {
            "registered": participant is not None,
            "phase": PHASE_NAMES[phase],
            "teams": [{"id": t.id, "name": t.name} for t in self._quiz.teams],
        }
        if participant is None:
            return state

        team = next(t for t in self._quiz.teams if t.id == participant.team_id)
        state["me"] = {
            "nickname": participant.nickname,
            "team": team.name,
            "total": self._quiz.participant_total(participant.id),
        }

        question = self._quiz.current_question()
        if question is not None:
            state["question"] = self._question_block()
            answer = self._quiz.answer_of(participant.id, question.id)
            state["voted"] = answer is not None

            if phase in (Phase.QUESTION_CLOSED, Phase.FINISHED):
                labels = self._labels[question.id]
                state["result"] = {
                    "voted": answer is not None,
                    "correct": bool(answer.correct) if answer else False,
                    "score": answer.score if answer else 0,
                    "correct_label": labels[question.correct_option],
                }
                global_block, _teams = self._stats_blocks(question.id)
                state["stats"] = global_block

        if phase in (Phase.QUESTION_CLOSED, Phase.FINISHED):
            state["leaderboard"] = self._leaderboard_block()
        return state

    def present_state(self, join_url: str) -> dict:
        phase = self._quiz.phase
        idx = self._quiz.current_index
        is_last = idx is not None and idx >= len(self._quiz.questions) - 1
        state: dict = {
            "phase": PHASE_NAMES[phase],
            "participants": self._quiz.participants_count(),
            "quiz_id": self._quiz.id,
            "is_last": is_last,
        }
        if phase is Phase.LOBBY:
            counts = self._quiz.participants_by_team()
            state["join_url"] = join_url
            state["teams"] = [
                {"name": t.name, "members": counts[t.id]} for t in self._quiz.teams
            ]
            return state

        question = self._quiz.current_question()
        if question is not None:
            state["question"] = self._question_block()
            state["votes"] = self._quiz.votes_count(question.id)
            if phase in (Phase.QUESTION_CLOSED, Phase.FINISHED):
                global_block, teams_block = self._stats_blocks(question.id)
                state["stats"] = global_block
                state["stats_by_team"] = teams_block
                state["correct_label"] = self._labels[question.id][question.correct_option]
                state["distribution"] = self._distribution_block(question.id)

        if phase in (Phase.QUESTION_CLOSED, Phase.FINISHED):
            state["leaderboard"] = self._leaderboard_block()

        if phase is Phase.FINISHED:
            state["per_question"] = self.per_question_summary()
            last = self._quiz.current_index if self._quiz.current_index is not None else -1
            state["per_question_dist"] = [
                self._distribution_block(q.id)
                for q in self._quiz.questions
                if q.order <= last
            ]
        return state

    def per_question_summary(self) -> list[dict]:
        rows = []
        for question in self._quiz.questions:
            glob = self._quiz.stats_global(question.id)
            by_team = self._quiz.stats_by_team(question.id)
            pct = round(100.0 * glob.correct / glob.total, 1) if glob.total else 0.0
            rows.append(
                {
                    "index": question.order,
                    "total": glob.total,
                    "pct": pct,
                    "teams": {
                        t.name: (
                            round(100.0 * by_team[t.id].correct / by_team[t.id].total, 1)
                            if by_team[t.id].total
                            else 0.0
                        )
                        for t in self._quiz.teams
                    },
                }
            )
        return rows

    def export(self) -> dict:
        """Dump complet pour analyse post-evenement."""
        participants = []
        counts = self._quiz.participants_by_team()
        for team in self._quiz.teams:
            participants.append({"team": team.name, "members": counts[team.id]})
        answers = []
        for question in self._quiz.questions:
            global_block, teams_block = self._stats_blocks(question.id)
            answers.append(
                {"question": question.id, "global": global_block, "by_team": teams_block}
            )
        return {
            "quiz_id": self._quiz.id,
            "phase": PHASE_NAMES[self._quiz.phase],
            "participants_by_team": participants,
            "leaderboard": self._leaderboard_block(),
            "per_question": answers,
        }
