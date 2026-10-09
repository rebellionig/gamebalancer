"""CLI: python main.py [--iters 8] [--matches 500] [--seed 42]"""
import argparse

from agents.analyst import Analyst
from agents.critic import Critic
from agents.designer import Designer
from agents.orchestrator import Orchestrator
from agents.reporter import Reporter
from agents.simulator import Simulator
from game import balance as bal
from store import Store


def main() -> None:
    ap = argparse.ArgumentParser(description="Мультиагентная балансировка игры")
    ap.add_argument("--iters", type=int, default=8)
    ap.add_argument("--matches", type=int, default=500)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--balance", default="balance.json", help="стартовый баланс (JSON)")
    args = ap.parse_args()

    orch = Orchestrator(Designer(), Critic(), Simulator(), Analyst(), Store(), max_iters=args.iters,
                        n_matches=args.matches, seed=args.seed, reporter=Reporter())
    out = orch.run(bal.load(args.balance))

    print(f"run_id={out['run_id']}  stop={out['stop_reason']}")
    for h in orch.store.history(out["run_id"]):
        r = h["result"]
        print(f"  iter {h['iteration']}: sides={r['side_winrate']} units={r['unit_winrate']}")
    print("final balance:", out["final_balance"])
    print("report:", out["report_path"])
    if out["report"] and out["report"].side_warning:
        print("ВНИМАНИЕ:", out["report"].side_warning)


if __name__ == "__main__":
    main()
