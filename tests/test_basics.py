import random

import pytest

from game import balance as bal
from game.engine import play_match, run_batch
from messages import Change, ChangeProposal

BALANCE = bal.load("balance.json")


def test_batch_is_deterministic():
    assert run_batch(BALANCE, 50, seed=1) == run_batch(BALANCE, 50, seed=1)


def test_different_seed_differs():
    assert run_batch(BALANCE, 200, seed=1) != run_batch(BALANCE, 200, seed=2)


def test_match_terminates():
    r = play_match(BALANCE, ["warrior"] * 3, ["mage"] * 3, "greedy", "focus", random.Random(0))
    assert r["winner"] in ("A", "B", "draw") and 1 <= r["turns"] <= 30


def test_apply_changes_does_not_mutate_original():
    new = bal.apply_changes(BALANCE, [{"unit": "mage", "param": "atk", "to": 5}])
    assert new["mage"]["atk"] == 5 and BALANCE["mage"]["atk"] == 4


@pytest.mark.parametrize("change", [
    {"unit": "dragon", "param": "atk", "to": 3},
    {"unit": "mage", "param": "mana", "to": 3},
    {"unit": "mage", "param": "hp", "to": 0},
    {"unit": "mage", "param": "atk", "to": 999},
])
def test_invalid_changes_rejected(change):
    with pytest.raises(bal.BalanceError):
        bal.apply_changes(BALANCE, [change])


def test_message_schema_validation():
    with pytest.raises(Exception):
        ChangeProposal(iteration=1, changes=[], rationale="пусто")  # нужна минимум 1 правка
    p = ChangeProposal(iteration=1, changes=[Change(unit="mage", param="atk", **{"from": 4}, to=3)], rationale="x")
    assert p.changes[0].to == 3
