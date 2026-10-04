"""Оркестратор: ТОЛЬКО планирует и передаёт сообщения. Предметной работы не делает.

Защита от зацикливания: лимит итераций и лимит времени.
"""
from __future__ import annotations

import time
import uuid

from logger import log_event
from messages import SimResult
from store import Store

NAME = "orchestrator"
TARGET = (0.45, 0.55)  # допустимый диапазон винрейтов


def converged(res: SimResult) -> bool:
    values = list(res.side_winrate.values()) + list(res.unit_winrate.values())
    return all(TARGET[0] <= v <= TARGET[1] for v in values)


class Orchestrator:
    def __init__(self, designer, simulator, store: Store, max_iters: int = 8,
                 max_seconds: float = 120.0, n_matches: int = 500, seed: int = 42):
        self.designer, self.simulator, self.store = designer, simulator, store
        self.max_iters, self.max_seconds = max_iters, max_seconds
        self.n_matches, self.seed = n_matches, seed

    def run(self, balance: dict) -> dict:
        run_id = uuid.uuid4().hex[:8]
        t0 = time.monotonic()
        prev: SimResult | None = None
        stop_reason = "max_iters"
        log_event(NAME, "agent", "start", {"run_id": run_id, "max_iters": self.max_iters})

        for i in range(1, self.max_iters + 1):
            if time.monotonic() - t0 > self.max_seconds:
                stop_reason = "timeout"
                break
            proposal = self.designer.propose(i, balance, prev)
            try:
                # seed меняется по итерациям, но воспроизводимо
                prev, balance = self.simulator.run(proposal, balance, self.n_matches, self.seed + i)
            except ValueError as e:  # BalanceError: невалидная правка -> пропускаем итерацию
                log_event(NAME, "agent", "skip_iteration", {"iteration": i}, None, ok=False, error=str(e))
                continue
            self.store.save_iteration(run_id, i, proposal.model_dump(by_alias=True), prev.model_dump(), balance)
            if converged(prev):
                stop_reason = "converged"
                break

        log_event(NAME, "agent", "finish", {"run_id": run_id}, {"stop_reason": stop_reason})
        return {"run_id": run_id, "stop_reason": stop_reason, "final_balance": balance, "last": prev}
