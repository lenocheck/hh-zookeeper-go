# Дз-4: обеспечение отказоустойчивости средствами Apache ZooKeeper. Вариант 7: «Программист, разработчик на Go»

Ансамбль из трёх серверов ZooKeeper 3.9.6 (Docker) и два координатора расчёта пар навыков Go-вакансий из дз-3. Один из координаторов выбирается лидером через ZooKeeper, при его приостановке запасной продолжает расчёт с чекпоинта. Сравнивается запуск без защиты (результат записан дважды) и с защитой по эпохе (запись устаревшего лидера отклоняется, BadVersionError)

Исходный csv в репозитории нет: файл хранится в объектном хранилище RustFS (бакет hh-lake), результат дз-3 для пар лежит в `s3://hh-lake/results/mr/n2.tsv`

Подробности выполнения: отчёт в папке `report/`

## Структура репозитория

```
hh-zookeeper-go/
    .gitignore
    .gitattributes
    README.md
    requirements.txt
    zk/                         ансамбль ZooKeeper
        compose.yaml            три контейнера zk1, zk2, zk3 (образ zookeeper:3.9.6)
        make_cfg.py             генерация zoo.cfg для трёх серверов
        zk1/zoo.cfg
        zk2/zoo.cfg
        zk3/zoo.cfg
    src/                        исходный код
        coordinator.py          координатор: выбор лидера, чекпоинт, публикация результата
        zk_common.py            общие константы: узлы ZooKeeper, таймаут сессии, каталог логов
        pause_proc.py           приостановка процесса лидера на заданное время
        zk_reset.py             очистка узлов ZooKeeper, чекпоинта и результатов перед прогоном
        check_result.py         проверка результата и время смены лидера
        common.py, s3_chunks.py, ...   код дз-3 (правило отбора вакансий, чтение csv из S3 чанками)
    sql/                        запросы DuckDB из дз-3
    logs/                       журналы прогонов и транскрипты этапов
    outputs/                    выводы команд текстом
    report/
        Луценко_Елена_дз4.pdf   отчёт
```

## Логи и выводы

| Файл | Содержимое |
|---|---|
| `logs/nofence_A.log`, `nofence_B.log`, `nofence_pause.log` | этап 3, без защиты (FENCING=0) |
| `logs/fence_A.log`, `fence_B.log`, `fence_pause.log` | этап 4, с защитой по эпохе (FENCING=1) |
| `logs/transcript_stage2.txt`, `transcript_stage3.txt`, `transcript_stage4.txt` | полные транскрипты консоли по этапам |
| `outputs/stage2_ensemble.txt`, `stage2_ephemeral.txt` | роли серверов, потеря серверов, эфемерный узел |
| `outputs/stage3_nofence.txt`, `check_nofence.txt` | вывод этапа 3 и проверка результата |
| `outputs/stage4_fence.txt`, `check_fence.txt` | вывод этапа 4 и проверка результата |
