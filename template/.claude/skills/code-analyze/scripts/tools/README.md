# Обновление данных о системных перечислениях

`../system_enums.json` — снапшот справки платформы для правил
`system-enum-value` и `reserved-system-name`: 664 системных перечисления
(2914 значений) и 8 наборов значений (517 значений), русские и английские имена.
**Модели этот файл читать не нужно** — его читает `rules.py`.

## Источник

Данные снимаются из `shcntx_ru.hbk` установленной платформы 1С через
`bsl-ctx` (тот же разбор справки, что используют MCP-серверы платформенного
контекста). Установленный `1c_platform` MCP (`mcp-bsl-context`) отдаёт методы,
свойства и типы, но не список системных перечислений/наборов, поэтому
снапшот обновляется генератором.

```bash
bsl-ctx capture "<каталог платформы 1С>" -o corpus.sqlite
bsl-ctx parse --all --db corpus.sqlite --out parsed.jsonl
python tools/update_system_names.py --corpus corpus.sqlite --parsed parsed.jsonl \
    --out system_enums.json --platform 8.3.27.2170
```

Команды выполняются из каталога `scripts/`. После обновления:

```bash
python -m pytest tests/ -q
```

Генератор использует только стандартную библиотеку Python; `bsl-ctx` нужен
только для обновления снапшота.
