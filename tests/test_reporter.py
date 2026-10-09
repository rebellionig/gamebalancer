"""Репортёр + интеграционный прогон всех 6 агентов (без сети: LLM заменена заглушкой)."""
import json

from agents.analyst import Analyst
from agents.critic import Critic
from agents.designer import Designer
from agents.orchestrator import Orchestrator
from agents.reporter import Reporter
from agents.simulator import Simulator
from game import balance as bal
from store import Store

BROKEN = bal.load("scenarios/archer_op.json")


class NoLLM:
    configured = False


class FakeLLM:
    configured = True

    def __init__(self, reply):
        self.reply, self.calls = reply, 0

    def chat(self, messages, temperature=0.2):
        self.calls += 1
        return self.reply


def run(tmp_path, reporter_llm):
    store = Store(tmp_path / "s.db")
    orch = Orchestrator(Designer(NoLLM()), Critic(), Simulator(), Analyst(), store, max_iters=6,
                        n_matches=300, seed=42, reporter=Reporter(reporter_llm, out_dir=tmp_path / "reports"))
    return orch.run(BROKEN)


def test_report_written_with_template_summary(tmp_path):
    out = run(tmp_path, NoLLM())
    text = out["report_path"].read_text(encoding="utf-8")
    assert out["run_id"] in text
    assert "| Юнит | Параметр | Было | Стало |" in text      # таблица изменений
    assert "## Ход итераций" in text and "собрано по шаблону" in text
    assert "archer" in text                                    # лучник был сломан и правился


def test_llm_summary_goes_only_under_conclusions(tmp_path):
    llm = FakeLLM(json.dumps({"summary": "Лучник был слишком сильным, его ослабили."}))
    out = run(tmp_path, llm)
    text = out["report_path"].read_text(encoding="utf-8")
    assert llm.calls == 1
    head, _, tail = text.partition("## Выводы")
    assert "Лучник был слишком сильным" in tail and "Лучник был слишком сильным" not in head
    assert "сгенерировано LLM" in tail


def test_garbage_llm_falls_back_to_template(tmp_path):
    out = run(tmp_path, FakeLLM("это не json"))
    assert "собрано по шаблону" in out["report_path"].read_text(encoding="utf-8")


def test_overlong_llm_summary_rejected(tmp_path):
    out = run(tmp_path, FakeLLM(json.dumps({"summary": "x" * 5000})))
    assert "собрано по шаблону" in out["report_path"].read_text(encoding="utf-8")


def test_all_agents_logged_and_final_balance_fixed(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)   # лог пишется в logs/run.jsonl относительно cwd
    import shutil, pathlib
    shutil.copy(pathlib.Path(__file__).parent.parent / "scenarios" / "archer_op.json", "archer_op.json")
    out = run(tmp_path, NoLLM())
    agents = {json.loads(l)["agent"] for l in open("logs/run.jsonl", encoding="utf-8")}
    assert {"orchestrator", "designer", "critic", "simulator", "analyst", "reporter"} <= agents
    assert out["final_balance"]["archer"]["atk"] < 6          # лучника ослабили
