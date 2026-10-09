"""Агент-Репортёр. Единственная роль: собрать итоговый отчёт по истории итераций.

Разделение ответственности (чтобы отчёт не мог «выдумать» цифры):
  - ВСЕ числа, таблицы и список изменений строятся кодом из истории в SQLite;
  - LLM пишет только короткий текстовый вывод (3-4 предложения) по уже готовым фактам;
  - если LLM не настроена, недоступна, вернула мусор или слишком длинный текст, вывод строится по шаблону.
В заголовке раздела «Выводы» указано, чем он сформирован: LLM или шаблоном.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from agents.llm import LLMClient, LLMError
from logger import log_event

NAME = "reporter"
MAX_SUMMARY_CHARS = 1200  # «3-4 предложения»: всё, что длиннее, считаем мусором

STOP_TEXT = {
    "converged": "баланс достигнут: ни один юнит не имеет значимого отклонения от 50%",
    "cycle": "баланс вернулся в уже пройденное состояние (цикл)",
    "max_iters": "исчерпан лимит итераций",
    "timeout": "исчерпан лимит времени",
}

SYSTEM_PROMPT = """Ты технический писатель. По фактам о прогоне балансировки игры напиши итог на русском:
3-4 предложения, без списков. Используй ТОЛЬКО числа и факты из входных данных, ничего не выдумывай.
Отвечай ТОЛЬКО JSON: {"summary": "текст"}"""


class Reporter:
    def __init__(self, llm: LLMClient | None = None, out_dir: str | Path = "reports"):
        self.llm = llm or LLMClient(NAME)
        self.out_dir = Path(out_dir)

    def write(self, run_id: str, stop_reason: str, start_balance: dict, final_balance: dict,
              history: list[dict], skipped: list[int] | None = None) -> Path | None:
        facts = self._facts(run_id, stop_reason, start_balance, final_balance, history, skipped or [])
        summary, source = self._summary(facts)
        path = self._save(run_id, self._render(facts, summary, source))
        log_event(NAME, "agent", "write", {"run_id": run_id, "iterations": len(history)},
                  {"path": str(path) if path else None, "summary_source": source})
        return path

    # ---------- факты (только код, без LLM) ----------
    @staticmethod
    def _facts(run_id, stop_reason, start, final, history, skipped) -> dict:
        rows = []
        for h in history:
            changes = [f"{c['unit']}.{c['param']} {c['from']}→{c['to']}" for c in h["proposal"]["changes"]
                       if c["from"] != c["to"]] or ["без изменений"]
            res = h["result"]
            rows.append({
                "iteration": h["iteration"],
                "changes": ", ".join(changes),
                "rationale": h["proposal"].get("rationale", ""),
                "units": res["unit_winrate"],
                "sides": res["side_winrate"],
                "revisions": res.get("revisions", 0),
            })
        net = [{"unit": u, "param": p, "from": start[u][p], "to": final[u][p]}
               for u in start for p in start[u] if start[u][p] != final[u][p]]
        last = history[-1]["result"].get("analysis", {}) if history else {}
        return {"run_id": run_id, "stop_reason": stop_reason, "iterations": len(history), "skipped": skipped,
                "revisions_total": sum(r["revisions"] for r in rows), "rows": rows, "net_changes": net,
                "last_unit_winrate": rows[-1]["units"] if rows else {}, "side_warning": last.get("side_warning")}

    # ---------- вывод: LLM или шаблон ----------
    def _summary(self, facts: dict) -> tuple[str, str]:
        if self.llm.configured:
            try:
                prompt_facts = {k: facts[k] for k in ("stop_reason", "iterations", "skipped", "revisions_total",
                                                      "net_changes", "last_unit_winrate")}
                raw = self.llm.chat([
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps(prompt_facts, ensure_ascii=False)},
                ])
                text = json.loads(raw).get("summary")
                if isinstance(text, str) and 0 < len(text.strip()) <= MAX_SUMMARY_CHARS:
                    return text.strip(), "LLM"
                log_event(NAME, "agent", "llm_fallback", {"run_id": facts["run_id"]}, None, ok=False,
                          error="пустой или слишком длинный вывод")
            except (LLMError, json.JSONDecodeError, AttributeError) as e:
                log_event(NAME, "agent", "llm_fallback", {"run_id": facts["run_id"]}, None, ok=False, error=str(e))
        return self._template_summary(facts), "шаблон"

    @staticmethod
    def _template_summary(f: dict) -> str:
        text = f"Прогон завершён: {STOP_TEXT.get(f['stop_reason'], f['stop_reason'])}. Выполнено итераций: {f['iterations']}. "
        if f["net_changes"]:
            text += "Итоговые изменения баланса: " + ", ".join(
                f"{c['unit']}.{c['param']} {c['from']}→{c['to']}" for c in f["net_changes"]) + ". "
        else:
            text += "Итоговый баланс совпадает с начальным. "
        if f["last_unit_winrate"]:
            text += "Винрейты юнитов на последней итерации: " + ", ".join(
                f"{u} {v:.1%}" for u, v in f["last_unit_winrate"].items()) + "."
        return text.strip()

    # ---------- markdown ----------
    @staticmethod
    def _render(f: dict, summary: str, source: str) -> str:
        skipped = ", ".join(map(str, f["skipped"])) if f["skipped"] else "нет"
        lines = [
            f"# Отчёт о балансировке (прогон {f['run_id']})", "",
            f"- Причина остановки: **{f['stop_reason']}** ({STOP_TEXT.get(f['stop_reason'], '')})",
            f"- Итераций выполнено: {f['iterations']}, пропущено: {skipped}",
            f"- Возвратов Критиком на доработку: {f['revisions_total']}",
            f"- Сформирован: {datetime.now():%Y-%m-%d %H:%M}", "",
            "## Изменения баланса (старт → итог)", "",
        ]
        if f["net_changes"]:
            lines += ["| Юнит | Параметр | Было | Стало |", "|---|---|---|---|"]
            lines += [f"| {c['unit']} | {c['param']} | {c['from']} | {c['to']} |" for c in f["net_changes"]]
        else:
            lines += ["Изменений нет."]
        if f["side_warning"]:
            lines += ["", f"> ⚠ {f['side_warning']}"]

        units = list(f["rows"][0]["units"]) if f["rows"] else []
        lines += ["", "## Ход итераций", "",
                  "| # | Правка | Обоснование | " + " | ".join(units) + " | A / B | Возвраты |",
                  "|---|---|---|" + "---|" * len(units) + "---|---|"]
        for r in f["rows"]:
            why = r["rationale"].replace("|", "/")
            winrates = " | ".join(f"{r['units'][u]:.1%}" for u in units)
            sides = " / ".join(f"{r['sides'][s]:.1%}" for s in ("A", "B") if s in r["sides"])
            lines.append(f"| {r['iteration']} | {r['changes']} | {why} | {winrates} | {sides} | {r['revisions']} |")

        label = "сгенерировано LLM по данным выше" if source == "LLM" else "собрано по шаблону из данных выше"
        lines += ["", f"## Выводы ({label})", "", summary]
        return "\n".join(lines) + "\n"

    # ---------- запись файла (инструмент) ----------
    def _save(self, run_id: str, md: str) -> Path | None:
        path = self.out_dir / f"report_{run_id}.md"
        try:
            self.out_dir.mkdir(parents=True, exist_ok=True)
            path.write_text(md, encoding="utf-8")
        except OSError as e:  # отчёт - не повод ронять весь прогон
            log_event(NAME, "tool", "write_report", {"path": str(path)}, None, ok=False, error=repr(e))
            return None
        log_event(NAME, "tool", "write_report", {"path": str(path), "chars": len(md)}, {"saved": True})
        return path
