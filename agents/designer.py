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
from messages import AnalysisReport, Change, ChangeProposal, CritiqueReport

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

    def propose(self, iteration: int, balance: dict, report: AnalysisReport | None,
                critique: CritiqueReport | None = None) -> ChangeProposal:
        proposal, source = None, "rule"
        if self.llm.configured:
            try:
                proposal, source = self._ask_llm(iteration, balance, report, critique), "llm"
            except (LLMError, ValueError) as e:
                log_event(NAME, "agent", "llm_fallback", {"iteration": iteration}, None, ok=False, error=str(e))
        if proposal is None:
            proposal = self._rule(iteration, balance, report)
        log_event(NAME, "agent", "propose", {"iteration": iteration, "source": source},
                  proposal.model_dump(by_alias=True))
        return proposal

    # ---- LLM-путь ----
    def _ask_llm(self, iteration: int, balance: dict, report: AnalysisReport | None,
                 critique: CritiqueReport | None) -> ChangeProposal:
        user = {"current_balance": balance,
                "analysis": report.model_dump(exclude={"type"}) if report else "нет, это первая итерация"}
        if critique is not None and not critique.approved:
            # предыдущая попытка отклонена Критиком: даём модели его замечания
            user["previous_attempt_rejected"] = [i.model_dump() for i in critique.issues]
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
    def _rule(self, iteration: int, balance: dict, report: AnalysisReport | None) -> ChangeProposal:
        """Одна правка за итерацию, только по реально сломанному юниту (шум игнорируем)."""
        worst = next((f for f in report.findings if f.metric == report.worst), None) if report else None
        if worst is None:
            a = balance["archer"]["atk"]
            return ChangeProposal(iteration=iteration, rationale="Базовый прогон без изменений.",
                                  changes=[Change(unit="archer", param="atk", **{"from": a}, to=a)])
        unit = worst.metric.split(":", 1)[1]
        atk = balance[unit]["atk"]
        to = max(1, atk - 1) if worst.verdict == "overpowered" else min(10, atk + 1)
        return ChangeProposal(
            iteration=iteration,
            rationale=f"[rule] {unit} {worst.verdict}: {worst.winrate:.0%} (z={worst.z})",
            changes=[Change(unit=unit, param="atk", **{"from": atk}, to=to)],
        )
