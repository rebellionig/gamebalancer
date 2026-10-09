from agents.analyst import Analyst
from agents.critic import Critic
from game import balance as bal
from messages import Change, ChangeProposal, SimResult

BASE = bal.load("balance.json")
BROKEN = bal.load("scenarios/archer_op.json")


def prop(*changes):
    return ChangeProposal(iteration=1, rationale="t", changes=[
        Change(unit=u, param=p, **{"from": f}, to=t) for u, p, f, t in changes])


def report(**units):
    base = {"warrior": 0.5, "archer": 0.5, "mage": 0.5}
    base.update(units)
    sim = SimResult(iteration=1, balance_hash="h", n_matches=1000, side_winrate={"A": 0.5, "B": 0.5},
                    draw_rate=0, unit_winrate=base, avg_turns=4)
    return Analyst().analyze(sim)


def codes(r):
    return {i.code for i in r.issues}


def test_small_correct_change_approved():
    assert Critic().review(prop(("archer", "atk", 3, 2)), BASE, None).approved


def test_step_too_large():
    assert "step_too_large" in codes(Critic().review(prop(("archer", "atk", 3, 8)), BASE, None))


def test_from_mismatch_detects_hallucinated_value():
    assert "from_mismatch" in codes(Critic().review(prop(("archer", "atk", 5, 4)), BASE, None))


def test_invalid_value_caught_before_simulation():
    r = Critic().review(prop(("archer", "atk", 3, 999)), BASE, None)
    assert "invalid_change" in codes(r) and not r.approved


def test_wrong_direction_buffing_overpowered_unit():
    r = Critic().review(prop(("archer", "atk", 3, 4)), BASE, report(archer=0.65))
    assert "wrong_direction" in codes(r)


def test_wrong_direction_nerfing_underpowered_unit():
    r = Critic().review(prop(("mage", "atk", 4, 3)), BASE, report(mage=0.35))
    assert "wrong_direction" in codes(r)


def test_correct_direction_passes():
    assert Critic().review(prop(("archer", "atk", 3, 2)), BASE, report(archer=0.65)).approved


def test_exploit_that_makes_things_worse_rejected():
    # archer.atk 3->5 на нормальном балансе: у лучников появляется жёсткая контра
    r = Critic().review(prop(("archer", "atk", 3, 5)), BASE, None)
    assert "exploit_worse" in codes(r) and r.probe


def test_noop_on_already_broken_balance_is_approved():
    # баланс сломан, но правка его НЕ ухудшает -> Критик не блокирует исправление
    r = Critic().review(prop(("archer", "atk", 6, 6)), BROKEN, None)
    assert r.approved


def test_fixing_broken_balance_is_approved():
    assert Critic().review(prop(("archer", "atk", 6, 5)), BROKEN, report(archer=0.65)).approved
