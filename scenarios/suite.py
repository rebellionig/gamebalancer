"""Набор тестовых сценариев системы. Каждый сценарий: стартовые условия -> ожидаемый результат -> автоматическая проверка.

Запуск:  python run_scenarios.py        (таблица PASS/FAIL)
         pytest tests/test_scenarios.py (то же самое под pytest)

Без сети и ключей: LLM заменяется заглушкой, всё детерминировано по seed.
Сценарии с kind="limitation" фиксируют ИЗВЕСТНОЕ ограничение системы: проверка подтверждает, что оно воспроизводится.
"""
from __future__ import annotations

import copy
import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from agents.analyst import Analyst
from agents.critic import Critic
from agents.designer import Designer
from agents.orchestrator import Orchestrator
from agents.simulator import Simulator
from game import balance as bal
from messages import Change, ChangeProposal, CritiqueReport
from store import Store

ROOT = Path(__file__).resolve().parent.parent
BASE = bal.load(ROOT / "balance.json")
N_MATCHES, SEED = 1000, 42


def variant(**changes) -> dict:
    """balance.json с заменёнными параметрами: variant(archer__atk=6) -> archer.atk = 6."""
    b = copy.deepcopy(BASE)
    for key, value in changes.items():
        unit, param = key.split("__")
        b[unit][param] = value
    return b


class NoLLM:
    configured = False


class GarbageLLM:
    """LLM, которая всегда отвечает не-JSON."""
    configured = True

    def __init__(self):
        self.calls = 0

    def chat(self, messages, temperature=0.2):
        self.calls += 1
        return "это не json"


class ScriptedDesigner:
    """Дизайнер, предлагающий правки по заранее заданному сценарию. Запоминает замечания Критика."""

    def __init__(self, fn):
        self.fn, self.seen = fn, []

    def propose(self, iteration, balance, report, critique=None):
        self.seen.append(critique)
        changes = [Change(unit=u, param=p, **{"from": balance[u][p]}, to=to) for u, p, to in self.fn(iteration, balance, report)]
        return ChangeProposal(iteration=iteration, rationale="scripted", changes=changes)


class ApprovingCritic:
    """Критик-пропускалка: нужен, чтобы проверять оркестратор отдельно от Критика."""

    def review(self, proposal, balance, report):
        return CritiqueReport(iteration=proposal.iteration, approved=True)


def execute(balance: dict, designer=None, critic=None, max_iters: int = 10):
    """Полный прогон оркестратора во временной БД. Возвращает (out, history, designer)."""
    designer = designer or Designer(NoLLM())
    with tempfile.TemporaryDirectory() as tmp:
        store = Store(Path(tmp) / "s.db")
        orch = Orchestrator(designer, critic or Critic(), Simulator(), Analyst(), store,
                            max_iters=max_iters, n_matches=N_MATCHES, seed=SEED)
        out = orch.run(balance)
        history = store.history(out["run_id"])
        store.db.close()
    return out, history, designer


def net_changes(start: dict, final: dict) -> dict:
    return {f"{u}.{p}": (start[u][p], final[u][p]) for u in start for p in start[u] if start[u][p] != final[u][p]}


def issue_codes(designer: ScriptedDesigner) -> set[str]:
    return {i.code for c in designer.seen if c is not None for i in c.issues}


# --------------------------------------------------------------------------- сценарии
@dataclass
class Scenario:
    id: str
    title: str
    expected: str
    run: Callable[[], tuple[bool, str]]
    kind: str = "normal"       # "normal" | "limitation"


def s_balanced():
    out, hist, _ = execute(variant())
    ok = out["stop_reason"] == "converged" and len(hist) == 1 and not net_changes(BASE, out["final_balance"])
    return ok, f"stop={out['stop_reason']}, итераций={len(hist)}, изменения={net_changes(BASE, out['final_balance'])}"


def _fixes_only(start: dict, unit: str, param: str, max_iters_expected: int):
    out, hist, _ = execute(start)
    net = net_changes(start, out["final_balance"])
    lo = out["final_balance"][unit][param] < start[unit][param]
    ok = out["stop_reason"] == "converged" and lo and list(net) == [f"{unit}.{param}"] and len(hist) <= max_iters_expected
    return ok, f"stop={out['stop_reason']}, итераций={len(hist)}, изменения={net}"


def s_archer_op():
    return _fixes_only(variant(archer__atk=6, archer__hp=7), "archer", "atk", 6)


def s_archer_mild():
    return _fixes_only(variant(archer__atk=5), "archer", "atk", 6)


def s_mage_op():
    return _fixes_only(variant(mage__atk=7), "mage", "atk", 6)


def s_llm_garbage():
    llm = GarbageLLM()
    out, hist, _ = execute(variant(archer__atk=6, archer__hp=7), designer=Designer(llm))
    ok = out["stop_reason"] == "converged" and llm.calls > 0 and out["final_balance"]["archer"]["atk"] < 6
    return ok, f"stop={out['stop_reason']}, вызовов LLM={llm.calls}, archer.atk={out['final_balance']['archer']['atk']}"


def s_critic_big_step():
    d = ScriptedDesigner(lambda i, b, r: [("archer", "atk", 8)])           # шаг 3 -> 8
    out, hist, d = execute(variant(), designer=d, max_iters=2)
    ok = (out["skipped"] == [1, 2] and not hist and "step_too_large" in issue_codes(d)
          and out["final_balance"] == BASE)
    return ok, f"пропущено={out['skipped']}, замечания={sorted(issue_codes(d))}, симуляций={len(hist)}"


