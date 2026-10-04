"""Детерминированный движок тактической игры 5x5.

Весь случайный выбор идёт через random.Random(seed), поэтому один и тот же
seed + balance всегда даёт один и тот же результат (важно для тестов и логов).
"""
from __future__ import annotations

import random
from dataclasses import dataclass

SIZE = 5
MAX_TURNS = 30
UNIT_TYPES = ("warrior", "archer", "mage")
BOTS = ("random", "greedy", "focus")


@dataclass
class Unit:
    kind: str
    side: str          # "A" или "B"
    hp: int
    atk: int
    move: int
    range: int
    x: int
    y: int

    @property
    def alive(self) -> bool:
        return self.hp > 0


def dist(a: Unit, b: Unit) -> int:
    """Манхэттенское расстояние."""
    return abs(a.x - b.x) + abs(a.y - b.y)


def _spawn(side: str, comp: list[str], balance: dict) -> list[Unit]:
    x = 0 if side == "A" else SIZE - 1
    rows = [1, 2, 3]  # три юнита в центре своей колонки
    return [Unit(kind, side, x=x, y=y, **balance[kind]) for kind, y in zip(comp, rows)]


def _reachable(unit: Unit, units: list[Unit]) -> list[tuple[int, int]]:
    """Клетки, куда юнит дойдёт за `move` шагов (BFS, чужие юниты блокируют)."""
    occupied = {(u.x, u.y) for u in units if u.alive and u is not unit}
    seen = {(unit.x, unit.y)}
    frontier = [(unit.x, unit.y)]
    for _ in range(unit.move):
        nxt = []
        for cx, cy in frontier:
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = cx + dx, cy + dy
                if 0 <= nx < SIZE and 0 <= ny < SIZE and (nx, ny) not in occupied and (nx, ny) not in seen:
                    seen.add((nx, ny))
                    nxt.append((nx, ny))
        frontier = nxt
    return sorted(seen)  # sorted -> детерминированный порядок


def _targets_from(unit: Unit, pos: tuple[int, int], enemies: list[Unit]) -> list[Unit]:
    return [e for e in enemies if abs(e.x - pos[0]) + abs(e.y - pos[1]) <= unit.range]


def _act(unit: Unit, units: list[Unit], bot: str, rng: random.Random) -> None:
    enemies = [u for u in units if u.alive and u.side != unit.side]
    if not enemies:
        return
    cells = _reachable(unit, units)

    if bot == "random":
        unit.x, unit.y = rng.choice(cells)
        tg = _targets_from(unit, (unit.x, unit.y), enemies)
        target = rng.choice(tg) if tg else None
    else:
        # cells, из которых можно кого-то ударить
        attack_cells = [c for c in cells if _targets_from(unit, c, enemies)]
        if attack_cells:
            # встаём как можно дальше от врагов (стрелки/маги держат дистанцию)
            def min_d(c):
                return min(abs(e.x - c[0]) + abs(e.y - c[1]) for e in enemies)
            unit.x, unit.y = max(attack_cells, key=lambda c: (min_d(c), c))
            tg = _targets_from(unit, (unit.x, unit.y), enemies)
            if bot == "focus":
                target = min(tg, key=lambda e: (e.hp, e.x, e.y))
            else:  # greedy: ближайший
                target = min(tg, key=lambda e: (dist(unit, e), e.x, e.y))
        else:
            nearest = min(enemies, key=lambda e: (dist(unit, e), e.x, e.y))
            unit.x, unit.y = min(cells, key=lambda c: (abs(nearest.x - c[0]) + abs(nearest.y - c[1]), c))
            target = None

    if target is not None:
        target.hp -= unit.atk
        if unit.kind == "mage":  # splash: половина урона по соседям цели
            for e in enemies:
                if e is not target and e.alive and abs(e.x - target.x) + abs(e.y - target.y) == 1:
                    e.hp -= unit.atk // 2


def play_match(balance: dict, comp_a: list[str], comp_b: list[str],
               bot_a: str, bot_b: str, rng: random.Random) -> dict:
    units = _spawn("A", comp_a, balance) + _spawn("B", comp_b, balance)
    for turn in range(1, MAX_TURNS + 1):
        for side, bot in (("A", bot_a), ("B", bot_b)):
            for u in [u for u in units if u.side == side and u.alive]:
                if u.alive:
                    _act(u, units, bot, rng)
            alive_a = any(u.alive for u in units if u.side == "A")
            alive_b = any(u.alive for u in units if u.side == "B")
            if not alive_a or not alive_b:
                return {"winner": "A" if alive_a else "B", "turns": turn}
    # по таймауту побеждает тот, у кого больше суммарного HP
    hp_a = sum(max(u.hp, 0) for u in units if u.side == "A")
    hp_b = sum(max(u.hp, 0) for u in units if u.side == "B")
    winner = "A" if hp_a > hp_b else "B" if hp_b > hp_a else "draw"
    return {"winner": winner, "turns": MAX_TURNS}


def run_batch(balance: dict, n_matches: int, seed: int) -> dict:
    """Один батч матчей -> агрегированная статистика (это и есть один вызов Симулятора)."""
    rng = random.Random(seed)
    wins = {"A": 0, "B": 0, "draw": 0}
    turns_total = 0
    unit_games = {k: 0 for k in UNIT_TYPES}   # в скольких матчах юнит участвовал
    unit_wins = {k: 0 for k in UNIT_TYPES}    # в скольких из них его сторона выиграла
    for _ in range(n_matches):
        comp_a = [rng.choice(UNIT_TYPES) for _ in range(3)]
        comp_b = [rng.choice(UNIT_TYPES) for _ in range(3)]
        bot_a, bot_b = rng.choice(BOTS), rng.choice(BOTS)
        res = play_match(balance, comp_a, comp_b, bot_a, bot_b, rng)
        wins[res["winner"]] += 1
        turns_total += res["turns"]
        for side, comp in (("A", comp_a), ("B", comp_b)):
            for kind in set(comp):
                unit_games[kind] += 1
                if res["winner"] == side:
                    unit_wins[kind] += 1
    decided = max(wins["A"] + wins["B"], 1)
    return {
        "n_matches": n_matches,
        "side_winrate": {"A": round(wins["A"] / decided, 4), "B": round(wins["B"] / decided, 4)},
        "draw_rate": round(wins["draw"] / n_matches, 4),
        "unit_winrate": {k: round(unit_wins[k] / max(unit_games[k], 1), 4) for k in UNIT_TYPES},
        "avg_turns": round(turns_total / n_matches, 2),
    }
