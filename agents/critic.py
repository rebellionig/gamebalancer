"""Агент-Критик. Единственная роль: независимо проверить правку Дизайнера ДО симуляции.

Проверки (все детерминированные, результат можно перепроверить руками):
  1. invalid_change   - значение вне допустимых границ (ловится game.balance.apply_changes)
  2. from_mismatch    - поле `from` не совпадает с реальным балансом (признак галлюцинации LLM)
  3. step_too_large   - |to - from| > MAX_STEP: за итерацию меняем понемногу
  4. wrong_direction  - усиливаем юнит, которого Аналитик признал сильным (и наоборот)
  5. exploit_worse    - пробные матчи «команда из одних юнитов против другой» показывают, что правка
                        создаёт или усиливает жёсткую контру (>=90% побед) по сравнению с текущим балансом

Важно: проверка 5 сравнивает с ТЕКУЩИМ балансом. Если баланс уже сломан, правка, которая его не ухудшает,
проходит - иначе Критик заблокировал бы само исправление.
"""
from __future__ import annotations

import itertools

from game import balance as bal
from game.engine import UNIT_TYPES, run_matchup
from logger import log_event, logged
from messages import AnalysisReport, ChangeProposal, CritiqueReport, Issue

NAME = "critic"
MAX_STEP = 2
PROBE_N = 100        # матчей на каждую пару (SE ~5%)
EXTREME = 0.40       # |winrate - 0.5| >= 0.40, то есть 90%+ побед или 10%- = жёсткая контра
WORSE_BY = 0.05      # насколько правка должна ухудшить худшую пару, чтобы считаться ухудшением


class Critic:
    def review(self, proposal: ChangeProposal, balance: dict,
               report: AnalysisReport | None) -> CritiqueReport:
        issues: list[Issue] = []
        changes = [{"unit": c.unit, "param": c.param, "to": c.to} for c in proposal.changes]

        for c in proposal.changes:
            actual = balance[c.unit][c.param]
            if c.from_ != actual:
                issues.append(Issue(code="from_mismatch",
                                    message=f"{c.unit}.{c.param}: в правке from={c.from_}, а в балансе {actual}"))
            if abs(c.to - actual) > MAX_STEP:
                issues.append(Issue(code="step_too_large",
                                    message=f"{c.unit}.{c.param} {actual}->{c.to}: шаг {abs(c.to - actual)} > {MAX_STEP}"))
            if report is not None:
                verdict = next((f.verdict for f in report.findings if f.metric == f"unit:{c.unit}"), "ok")
                # для всех четырёх параметров больше = сильнее
                if verdict == "overpowered" and c.to > actual:
                    issues.append(Issue(code="wrong_direction",
                                        message=f"{c.unit} признан сильным, а {c.param} растёт {actual}->{c.to}"))
                if verdict == "underpowered" and c.to < actual:
                    issues.append(Issue(code="wrong_direction",
                                        message=f"{c.unit} признан слабым, а {c.param} падает {actual}->{c.to}"))

        probe: dict[str, float] = {}
        try:
            proposed = bal.apply_changes(balance, changes)
        except bal.BalanceError as e:
            issues.append(Issue(code="invalid_change", message=str(e)))
        else:
            # пробные матчи нужны только если правка вообще что-то меняет
            if any(c["to"] != balance[c["unit"]][c["param"]] for c in changes):
                before, probe = self._probe(balance, proposed, proposal.iteration)
                worst_before = max(abs(v - 0.5) for v in before.values())
                worst_after = max(abs(v - 0.5) for v in probe.values())
                if worst_after >= EXTREME and worst_after > worst_before + WORSE_BY:
                    pair = max(probe, key=lambda k: abs(probe[k] - 0.5))
                    issues.append(Issue(code="exploit_worse",
                                        message=f"правка создаёт жёсткую контру {pair}={probe[pair]:.0%} "
                                                f"(было не хуже {0.5 + worst_before:.0%})"))

        result = CritiqueReport(iteration=proposal.iteration, approved=not issues, issues=issues, probe=probe)
        log_event(NAME, "agent", "review", proposal.model_dump(by_alias=True), result.model_dump(),
                  ok=result.approved, error=None if result.approved else "; ".join(i.code for i in issues))
        return result

    @logged(NAME, "tool", "exploit_probe")
    def _probe(self, before: dict, after: dict, iteration: int) -> tuple[dict, dict]:
        """Один вызов инструмента = пробные матчи для баланса ДО и ПОСЛЕ правки."""
        def matrix(b: dict) -> dict[str, float]:
            return {f"{a}>{c}": run_matchup(b, a, c, PROBE_N, seed=1000 + iteration)
                    for a, c in itertools.combinations(UNIT_TYPES, 2)}
        return matrix(before), matrix(after)
