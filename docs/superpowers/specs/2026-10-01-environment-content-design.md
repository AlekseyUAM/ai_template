# Содержимое окружения (субагенты, скилы, правила, хуки) — дизайн (подсистема №2)

Дата: 2026-10-01
Статус: утверждён к реализации (автономный режим — решения приняты на основе PLAN.md, спека №1 и референсов в deps/)

## Контекст

Подсистема №2 наполняет окружение, каркас которого создаёт подсистема №1
(установщик в составе agentmon). №1 уже:
- создаёт layout: `.claude/agents`, `.claude/skills`, `.claude/hooks`, `src/cf`, `src/cfe`, `tasks`;
- пишет `ai1c.config.json` (источник истины, Вариант A), в т.ч. список субагентов
  с `{agent, model, effort}`;
- пишет заглушку `CLAUDE.md` (шаг `claude` в `installer.py`).

№2 заменяет заглушку реальным содержимым: 5 субагентов, набор скилов, правил и
хуков, а также шаблон `settings.json`. Содержимое раскладывается установщиком при
создании/обновлении проекта и параметризуется моделью/effort из конфига.

Рамочные решения проекта (из спека №1) действуют: своя реализация (deps —
референс), кросс-платформа Linux+Windows, хост-нативно + MCP в Docker, без новых
зависимостей, тексты на русском.

## Референсы (deps/, только читаем)

- `deps/1c-agent-based-dev-framework` — формат агентов (frontmatter name/description/
  model/skills + системный промпт на русском), методология SDD+TDD, этапы 0-4,
  хуки (block-xml-edit, инъекция каталога скилов), capability↔MCP реестр, RUS-ENG зеркало.
- `deps/cc-1c-skills` — формат скилов Claude Code (SKILL.md: frontmatter
  name/description/allowed-tools + тело), хуки PreToolUse (support-guard) и
  PostToolUse (skill-suggester) на Node, набор операционных скилов 1С.

## Сознательные упрощения (YAGNI, зафиксировано)

1. **Без RUS-ENG зеркала.** Пишем контент сразу на русском, одно дерево. Экономия
   токенов зеркалом не стоит сложности синхронизации для нашего масштаба.
2. **Без воспроизведения 80+ операционных скилов cc-1c-skills.** Они — обёртки над
   ps1/py-скриптами и платформой; это отдельная интеграция (будущая работа). №2
   даёт небольшой набор скилов-руководств (MCP-ориентированных), а не тул-обёрток.
3. **Копирование, не симлинки.** Контент копируется в проект (самодостаточный
   каталог в git, Вариант A; симлинки проблемны на Windows). Framework использует
   симлинки — мы сознательно иначе.
4. **Хуки на Python** (не Node и не PowerShell) — кросс-платформенно и без новых
   зависимостей (у нас уже Python-стек).
5. **Минимум хуков/правил/скилов** — ровно то, что нужно для цикла; расширяется позже.

## Состав содержимого

### Субагенты (5, формат Claude Code)

Файлы `.claude/agents/<name>.md`, frontmatter + системный промпт на русском.
Frontmatter: `name`, `description` (с триггером «когда применять»), `tools`
(список инструментов + нужные MCP), `model` (подставляется из конфига при
установке). `effort` переносится как справочное поле frontmatter (Claude Code
нативно потребляет `model`; `effort` — advisory, используется оркестрацией №3).

| name | роль | readonly | ключевые MCP |
|------|------|----------|--------------|
| analyst | аналитик: требования → спека (цель, требования, ограничения, критерии приёмки) | да | bsl-platform-context, 1c-naparnic, code-index, 1c-md |
| architect | архитектор: техдизайн + декомпозиция на этапы | да | 1c-md, code-index, bsl-platform-context |
| developer | разработчик: BSL-код по спеке и тестам | нет | 1c-syntax-checker-mcp, code-index, bsl-platform-context, 1c-md |
| tester | тестировщик: тесты (YaxUnit), покрытие, прогон | нет | 1c-syntax-checker-mcp, 1c-md |
| reviewer | код-ревьюер: приёмка, стандарты, качество | да | 1c-syntax-checker-mcp, code-index, 1c-naparnic |

Каждый системный промпт по структуре: Роль / Когда вызываюсь / Вход / Что делаю /
Выход (артефакт `<ROLE>.md` в каталоге задачи — согласуется с №3) / Используемые MCP /
Границы.

### Скилы (руководства, SKILL.md)

Файлы `.claude/skills/<name>/SKILL.md`. Небольшой набор:

1. `mcp-usage` — какой из 5 MCP когда применять (метаданные→1c-md, статанализ BSL→
   1c-syntax-checker-mcp, справка платформы→bsl-platform-context, сложные вопросы 1С→
   1c-naparnic, поиск по кодовой базе→code-index). `allowed-tools: []` (руководство).
