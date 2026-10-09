"""Типизированные сообщения между агентами (pydantic). Любое сообщение проверяется на входе."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Unit = Literal["warrior", "archer", "mage"]
Param = Literal["hp", "atk", "move", "range"]


class Change(BaseModel):
    unit: Unit
    param: Param
    from_: int = Field(alias="from")
    to: int

    model_config = {"populate_by_name": True}


class ChangeProposal(BaseModel):
    type: Literal["ChangeProposal"] = "ChangeProposal"
    iteration: int
    changes: list[Change] = Field(min_length=1, max_length=3)  # не больше 3 правок за итерацию
    rationale: str


class SimResult(BaseModel):
    type: Literal["SimResult"] = "SimResult"
    iteration: int
    balance_hash: str
    n_matches: int
    side_winrate: dict[str, float]
    draw_rate: float
    unit_winrate: dict[str, float]
    avg_turns: float


class Finding(BaseModel):
    metric: str                                    # например "unit:archer"
    winrate: float
    deviation: float                               # winrate - 0.5
    z: float                                       # отклонение в единицах стандартной ошибки
    verdict: Literal["overpowered", "underpowered", "ok"]


class AnalysisReport(BaseModel):
    type: Literal["AnalysisReport"] = "AnalysisReport"
    iteration: int
    n_matches: int
    balanced: bool                                 # нет ни одного юнита с реальным (не шумовым) дисбалансом
    findings: list[Finding]
    worst: str | None = None                       # метрика с наибольшим |z| среди нарушающих
    side_warning: str | None = None                # перекос сторон: параметрами юнитов не лечится


class Issue(BaseModel):
    code: Literal["invalid_change", "from_mismatch", "step_too_large", "wrong_direction", "exploit_worse"]
    message: str


class CritiqueReport(BaseModel):
    type: Literal["CritiqueReport"] = "CritiqueReport"
    iteration: int
    approved: bool
    issues: list[Issue] = []
    probe: dict[str, float] = {}      # матрица «чистых» матчей для ПРЕДЛОЖЕННОГО баланса, например "warrior>archer": 0.74
