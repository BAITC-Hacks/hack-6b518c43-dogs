# Карта сдачи BeeAgent

| Требование | Дополнительная возможность | Реализация | Проверка | Настоящий артефакт |
|---|---|---|---|---|
| Agent.act(env), 1–10 кампаний | Повторная проверка крупных неопределённых решений | agent.py | python local_eval.py | reports/stage3/local_eval.txt |
| Пилоты, бюджет, контакты, порядок, пересечения | Ограничение исследовательских контактов | Engine.next_pilot / forecast / solve | python local_eval.py --runs 10 | reports/stage3/local_eval_10.txt |
| Проверка улучшений без подгонки под 42 | Замороженный протокол, старый агент, два кандидата и компаратор | tools/validate_stage3.py; архив baseline | JSONL всех 188 исходов; select_stage3.py | development.json, heldout.json, selection.json |
| Неизменность среды и данных | Хеши 16 защищённых файлов | tools/verify_originals.py | python tools/verify_originals.py | reports/stage3/originals.json |
| Детерминированный submission | Свежие процессы, разный hash seed, отсутствие/наличие фиктивного ключа | make_submission.py без изменений | python tools/check_reproducibility.py | reports/stage3/reproducibility.json |
| Честные показатели | Измерение привязано к алгоритму, данным и точному плану; несовместимые архивы блокируют пересчёт | backend/identity.py, plans.py | unittest + браузер | unit_tests.txt; screenshots/overview-1440.png |
| Агент объясняет решения | Реальные предварительные планы до/после пилота; паспорт и сравнение канала | Engine.observe; DecisionEvidence.tsx | браузер + диагностика | decision_trace.json; repeat-pilot-evidence.png |
| Изменение условий | Без новых пилотов, отдельная версия, сравнение и явное применение | PlanService / Engine | python tools/smoke_stage3.py | api_stage3.json; screenshots/compare-before-apply.png |
| Сохранение и экспорт | Активная версия переживает перезапуск; CSV не подменяет submission | server.py / plans.py | HTTP + браузер | browser_checks.json; screenshots/variant-restored.png |
| LLM вызывает настоящий движок | Четыре строгих инструмента, проверенные ссылки на показатели, предложения без авто-применения | backend/assistant.py | fake SDK protocol tests; explicit paid smoke после нового ключа | unit_tests.txt; ai_integration.json |
| Работа без API | Все ручные функции и конкурсная стратегия автономны | agent.py, frontend/backend | чистая установка + браузер | clean_install.json; assistant-no-api-1440.png |
| Подключение для проверяющего | Собственный локальный ключ, скрытый ввод, журнал расходов и предел $3 | configure_ai.py / check_ai_connection.py | config check без платного флага | ai_integration.json; docs/AI_ASSISTANT.md |

Внешний OpenAI не прошёл реальный smoke: локальный ключ отсутствует, сетевых вызовов 0. Подменные ответы не считаются доказательством внешней интеграции. Численные результаты на данных кейса, прогнозы и авторские стресс-миры имеют разные источники и не объединяются в один показатель.
