"""Запуск набора тестовых сценариев: python run_scenarios.py [--md docs/scenario_results.md]"""
import argparse
import time

from scenarios.suite import SCENARIOS


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--md", help="сохранить таблицу результатов в markdown-файл")
    args = ap.parse_args()

    rows, failed = [], 0
    for sc in SCENARIOS:
        t0 = time.perf_counter()
        ok, detail = sc.run()
        dt = time.perf_counter() - t0
        status = ("ОГРАНИЧЕНИЕ (воспроизводится)" if ok else "FAIL") if sc.kind == "limitation" else ("PASS" if ok else "FAIL")
        failed += 0 if ok else 1
        rows.append((sc, status, detail, dt))
        print(f"[{status:>6}] {sc.id:32s} {dt:5.1f}s  {detail}")

    passed = sum(1 for _, s, _, _ in rows if s == "PASS")
    print(f"\nPASS: {passed}/{len(rows)}, ограничений зафиксировано: {sum(1 for s, st, _, _ in rows if s.kind == 'limitation' and st != 'FAIL')}, FAIL: {failed}")

    if args.md:
        lines = ["# Результаты тестовых сценариев", "",
                 "| # | Сценарий | Ожидаемый результат | Фактический результат | Статус |", "|---|---|---|---|---|"]
        for i, (sc, status, detail, _) in enumerate(rows, 1):
            lines.append(f"| {i} | {sc.title} (`{sc.id}`) | {sc.expected} | {detail} | {status} |")
        open(args.md, "w", encoding="utf-8").write("\n".join(lines) + "\n")
        print("записано:", args.md)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
