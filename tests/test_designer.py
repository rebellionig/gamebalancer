"""Тесты Дизайнера на фейковом LLM (без сети и ключей)."""
import json

from agents.designer import Designer
from game import balance as bal

BALANCE = bal.load("balance.json")
GOOD = json.dumps({"changes": [{"unit": "mage", "param": "atk", "from": 4, "to": 3}], "rationale": "маг силён"})


class FakeLLM:
    def __init__(self, replies):
        self.replies, self.calls = list(replies), 0
        self.configured = True

    def chat(self, messages, temperature=0.2):
        self.calls += 1
        return self.replies.pop(0)


def test_valid_json_used():
    d = Designer(FakeLLM([GOOD]))
    p = d.propose(1, BALANCE, None)
    assert p.changes[0].unit == "mage" and p.changes[0].to == 3


def test_invalid_json_is_repaired():
    llm = FakeLLM(["это не json", GOOD])
    p = Designer(llm).propose(1, BALANCE, None)
    assert llm.calls == 2 and p.changes[0].unit == "mage"


def test_falls_back_to_rule_after_repeated_garbage():
    llm = FakeLLM(["мусор"] * 3)
    p = Designer(llm).propose(1, BALANCE, None)
    assert llm.calls == 3 and p.changes  # сработало правило, система не упала


def test_schema_violation_triggers_repair():
    bad = json.dumps({"changes": [], "rationale": "пусто"})  # нужна минимум 1 правка
    llm = FakeLLM([bad, GOOD])
    assert Designer(llm).propose(1, BALANCE, None).changes[0].unit == "mage"
