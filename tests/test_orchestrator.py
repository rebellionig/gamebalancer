from agents.analyst import Analyst
from agents.orchestrator import Orchestrator
from messages import CritiqueReport
from game import balance as bal
from messages import Change, ChangeProposal, SimResult
from store import Store

BALANCE = bal.load("balance.json")


class AnyDesigner:
    def propose(self, iteration, balance, report, critique=None):
        a = balance["archer"]["atk"]
        return ChangeProposal(iteration=iteration, rationale="x",
                              changes=[Change(unit="archer", param="atk", **{"from": a}, to=a)])


class ApprovingCritic:
    def review(self, proposal, balance, report):
        return CritiqueReport(iteration=proposal.iteration, approved=True)


class FakeSimulator:
    """Всегда возвращает НЕсбалансированную статистику; хеши баланса идут по кругу a, b, a, b..."""
    def __init__(self):
        self.calls = 0

    def run(self, proposal, base_balance, n_matches, seed):
        h = "ab"[self.calls % 2]
        self.calls += 1
        res = SimResult(iteration=proposal.iteration, balance_hash=h, n_matches=n_matches,
                        side_winrate={"A": 0.5, "B": 0.5}, draw_rate=0.0,
                        unit_winrate={"warrior": 0.7, "archer": 0.3, "mage": 0.5}, avg_turns=4.0)
        return res, base_balance


def test_cycle_stops_early(tmp_path):
    orch = Orchestrator(AnyDesigner(), ApprovingCritic(), FakeSimulator(), Analyst(), Store(tmp_path / "s.db"), max_iters=8)
    out = orch.run(BALANCE)
    assert out["stop_reason"] == "cycle"
    assert len(orch.store.history(out["run_id"])) == 3  # a, b, снова a -> стоп на третьей итерации


class Fresh(FakeSimulator):
    """Каждый раз новый хеш баланса -> цикла нет."""
    def run(self, proposal, base_balance, n_matches, seed):
        res, b = super().run(proposal, base_balance, n_matches, seed)
        return res.model_copy(update={"balance_hash": f"h{self.calls}"}), b


def test_max_iters_when_no_cycle(tmp_path):
    orch = Orchestrator(AnyDesigner(), ApprovingCritic(), Fresh(), Analyst(), Store(tmp_path / "s.db"), max_iters=4)
    assert orch.run(BALANCE)["stop_reason"] == "max_iters"


class RejectNTimesCritic:
    """Отклоняет первые n правок, потом одобряет. Запоминает, что получил Дизайнер."""
    def __init__(self, n):
        self.n, self.calls = n, 0

    def review(self, proposal, balance, report):
        self.calls += 1
        from messages import Issue
        if self.calls <= self.n:
            return CritiqueReport(iteration=proposal.iteration, approved=False,
                                  issues=[Issue(code="step_too_large", message="слишком большой шаг")])
        return CritiqueReport(iteration=proposal.iteration, approved=True)


class RecordingDesigner(AnyDesigner):
    def __init__(self):
        self.critiques = []

    def propose(self, iteration, balance, report, critique=None):
        self.critiques.append(critique)
        return super().propose(iteration, balance, report, critique)


def test_rejected_proposal_returns_to_designer_with_critique(tmp_path):
    d = RecordingDesigner()
    orch = Orchestrator(d, RejectNTimesCritic(2), Fresh(), Analyst(), Store(tmp_path / "s.db"), max_iters=1)
    orch.run(BALANCE)
    assert d.critiques[0] is None                       # первая попытка без замечаний
    assert d.critiques[1] is not None and not d.critiques[1].approved   # вторая - с замечаниями Критика
    assert len(d.critiques) == 3                        # 1 попытка + 2 ревизии


def test_iteration_skipped_when_critic_always_rejects(tmp_path):
    orch = Orchestrator(AnyDesigner(), RejectNTimesCritic(99), Fresh(), Analyst(),
                        Store(tmp_path / "s.db"), max_iters=2)
    out = orch.run(BALANCE)
    assert orch.store.history(out["run_id"]) == []      # ничего не симулировалось
