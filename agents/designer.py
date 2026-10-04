"""Агент-Дизайнер: предлагает правку баланса.

Основной путь: LLM возвращает JSON -> проверяем схемой ChangeProposal -> при ошибке просим исправить.
Запасной путь: если LLM не настроен или недоступен, работает простое правило (система не падает).
"""
from __future__ import annotations

import json

from pydantic import ValidationError

from agents.llm import LLMClient, LLMError
from game.balance import LIMITS
from logger import log_event
from messages import Change, ChangeProposal, SimResult

NAME = "designer"
MAX_FIX_ATTEMPTS = 2  # сколько раз просим LLM исправить невалидный JSON

SYSTEM_PROMPT = f"""Ты - дизайнер баланса тактической игры 5x5. Три юнита: warrior, archer, mage.
У каждого параметры hp, atk, move, range (целые числа). Допустимые диапазоны: {json.dumps(LIMITS)}.
Цель: винрейт каждой стороны и каждого юнита в диапазоне 45-55%.
Меняй минимум параметров: 1-3 правки за итерацию, небольшими шагами (обычно +-1).
Отвечай ТОЛЬКО JSON такого вида:
{{"changes": [{{"unit": "archer", "param": "atk", "from": 3, "to": 2}}], "rationale": "кратко почему"}}"""


class Designer:
    def __init__(self, llm: LLMClient | None = None):
        self.llm = llm or LLMClient(NAME)

    def propose(self, iteration: int, balance: dict, prev: SimResult | None) -> ChangeProposal:
        proposal, source = None, "rule"
        if self.llm.configured:
            try:
                proposal, source = self._ask_llm(iteration, balance, prev), "llm"
            except (LLMError, ValueError) as e:
                log_event(NAME, "agent", "llm_fallback", {"iteration": iteration}, None, ok=False, error=str(e))
        if proposal is None:
            proposal = self._rule(iteration, balance, prev)
        log_event(NAME, "agent", "propose", {"iteration": iteration, "source": source},
                  proposal.model_dump(by_alias=True))
        return proposal

    # ---- LLM-путь ----
    def _ask_llm(self, iteration: int, balance: dict, prev: SimResult | None) -> ChangeProposal:
        user = {"current_balance": balance,
                "last_stats": prev.model_dump(exclude={"type"}) if prev else "нет, это первая итерация"}
        messages = [{"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps(user, ensure_ascii=False)}]
        last_err = ""
        for _ in range(MAX_FIX_ATTEMPTS + 1):
            raw = self.llm.chat(messages)
            try:
                data = json.loads(raw)
                return ChangeProposal(iteration=iteration, **data)
            except (json.JSONDecodeError, ValidationError, TypeError) as e:
                last_err = str(e)[:300]
                # обратная связь: показываем модели её ответ и ошибку
                messages += [{"role": "assistant", "content": raw},
                             {"role": "user", "content": f"Ответ невалиден: {last_err}. Исправь и верни только JSON."}]
        raise ValueError(f"LLM не дала валидный JSON за {MAX_FIX_ATTEMPTS + 1} попытки: {last_err}")

    # ---- запасное правило ----
    def _rule(self, iteration: int, balance: dict, prev: SimResult | None) -> ChangeProposal:
        if prev is None:
            a = balance["archer"]["atk"]
            return ChangeProposal(iteration=iteration, rationale="Базовый прогон без изменений.",
                                  changes=[Change(unit="archer", param="atk", **{"from": a}, to=a)])
        strongest = max(prev.unit_winrate, key=prev.unit_winrate.get)
        weakest = min(prev.unit_winrate, key=prev.unit_winrate.get)
        s, w = balance[strongest]["atk"], balance[weakest]["atk"]
        return ChangeProposal(
            iteration=iteration,
            rationale=f"[rule] {strongest} {prev.unit_winrate[strongest]:.0%}, {weakest} {prev.unit_winrate[weakest]:.0%}",
            changes=[Change(unit=strongest, param="atk", **{"from": s}, to=max(1, s - 1)),
                     Change(unit=weakest, param="atk", **{"from": w}, to=min(10, w + 1))],
        )
