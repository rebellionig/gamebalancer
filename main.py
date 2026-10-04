"""CLI: python main.py [--iters 8] [--matches 500] [--seed 42]"""
import argparse

from agents.designer import Designer
from agents.orchestrator import Orchestrator
from agents.simulator import Simulator
from game import balance as bal
from store import Store


def main() -> None:
    ap = argparse.ArgumentParser(description="Мультиагентная балансировка игры")
    ap.add_argument("--iters", type=int, default=8)
    ap.add_argument("--matches", type=int, default=500)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    orch = Orchestrator(Designer(), Simulator(), Store(), max_iters=args.iters,
                        n_matches=args.matches, seed=args.seed)
    out = orch.run(bal.load())

    print(f"run_id={out['run_id']}  stop={out['stop_reason']}")
    for h in orch.store.history(out["run_id"]):
        r = h["result"]
        print(f"  iter {h['iteration']}: sides={r['side_winrate']} units={r['unit_winrate']}")
    print("final balance:", out["final_balance"])


if __name__ == "__main__":
    main()
