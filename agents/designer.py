"""Агент-Дизайнер: предлагает правку баланса.

СЕЙЧАС: правило вместо LLM (нерфим самый сильный юнит, бафаем самый слабый).
TODO (тебе): заменить `_decide` на вызов LLM, который возвращает JSON ChangeProposal.
Интерфейс `propose` менять не нужно - остальная система не заметит замены.
"""
from __future__ import annotations

from logger import log_event
from messages import Change, ChangeProposal, SimResult

NAME = "designer"


class Designer:
    def propose(self, iteration: int, balance: dict, prev: SimResult | None) -> ChangeProposal:
        proposal = self._decide(iteration, balance, prev)
        log_event(NAME, "agent", "propose", {"iteration": iteration,
                  "prev_unit_winrate": prev.unit_winrate if prev else None}, proposal.model_dump(by_alias=True))
        return proposal

    def _decide(self, iteration: int, balance: dict, prev: SimResult | None) -> ChangeProposal:
        if prev is None:
            # первая итерация: нет статистики, ничего не меняем осмысленно -> пробная правка
            return ChangeProposal(
                iteration=iteration,
                changes=[Change(unit="archer", param="atk", **{"from": balance["archer"]["atk"]},
                                to=balance["archer"]["atk"])],
                rationale="Базовый прогон без изменений: снимаем стартовую статистику.",
            )
        strongest = max(prev.unit_winrate, key=prev.unit_winrate.get)
        weakest = min(prev.unit_winrate, key=prev.unit_winrate.get)
        s_atk, w_atk = balance[strongest]["atk"], balance[weakest]["atk"]
        return ChangeProposal(
            iteration=iteration,
            changes=[
                Change(unit=strongest, param="atk", **{"from": s_atk}, to=max(1, s_atk - 1)),
                Change(unit=weakest, param="atk", **{"from": w_atk}, to=min(10, w_atk + 1)),
            ],
            rationale=f"{strongest} выигрывает {prev.unit_winrate[strongest]:.0%}, "
                      f"{weakest} только {prev.unit_winrate[weakest]:.0%}: сближаем.",
        )
