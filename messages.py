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
