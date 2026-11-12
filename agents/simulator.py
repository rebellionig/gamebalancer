"""Агент-Симулятор. Единственная роль: применить правки и прогнать батч матчей.

LLM не использует. Один вызов = один батч (иначе он перегрузит статистику вызовов).
"""
from __future__ import annotations

import itertools
import time

from game import balance as bal
from game.engine import UNIT_TYPES, run_batch, run_matchup
from logger import log_event, logged
from messages import ChangeProposal, SimResult

NAME = "simulator"
RETRIES = 2
PURE_N = 150  # матчей на каждую пару «чистых» составов


class Simulator:
    def run(self, proposal: ChangeProposal, base_balance: dict, n_matches: int, seed: int
            ) -> tuple[SimResult, dict]:
        """Возвращает (результат, новый баланс). Ошибки движка ретраятся, невалидная правка - нет."""
        changes = [{"unit": c.unit, "param": c.param, "to": c.to} for c in proposal.changes]
        new_balance = bal.apply_changes(base_balance, changes)  # BalanceError пробрасываем наверх

        last_err = None
        for attempt in range(1, RETRIES + 2):
            try:
                stats = self._engine(new_balance, n_matches, seed)
                break
            except Exception as e:  # noqa: BLE001 - любая ошибка движка -> повтор
                last_err = e
                time.sleep(0.1 * attempt)
        else:
            raise RuntimeError(f"Симулятор: движок упал {RETRIES + 1} раза: {last_err!r}")

        result = SimResult(iteration=proposal.iteration, balance_hash=bal.digest(new_balance), **stats)
        log_event(NAME, "agent", "run", proposal.model_dump(by_alias=True), result.model_dump())
        return result, new_balance

    @logged(NAME, "tool", "engine.simulate")
    def _engine(self, balance: dict, n_matches: int, seed: int) -> dict:
        """ОДИН вызов инструмента: смешанный батч + матрица чистых матчей (чтобы не раздувать долю Симулятора).
        Чистые матчи вскрывают юнит, который проигрывает/выигрывает у всех, что размыто в смешанных составах."""
        stats = run_batch(balance, n_matches, seed)
        stats["pure_n"] = PURE_N
        stats["matchups"] = {f"{a}>{b}": run_matchup(balance, a, b, PURE_N, seed)
                             for a, b in itertools.combinations(UNIT_TYPES, 2)}
        return stats
