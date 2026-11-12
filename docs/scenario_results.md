# Результаты тестовых сценариев

| # | Сценарий | Ожидаемый результат | Фактический результат | Статус |
|---|---|---|---|---|
| 1 | Сбалансированный старт (`balanced_start`) | converged на 1-й итерации, баланс не меняется | stop=converged, итераций=1, изменения={} | PASS |
| 2 | Лучник слишком силён (atk 6, hp 7) (`archer_overpowered`) | converged ≤6 итераций, меняется только archer.atk (вниз) | stop=converged, итераций=5, изменения={'archer.atk': (6, 2)} | PASS |
| 3 | Лучник немного силён (atk 5) (`archer_mild`) | converged ≤6 итераций, меняется только archer.atk (вниз) | stop=converged, итераций=3, изменения={'archer.atk': (5, 3)} | PASS |
| 4 | Маг слишком силён (atk 7) (`mage_overpowered`) | converged ≤6 итераций, меняется только mage.atk (вниз) | stop=converged, итераций=4, изменения={'mage.atk': (7, 4)} | PASS |
| 5 | LLM отвечает не-JSON (`llm_returns_garbage`) | Дизайнер переходит на запасное правило, система всё равно сходится | stop=converged, вызовов LLM=15, archer.atk=2 | PASS |
| 6 | Дизайнер предлагает шаг 3→8 (`critic_rejects_big_step`) | Критик отклоняет (step_too_large), итерации пропущены, симуляций нет | пропущено=[1, 2], замечания=['exploit_worse', 'step_too_large'], симуляций=0 | PASS |
| 7 | Дизайнер усиливает уже сильного лучника (`critic_rejects_wrong_direction`) | Критик отклоняет (wrong_direction), баланс не меняется | симуляций=1, пропущено=[2, 3], замечания=['wrong_direction'] | PASS |
| 8 | Правка создаёт жёсткую контру (`critic_blocks_new_exploit`) | Критик отклоняет (exploit_worse) по пробным матчам | пропущено=[1], замечания=['exploit_worse'] | PASS |
| 9 | Баланс ходит между двумя сломанными состояниями (`cycle_detected`) | stop=cycle на 3-й итерации, а не 8 итераций впустую | stop=cycle, итераций=3 из 8 | PASS |
| 10 | Лимит итераций меньше, чем нужно для сходимости (`iteration_limit`) | stop=max_iters, ровно 2 итерации, баланс ещё не достигнут | stop=max_iters, итераций=2, balanced=False | PASS |
| 11 | Воин почти без урона (atk 1): слепое пятно командной метрики (`weak_unit_detected`) | чистые матчи вскрывают воина, converged, меняется только warrior.atk (вверх) | stop=converged, итераций=2, изменения={'warrior.atk': (1, 2)} | PASS |
| 12 | Маг с hp 8 (доминирует в чистых матчах) (`strong_mage_hp`) | converged, меняется только mage.atk (вниз) | stop=converged, итераций=2, изменения={'mage.atk': (4, 3)} | PASS |
