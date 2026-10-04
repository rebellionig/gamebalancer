"""Тонкий клиент LLM (OpenAI-совместимый /chat/completions: Groq, OpenAI, Ollama, LM Studio...).

Настройка только через переменные окружения / .env:
  LLM_API_KEY   - ключ (для локальных моделей можно любой непустой)
  LLM_MODEL     - имя модели
  LLM_BASE_URL  - по умолчанию https://api.groq.com/openai/v1
Каждый вызов логируется (kind="llm"), поэтому он учитывается в распределении нагрузки.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

from logger import log_event

DEFAULT_BASE_URL = "https://api.groq.com/openai/v1"
RETRIES = 2
TIMEOUT_S = 30


def load_env(path: str = ".env") -> None:
    """Минимальный загрузчик .env (без зависимостей). Уже заданные переменные не перезаписывает."""
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


class LLMError(RuntimeError):
    pass


class LLMClient:
    def __init__(self, agent: str):
        load_env()
        self.agent = agent
        self.key = os.environ.get("LLM_API_KEY", "")
        self.model = os.environ.get("LLM_MODEL", "")
        self.base_url = os.environ.get("LLM_BASE_URL", DEFAULT_BASE_URL).rstrip("/")

    @property
    def configured(self) -> bool:
        return bool(self.key and self.model)

    def chat(self, messages: list[dict], temperature: float = 0.2) -> str:
        if not self.configured:
            raise LLMError("LLM не настроен: задай LLM_API_KEY и LLM_MODEL в .env")
        body = json.dumps({
            "model": self.model, "messages": messages, "temperature": temperature,
            "response_format": {"type": "json_object"},
        }).encode()
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions", data=body, method="POST",
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.key}"},
        )
        last = None
        for attempt in range(1, RETRIES + 2):
            t0 = time.perf_counter()
            try:
                with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
                    text = json.load(resp)["choices"][0]["message"]["content"]
                log_event(self.agent, "llm", "chat", {"model": self.model, "messages": messages}, text,
                          duration_ms=(time.perf_counter() - t0) * 1000)
                return text
            except (urllib.error.URLError, TimeoutError, KeyError, json.JSONDecodeError) as e:
                last = e
                log_event(self.agent, "llm", "chat", {"model": self.model, "attempt": attempt}, None,
                          ok=False, error=repr(e), duration_ms=(time.perf_counter() - t0) * 1000)
                time.sleep(1.0 * attempt)
        raise LLMError(f"LLM недоступен после {RETRIES + 1} попыток: {last!r}")
