"""Оркестратор: ТОЛЬКО планирует и передаёт сообщения. Предметной работы не делает.

Цикл итерации:  Дизайнер -> Критик (до MAX_REVISIONS возвратов на доработку) -> Симулятор -> Аналитик.
После цикла: Репортёр собирает отчёт.
Защита от зацикливания: лимит итераций, лимит времени и определение цикла
(если баланс вернулся в состояние, которое уже было, останавливаемся: stop_reason="cycle").
"""
from __future__ import annotations

import copy
import time
import uuid

from logger import log_event
from messages import AnalysisReport, CritiqueReport, SimResult
from store import Store

NAME = "orchestrator"
MAX_REVISIONS = 2  # сколько раз Критик может вернуть правку Дизайнеру за одну итерацию


class Orchestrator:
    def __init__(self, designer, critic, simulator, analyst, store: Store, max_iters: int = 8,
                 max_seconds: float = 120.0, n_matches: int = 500, seed: int = 42, reporter=None):
        self.designer, self.critic, self.simulator, self.analyst, self.store = (
            designer, critic, simulator, analyst, store)
        self.reporter = reporter  # необязателен: без него итоговый отчёт просто не пишется
        self.max_iters, self.max_seconds = max_iters, max_seconds
        self.n_matches, self.seed = n_matches, seed

    def _get_approved_proposal(self, i: int, balance: dict, report: AnalysisReport | None):
        """Просит правку у Дизайнера и показывает Критику; при отказе возвращает на доработку."""
        critique: CritiqueReport | None = None
        for attempt in range(MAX_REVISIONS + 1):
            proposal = self.designer.propose(i, balance, report, critique)
            critique = self.critic.review(proposal, balance, report)
            if critique.approved:
                return proposal, critique, attempt  # attempt = сколько раз правку возвращали на доработку
            log_event(NAME, "agent", "revision_requested", {"iteration": i, "attempt": attempt + 1},
                      [issue.code for issue in critique.issues])
        return None, critique, MAX_REVISIONS + 1

    def run(self, balance: dict) -> dict:
        run_id = uuid.uuid4().hex[:8]
        t0 = time.monotonic()
        prev: SimResult | None = None
        report: AnalysisReport | None = None
        stop_reason = "max_iters"
        start_balance = copy.deepcopy(balance)
        skipped: list[int] = []
        seen_hashes: set[str] = set()
        log_event(NAME, "agent", "start", {"run_id": run_id, "max_iters": self.max_iters})

        for i in range(1, self.max_iters + 1):
            if time.monotonic() - t0 > self.max_seconds:
                stop_reason = "timeout"
                break
            proposal, critique, revisions = self._get_approved_proposal(i, balance, report)
            if proposal is None:  # Критик отклонил все попытки -> итерацию пропускаем
                skipped.append(i)
                log_event(NAME, "agent", "skip_iteration", {"iteration": i}, None, ok=False,
                          error="правка не прошла проверку Критика")
                continue
            try:
                # seed меняется по итерациям, но воспроизводимо
                prev, balance = self.simulator.run(proposal, balance, self.n_matches, self.seed + i)
            except ValueError as e:  # BalanceError (страховка: Критик такое уже отсекает)
                skipped.append(i)
                log_event(NAME, "agent", "skip_iteration", {"iteration": i}, None, ok=False, error=str(e))
                continue
            report = self.analyst.analyze(prev)
            # отчёты кладём внутрь result, чтобы не менять схему таблицы
            result = {**prev.model_dump(), "analysis": report.model_dump(), "critique": critique.model_dump(),
                      "revisions": revisions}
            self.store.save_iteration(run_id, i, proposal.model_dump(by_alias=True), result, balance)
            if report.balanced:
                stop_reason = "converged"
                break
            if prev.balance_hash in seen_hashes:  # баланс уже был -> дальше пойдём по кругу
                stop_reason = "cycle"
                break
            seen_hashes.add(prev.balance_hash)

        report_path = None
        if self.reporter is not None:
            report_path = self.reporter.write(run_id, stop_reason, start_balance, balance,
                                              self.store.history(run_id), skipped)
        log_event(NAME, "agent", "finish", {"run_id": run_id}, {"stop_reason": stop_reason})
        return {"run_id": run_id, "stop_reason": stop_reason, "final_balance": balance,
                "last": prev, "report": report, "report_path": report_path, "skipped": skipped}
