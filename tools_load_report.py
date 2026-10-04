"""Считает распределение нагрузки по логам: доля вызовов (агенты + LLM + инструменты) на агента.

Запуск: python tools_load_report.py [logs/run.jsonl]
Требование ТЗ: ни один агент не выполняет более 40% всех вызовов LLM и инструментов.
"""
import json
import sys
from collections import Counter

path = sys.argv[1] if len(sys.argv) > 1 else "logs/run.jsonl"
calls = Counter()
for line in open(path, encoding="utf-8"):
    rec = json.loads(line)
    if rec["kind"] in ("llm", "tool"):   # считаем только вызовы LLM и инструментов
        calls[rec["agent"]] += 1

total = sum(calls.values())
print(f"всего вызовов LLM+инструментов: {total}")
for agent, n in calls.most_common():
    share = n / total
    flag = "  <-- ПРЕВЫШЕНИЕ 40%" if share > 0.40 else ""
    print(f"  {agent:12s} {n:4d}  {share:6.1%}{flag}")
