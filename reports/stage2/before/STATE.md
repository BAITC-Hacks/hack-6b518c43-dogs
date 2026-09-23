# LEVRA — состояние на 2026-09-23

Работа сохранена в существующем официальном репозитории команды. Предоставленный kit перенесён из Downloads; история Git не переписана. Исходные файлы организаторов проверены по 16 SHA-256; все совпадают.

## Реализовано

- `agent.py`: self-contained deterministic offline `Agent.act(env)`, pooled historical priors, floor неопределённости, precision update по actual_n, tempering при конфликте prior/пилота, адаптивная разведка относительно предварительного плана, исследование альтернатив, отдельная модель call, остановка по ресурсам/ценности информации.
- Единый `Engine`: ordered ledger, реальные фильтры/сортировка/caps, затраты повторных контактов, отрицательный best effect, вероятностный pilot overlap, greedy и локальные перестановки/замены.
- Журнал собственных аргументов пилотов, prior/posterior, причины, ресурсы до/после, полный снимок гипотез и manifest. Нет чтения скрытых эффектов или состояния RNG.
- `backend/server.py`: реальный запуск через неизменённый local_eval, replay, immutable snapshot replan, паспорта, audit/repair, файловые артефакты.
- React/TypeScript UI: план, what-if, evidence, пилоты, сравнение политик/запусков, редактирование и ремонт плана; реальные данные, явные source labels. По последнему указанию пользователя Impeccable отключён, дизайн написан напрямую.
- `submission.csv`: 8 кампаний, сгенерирован неизменённым make_submission.py.

## Выполненные проверки

```sh
.venv/bin/python local_eval.py
.venv/bin/python local_eval.py --runs 10
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python tools/verify_originals.py
.venv/bin/python tools/benchmark_levra.py
.venv/bin/python tools/stress_levra.py
.venv/bin/python tools/check_reproducibility.py
.venv/bin/python tools/audit_repair_benchmark.py
npm --prefix frontend run build
.venv/bin/python tools/smoke_api.py
```

- 10 unit/integration checks прошли: actual_n/precision, негативный best, overlap/cost, порядок/caps/остатки, saturation, sunk costs, snapshot immutability, small/missing groups, зависимость решений от наблюдений и сброс act, audit/repair, запрет импортов truth.
- Official mock seed 42: net 2 434 331.795569111, cost 99 994, contacts 15 000, unique 11 603, pilots 20, final campaigns 8.
- Official mock seeds 0–9: mean 2 456 826.660924861; median 2 661 673.213636079; min 304 998.0907764959; max 3 290 635.183725944; 10/10 положительных. Mean runtime 3.54 с, max 4.11 с.
- Сравнение на тех же seed: template mean −480 836; history-only 3 783 136; fixed-pilots 4 322 639. Adaptive уступает последним двум в текущем mock; это не скрывается.
- 63 synthetic stress runs (7 сценариев, 3 seed, 3 floor). Default floor: sign-flip, редкий полезный переход и общие слабые эффекты остаются убыточными. Результаты независимы от official mock и не являются hidden benchmark.
- Два fresh процесса make_submission.py, PYTHONHASHSEED=11/937, dummy API key отсутствует/присутствует: SHA-256 одинаковый `903bb606121cb79e35edf8931870a7eb6d06d213ae015039300b8428ed2db622`.
- API smoke: настоящий run, replan без новых пилотов, channels/max campaigns/sunk-cost ограничения, отказ бюджета ниже уже потраченного и пустых каналов, audit некорректного плана, repair тем же solver. Исходный файл снимка не изменился. До ремонта 25 замечаний, после 6; оставшиеся предупреждения честно показаны.
- Отдельная audit/repair ablation: 3 фиксированных synthetic случая (дубликат, порядок при ограниченных ресурсах, неверный фильтр); после ремонта все валидны.
- Frontend build успешен; UI запуск проверен в реальном браузере. В ходе проверки исправлен step поля бюджета, мешавший вводу круглых сумм при ненулевых sunk costs.

Логи и машиночитаемые результаты: `reports/levra/`. Первоначальные template-отчёты сохранены отдельно. Во время разработки исправлялись эвристики разведки; приведённые выше числа относятся к финальной версии кода, не к ранним прогонам.

## Не готово / реальные ограничения

- Не доказано преимущество adaptive над history-only/fixed-pilot; следующая алгоритмическая работа — стоимость исследования и обнаружение редких переходов.
- Forecast существенно может завышать результат: seed 42 ~6.43 млн против Official mock 2.43 млн. Не калиброванный confidence и не реальная прибыль.
- Нет точных ID пилотов: их overlap только вероятностный. Solver ограниченный, не глобальный оптимум.
- LLM-ассистент не реализован; ключ никак не меняет default execution. Никаких внешних интеграций и реальных рассылок.
- Скрытый scorer не запускался. Производительность на гораздо больших входах не подтверждена.

Запуск продукта после установки зависимостей: `./run.sh`, http://127.0.0.1:8765. Инструкция чистой установки — README.md.

## Чистое окружение и интерфейс

Дополнительно создан отдельный venv без system-site-packages (`/private/tmp/levra-clean-venv`), установлен только requirements.txt. В нём официальный seed 42 дал те же 2 434 331.795569111, все 10 тестов прошли. Логи: `clean_install.txt`, `clean_local_eval.txt`, `clean_tests.txt`.

В реальном браузере проверены: запуск исследования, what-if 40 000 у.е. / 4 кампании / без звонков (0 новых пилотов), отображение ошибочного канала и автоматическое исправление, replay. Desktop и mobile 390 px сохранены в `reports/levra/ui/`; на mobile ширина документа = ширине viewport (390), горизонтального переполнения страницы нет; широкая таблица имеет собственную прокрутку.
