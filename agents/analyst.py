"""Агент-Аналитик. Единственная роль: отличить РЕАЛЬНЫЙ дисбаланс от шума симуляции.

Винрейт из n матчей имеет стандартную ошибку SE = sqrt(0.25 / n) (при истинных 50%).
Для n=500 это ~2.2%, поэтому 52% против 48% - это шум, а не повод менять баланс.
Юнит считается "сломанным" (off) только если ОБА условия выполнены:
  1) |winrate - 0.5| > TOL          (отклонение достаточно большое по существу)
  2) |z| = |winrate - 0.5| / SE >= Z_MIN   (и достаточно велико по сравнению с шумом)
LLM не используется: это чистые вычисления, их результат можно проверить руками.
"""
from __future__ import annotations

import math

from logger import logged
from messages import AnalysisReport, Finding, SimResult

NAME = "analyst"
TOL = 0.05    # допустимое отклонение от 50% (диапазон 45-55%)
Z_MIN = 2.0   # ~95% уверенность, что отклонение не шум
SIDE_TOL = 0.05
PURE_TOL = 0.20   # средний винрейт юнита в чистых матчах: допуск шире (составы нереалистичны), но 0%/100% ловятся
PURE_Z_MIN = 3.0


class Analyst:
    @logged(NAME, "tool", "stats.analyze")
    def analyze(self, result: SimResult) -> AnalysisReport:
        # SE считаем по n_matches: для юнита это консервативная оценка (его выборка не меньше)
        se = math.sqrt(0.25 / result.n_matches)
        findings: list[Finding] = []
        for unit, wr in result.unit_winrate.items():
            dev = wr - 0.5
            z = dev / se
            off = abs(dev) > TOL and abs(z) >= Z_MIN
            verdict = ("overpowered" if dev > 0 else "underpowered") if off else "ok"
            findings.append(Finding(metric=f"unit:{unit}", winrate=wr, deviation=round(dev, 4),
                                    z=round(z, 2), verdict=verdict))

        # второй взгляд: чистые матчи. Находит юнит, чей эффект тонет в смешанных составах (напр. воин с atk 1)
        # только если командные метрики чисты: иначе чистые матчи показывают следствия того же перекоса (лучник
        # давит всех -> «слабым» выглядит воин), и Дизайнер начал бы лечить следствие вместо причины
        team_off = any(f.verdict != "ok" for f in findings)
        for unit, wr, n in ([] if team_off else self._pure_winrates(result)):
            dev = wr - 0.5
            z = dev / math.sqrt(0.25 / n)
            if abs(dev) > PURE_TOL and abs(z) >= PURE_Z_MIN:
                findings.append(Finding(metric=f"pure:{unit}", winrate=round(wr, 4), deviation=round(dev, 4),
                                        z=round(z, 2), verdict="overpowered" if dev > 0 else "underpowered"))

        off_findings = [f for f in findings if f.verdict != "ok"]
        worst = max(off_findings, key=lambda f: abs(f.z)).metric if off_findings else None

        side_a = result.side_winrate.get("A", 0.5)
        side_warning = None
        if abs(side_a - 0.5) > SIDE_TOL and abs(side_a - 0.5) / se >= Z_MIN:
            side_warning = (f"Перекос сторон: A выигрывает {side_a:.0%}. "
                            "Параметрами юнитов это не исправить - проверь правила (порядок хода, расстановка).")

        return AnalysisReport(iteration=result.iteration, n_matches=result.n_matches,
                              balanced=not off_findings, findings=findings,
                              worst=worst, side_warning=side_warning)

    @staticmethod
    def _pure_winrates(result: SimResult):
        """(юнит, средний винрейт против двух других типов, число матчей). Пусто, если матрицы нет."""
        wins: dict[str, list[float]] = {}
        for pair, v in result.matchups.items():
            a, b = pair.split(">")
            wins.setdefault(a, []).append(v)
            wins.setdefault(b, []).append(1 - v)
        return [(u, sum(v) / len(v), result.pure_n * len(v)) for u, v in wins.items()]
