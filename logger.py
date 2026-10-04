"""Логирование КАЖДОГО вызова агента и инструмента в logs/run.jsonl.

Из этого файла потом считается распределение нагрузки (tools/load_report.py).
"""
from __future__ import annotations

import functools
import json
import time
from pathlib import Path

LOG_PATH = Path("logs/run.jsonl")


def log_event(agent: str, kind: str, name: str, payload_in, payload_out=None,
              ok: bool = True, error: str | None = None, duration_ms: float = 0.0) -> None:
    """kind: 'agent' | 'llm' | 'tool'."""
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    rec = {
        "ts": time.time(), "agent": agent, "kind": kind, "name": name,
        "ok": ok, "error": error, "duration_ms": round(duration_ms, 2),
        "input": payload_in, "output": payload_out,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")


def logged(agent: str, kind: str, name: str):
    """Декоратор: логирует вход, выход, время и ошибки функции."""
    def deco(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            t0 = time.perf_counter()
            try:
                out = fn(*args, **kwargs)
            except Exception as e:
                log_event(agent, kind, name, {"args": args[1:], "kwargs": kwargs}, None,
                          ok=False, error=repr(e), duration_ms=(time.perf_counter() - t0) * 1000)
                raise
            log_event(agent, kind, name, {"args": args[1:], "kwargs": kwargs}, out,
                      duration_ms=(time.perf_counter() - t0) * 1000)
            return out
        return wrapper
    return deco
