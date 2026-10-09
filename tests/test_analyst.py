from agents.analyst import Analyst
from messages import SimResult


def sim(n, **units):
    base = {"warrior": 0.5, "archer": 0.5, "mage": 0.5}
    base.update(units)
    return SimResult(iteration=1, balance_hash="h", n_matches=n, side_winrate={"A": 0.5, "B": 0.5},
                     draw_rate=0.0, unit_winrate=base, avg_turns=4.0)


def test_real_imbalance_detected():
    r = Analyst().analyze(sim(1000, archer=0.62, mage=0.47))
    verdicts = {f.metric: f.verdict for f in r.findings}
    assert verdicts["unit:archer"] == "overpowered" and verdicts["unit:mage"] == "ok"
    assert r.worst == "unit:archer" and not r.balanced


def test_noise_is_ignored():
    # 56% при n=50: отклонение больше 5%, но SE=7%, z<2 -> это шум, не сигнал
    r = Analyst().analyze(sim(50, archer=0.56))
    assert r.balanced and r.worst is None


def test_balanced_within_tolerance():
    assert Analyst().analyze(sim(1000, archer=0.53, warrior=0.47)).balanced


def test_underpowered_and_worst_choice():
    r = Analyst().analyze(sim(1000, warrior=0.40, archer=0.58))
    assert r.worst == "unit:warrior"  # |z| у warrior больше
    assert {f.metric: f.verdict for f in r.findings}["unit:warrior"] == "underpowered"


def test_side_warning():
    res = sim(1000)
    res.side_winrate = {"A": 0.38, "B": 0.62}
    assert "Перекос" in Analyst().analyze(res).side_warning