def s_critic_wrong_direction():
    # 1-я итерация без изменений, дальше пытаемся УСИЛИТЬ уже слишком сильного лучника
    def fn(i, b, r):
        return [("archer", "atk", b["archer"]["atk"] + (0 if i == 1 else 1))]
    start = variant(archer__atk=6, archer__hp=7)
    out, hist, d = execute(start, designer=ScriptedDesigner(fn), max_iters=3)
    ok = (len(hist) == 1 and out["skipped"] == [2, 3] and "wrong_direction" in issue_codes(d)
          and out["final_balance"] == start)
    return ok, f"симуляций={len(hist)}, пропущено={out['skipped']}, замечания={sorted(issue_codes(d))}"


def s_critic_exploit():
    d = ScriptedDesigner(lambda i, b, r: [("archer", "atk", 5)])           # шаг 2 допустим, но создаёт жёсткую контру
    out, hist, d = execute(variant(), designer=d, max_iters=1)
    ok = out["skipped"] == [1] and "exploit_worse" in issue_codes(d) and out["final_balance"] == BASE
    return ok, f"пропущено={out['skipped']}, замечания={sorted(issue_codes(d))}"


def s_cycle():
    # баланс бегает между двумя сломанными состояниями; Критик отключён, чтобы проверить именно оркестратор
    d = ScriptedDesigner(lambda i, b, r: [("archer", "atk", 7 if b["archer"]["atk"] == 6 else 6)])
    out, hist, _ = execute(variant(archer__atk=6, archer__hp=7), designer=d, critic=ApprovingCritic(), max_iters=8)
    ok = out["stop_reason"] == "cycle" and len(hist) == 3
    return ok, f"stop={out['stop_reason']}, итераций={len(hist)} из 8"


def s_iter_limit():
    out, hist, _ = execute(variant(archer__atk=6, archer__hp=7), max_iters=2)
    ok = out["stop_reason"] == "max_iters" and len(hist) == 2 and not out["report"].balanced
    return ok, f"stop={out['stop_reason']}, итераций={len(hist)}, balanced={out['report'].balanced}"


def s_weak_unit_found():
    # воин почти без урона: в смешанных составах это размыто, но чистые матчи (0% против всех) его вскрывают
    start = variant(warrior__atk=1)
    out, hist, _ = execute(start)
    net = net_changes(start, out["final_balance"])
    ok = (out["stop_reason"] == "converged" and list(net) == ["warrior.atk"]
          and out["final_balance"]["warrior"]["atk"] > 1 and len(hist) <= 6)
    return ok, f"stop={out['stop_reason']}, итераций={len(hist)}, изменения={net}"


def s_strong_mage_hp():
    # маг с hp 8: «жирный» маг незаметен по командному винрейту, но доминирует в чистых матчах
    start = variant(mage__hp=8)
    out, hist, _ = execute(start)
    net = net_changes(start, out["final_balance"])
    ok = out["stop_reason"] == "converged" and set(net) == {"mage.atk"} and out["final_balance"]["mage"]["atk"] < 4
    return ok, f"stop={out['stop_reason']}, итераций={len(hist)}, изменения={net}"


SCENARIOS: list[Scenario] = [
    Scenario("balanced_start", "Сбалансированный старт",
             "converged на 1-й итерации, баланс не меняется", s_balanced),
    Scenario("archer_overpowered", "Лучник слишком силён (atk 6, hp 7)",
             "converged ≤6 итераций, меняется только archer.atk (вниз)", s_archer_op),
    Scenario("archer_mild", "Лучник немного силён (atk 5)",
             "converged ≤6 итераций, меняется только archer.atk (вниз)", s_archer_mild),
    Scenario("mage_overpowered", "Маг слишком силён (atk 7)",
             "converged ≤6 итераций, меняется только mage.atk (вниз)", s_mage_op),
    Scenario("llm_returns_garbage", "LLM отвечает не-JSON",
             "Дизайнер переходит на запасное правило, система всё равно сходится", s_llm_garbage),
    Scenario("critic_rejects_big_step", "Дизайнер предлагает шаг 3→8",
             "Критик отклоняет (step_too_large), итерации пропущены, симуляций нет", s_critic_big_step),
    Scenario("critic_rejects_wrong_direction", "Дизайнер усиливает уже сильного лучника",
             "Критик отклоняет (wrong_direction), баланс не меняется", s_critic_wrong_direction),
    Scenario("critic_blocks_new_exploit", "Правка создаёт жёсткую контру",
             "Критик отклоняет (exploit_worse) по пробным матчам", s_critic_exploit),
    Scenario("cycle_detected", "Баланс ходит между двумя сломанными состояниями",
             "stop=cycle на 3-й итерации, а не 8 итераций впустую", s_cycle),
    Scenario("iteration_limit", "Лимит итераций меньше, чем нужно для сходимости",
             "stop=max_iters, ровно 2 итерации, баланс ещё не достигнут", s_iter_limit),
    Scenario("weak_unit_detected", "Воин почти без урона (atk 1): слепое пятно командной метрики",
             "чистые матчи вскрывают воина, converged, меняется только warrior.atk (вверх)", s_weak_unit_found),
    Scenario("strong_mage_hp", "Маг с hp 8 (доминирует в чистых матчах)",
             "converged, меняется только mage.atk (вниз)", s_strong_mage_hp),
]