2. `bsl-coding-standards` — стандарты кода BSL (именование, структура модулей,
   запросы, обработка ошибок). Руководство.
3. `sdd-tdd-workflow` — методология: спека до кода, Red→Green, слои тестов (YaxUnit
   для серверной логики). Руководство.

### Правила (markdown, подключаются из CLAUDE.md)

Файлы `.claude/rules/<name>.md`. Набор-гардрейлы:

1. `search-before-write` — перед написанием нового кода искать существующее через
   code-index / 1c-md.
2. `verify-with-syntax-checker` — после правок BSL прогонять статанализ через
   1c-syntax-checker-mcp.
3. `task-artifacts` — каждый субагент оставляет результат в `<ROLE>.md` в каталоге
   задачи и дописывает статус (мост к №3; в №2 — как соглашение).

### Хуки (Python, кросс-платформа)

Файл `.claude/hooks/bsl_nudge.py` — `PostToolUse` по `Edit|Write|MultiEdit`: если
изменён `*.bsl`, выдаёт `additionalContext`-подсказку «прогони статанализ (навык
mcp-usage / 1c-syntax-checker-mcp)». Неблокирующий. Читает stdin-JSON протокола
Claude Code, пишет stdout-JSON. Регистрируется в `settings.json`.

### settings.json

Шаблон `settings.json` (рендерится установщиком): регистрация хука `bsl_nudge.py`;
разрешения (allow для инструментов MCP и для команд выгрузки). Модели субагентов —
в файлах агентов (frontmatter), не здесь.

### CLAUDE.md

Шаблон: заголовок проекта, данные разработчика/платформы (из конфига, как сейчас в
№1), раздел «Правила» со ссылками-подключениями на файлы `.claude/rules/*.md`,
краткий обзор цикла задачи и 5 субагентов.

## Размещение контента (интеграция с №1)

Новый модуль `app/src/agentmon/env/content.py`:

- Каталог-шаблон `app/src/agentmon/env/content/` в пакете:
  `agents/*.md`, `skills/<name>/SKILL.md`, `rules/*.md`, `hooks/bsl_nudge.py`,
  `settings.json.tmpl`, `CLAUDE.md.tmpl`.
- `deploy_content(config, *, update) -> None`:
  1. копирует `agents/`, `skills/`, `rules/`, `hooks/` в `<project>/.claude/`;
  2. в каждый скопированный `agents/<name>.md` подставляет `model` и `effort` из
     `config.agents` (по совпадению `name`==`agent`); агент без записи в конфиге
     получает дефолт;
  3. рендерит `settings.json` → `<project>/.claude/settings.json`;
  4. рендерит `CLAUDE.md` → `<project>/CLAUDE.md`.
- Поведение при `update`: `CLAUDE.md` и `.claude/settings.json` пишутся через
  `write_preserving` (бэкап `.bak` перед заменой — пользователь мог править);
  `agents/skills/rules/hooks` — перезапись из шаблона (framework-managed), т.к.
  это сопровождаемый контент.

### Правка установщика №1

В `installer.py` шаг `claude` (сейчас пишет заглушку `CLAUDE.md`) заменяется на шаг
`content`, вызывающий `deploy_content(config, update=update)`. Остальные шаги (layout,
config, mcp, dump-*, register) без изменений. Рендеринг `CLAUDE.md` из конфига
переезжает в `content.py` (из `installer._claude_md`).

## Границы (не входит в №2)

- Жизненный цикл задачи, `tasks/task#id`, json-этапы/статусы, оркестрация этапов — №3.
- Автономный прогон списка задач — №4.
- Бенчмарки — №5.
- Операционные тул-скилы 1С (обёртки ps1/py над платформой) — будущая интеграция.

## Тестирование

- Валидационный тест контента: каждый `agents/<name>.md` имеет корректный frontmatter
  (name ∈ {analyst,architect,reviewer,developer,tester}, есть description/tools), ровно
  5 агентов; каждый `skills/*/SKILL.md` и `rules/*.md` имеют требуемый frontmatter/
  заголовок; `hooks/bsl_nudge.py` существует.
- Юнит-тест `bsl_nudge.py`: stdin-JSON про `Edit` `*.bsl` → stdout содержит подсказку;
  не-bsl файл → пустой/нейтральный вывод (не блокирует).
- Юнит-тест `deploy_content` (на временном каталоге): файлы скопированы в `.claude/`;
  в `agents/developer.md` подставлены `model`/`effort` из конфига; `settings.json` и
  `CLAUDE.md` отрендерены; при `update=True` старые `CLAUDE.md`/`settings.json`
  забэкаплены в `.bak`.
- Интеграционный тест установщика: после `install_environment` в проекте есть
  `.claude/agents/*.md` (5 шт.), `.claude/skills/*`, `.claude/rules/*`,
  `.claude/hooks/bsl_nudge.py`, `.claude/settings.json`, `CLAUDE.md`; полный набор
  тестов зелёный.
