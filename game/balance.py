"""Загрузка и безопасное применение правок баланса.

Это защитный слой: что бы ни предложил LLM, в движок попадёт только валидный баланс.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from .engine import UNIT_TYPES

PARAMS = ("hp", "atk", "move", "range")
LIMITS = {"hp": (1, 30), "atk": (1, 10), "move": (1, 3), "range": (1, 4)}


class BalanceError(ValueError):
    pass


def load(path: str | Path = "balance.json") -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def digest(balance: dict) -> str:
    return hashlib.sha256(json.dumps(balance, sort_keys=True).encode()).hexdigest()[:10]


def apply_changes(balance: dict, changes: list[dict]) -> dict:
    """Возвращает НОВЫЙ баланс (исходный не меняется). Бросает BalanceError при невалидной правке."""
    new = copy.deepcopy(balance)
    for ch in changes:
        unit, param, value = ch["unit"], ch["param"], ch["to"]
        if unit not in UNIT_TYPES:
            raise BalanceError(f"неизвестный юнит: {unit}")
        if param not in PARAMS:
            raise BalanceError(f"неизвестный параметр: {param}")
        lo, hi = LIMITS[param]
        if not isinstance(value, int) or not lo <= value <= hi:
            raise BalanceError(f"{unit}.{param}={value} вне диапазона [{lo}, {hi}]")
        new[unit][param] = value
    return new
