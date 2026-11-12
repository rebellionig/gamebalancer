"""Сценарии системы под pytest. Источник правды: scenarios/suite.py."""
import pytest

from scenarios import suite
from scenarios.suite import SCENARIOS


@pytest.mark.parametrize("sc", SCENARIOS, ids=[s.id for s in SCENARIOS])
def test_scenario(sc):
    ok, detail = sc.run()
    assert ok, f"{sc.title}: ожидалось «{sc.expected}», получено: {detail}"


def test_harness_can_fail():
    # лучнику нужно 4 итерации; если потребовать не более 1, проверка обязана провалиться
    ok, _ = suite._fixes_only(suite.variant(archer__atk=6, archer__hp=7), "archer", "atk", 1)
    assert not ok


def test_enough_scenarios_for_exam():
    assert len([s for s in SCENARIOS if s.kind == "normal"]) >= 10
