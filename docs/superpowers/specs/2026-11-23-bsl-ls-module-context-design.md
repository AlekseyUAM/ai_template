# Контекст вида модуля для MCP bsl_ls — дизайн

Дата: 2026-11-23
Статус: отложено — для задачи выбран отдельный скрипт в `code-analyze`
(см. `2026-11-23-event-handler-check-design.md`)

## Задача

Научить MCP-сервер `bsl_ls` проверять контекстные диагностики BSL Language
Server (прежде всего `EventHandlerInvalidSignature`) на одном модуле, без
монтирования проекта. Вид модуля и имя объекта передаются вместе с кодом.

## Почему сейчас не работает

BSL LS 1.30.0 содержит `EventHandlerInvalidSignature` (Error, включена), но
`EventContractsIndex` берёт контракты из `bsl-context` (HBK платформы), а
owner-тип — из `documentContext.getMdObject()` (`ДокументОбъект.<Имя>`).
MCP-обёртка запускает `analyze` на временном `src/<filename>` без
`--workspaceDir`; в контейнере нет HBK и метаданных. Контракт пуст —
диагностика молчит.

## Проверено

- С `--workspaceDir` + `--srcDir` + `"v8platform": {"binPath": ...}` BSL LS
  выдаёт:
  `EventHandlerInvalidSignature: ожидается до 2 параметров, объявлено 3`
  на реальном `Documents/ПриходнаяНакладная/Ext/ObjectModule.bsl`.
- Достаточно минимального workspace: `Configuration.xml` (10 КБ) с одним
  `<Document>ПриходнаяНакладная</Document>` + сгенерированный XML объекта
  (307 байт, только `<Document><Properties><Name>…`) + модуль.
- Проверка подкаталога (`--srcDir Documents/.../Ext`) не резолвит метаданные;
  нужен `--srcDir` = корень workspace. Поэтому workspace собирается
  минимальный (один объект), а не весь проект.

## Цели

1. Новый необязательный аргумент `check`: `module_type` + `owner_name`.
2. При их наличии обёртка генерирует минимальный workspace и запускает BSL LS
   с `--workspaceDir`, возвращая диагностики по модулю.
3. Без аргументов поведение не меняется (локальные диагностики).
4. Покрытие видов модулей: объектные и менеджерские модули, наборы записей,
   менеджер значения константы, общие модули, команды, модули приложения/сеанса,
   HTTP/Web-сервисы, внешние обработки/отчёты (по мере шаблонов).
5. Тесты чистой логики + интеграционный тест на реальном BSL LS.

## Не-цели

- Не монтируем проект и не сканируем всю конфигурацию (791 МБ).
- Не эмулируем полные метаданные: диагностики, которым нужны все объекты
  конфигурации (`QueryToMissingMetadata`, подписки и т.п.), в минимальном
  workspace не заработают. Это отдельный режим «полный workspace», если нужен.
- Не заменяем `code-analyze`: скрипт с проверкой экспортности/чужого модуля
  остаётся отдельной задачей (отложен).

## API

```json
{
  "sha256": "…",
  "code": "Процедура ОбработкаПроведения(…) …",
  "filename": "ObjectModule.bsl",
  "config": "{…}",
  "module_type": "Document.ObjectModule",
  "owner_name": "ПриходнаяНакладная"
}
```

- `module_type` — канонический ключ вида модуля (тот же, что в
  `event_handlers.json`): `Document.ObjectModule`, `Catalog.ManagerModule`,
  `InformationRegister.RecordSetModule`, `Configuration.ManagedApplicationModule`,
  `CommonModule.Module` и т.д.
- `owner_name` — имя объекта метаданных; обязательно для модулей объектов,
  менеджеров, наборов записей, констант, команд, сервисов. Для
  `Configuration.*` не требуется.
- Оба аргумента необязательны; если `module_type` не передан — старое поведение.
- Валидация: ключ из белого списка; `owner_name` — идентификатор 1С
  (буквы/цифры/`_`, не пустой, ≤ 128); никаких путей из ввода.

## Генерация workspace

Таблица `module_type → (каталог, XML-тег, файл модуля)`:
`Document.ObjectModule → Documents, Document, Ext/ObjectModule.bsl`,
`InformationRegister.RecordSetModule → InformationRegisters, InformationRegister,
Ext/RecordSetModule.bsl`, `CommonModule.Module → CommonModules, CommonModule,
Ext/Module.bsl`, `Configuration.ManagedApplicationModule → —, —,
Ext/ManagedApplicationModule.bsl` и т.д.

Для объектных/менеджерских/наборных модулей:

```
<tmp>/ws/Configuration.xml                 # <ChildObjects><Document>Имя</Document>
<tmp>/ws/Documents/Имя.xml                # минимальный XML объекта
<tmp>/ws/Documents/Имя/Ext/ObjectModule.bsl
<tmp>/ws/.bsl-language-server.json        # config + v8platform.binPath
```

Для `Configuration.*` — только `Configuration.xml` + `Ext/<ModuleFile>`.
Для общих модулей/команд/сервисов — соответствующий XML объекта + модуль.

Запуск:

```
java -jar bsl-language-server.jar analyze \
  --srcDir <ws> --workspaceDir <ws> \
  --configuration <ws>/.bsl-language-server.json \
  --outputDir <out> --reporter json
```

Диагностики фильтруются по имени файла модуля; формат ответа не меняется,
добавляется `context_used: true` и `module_type`.

## Справка платформы (HBK)

BSL LS нужен `shcntx_ru.hbk` (~40 МБ) — статическая справка платформы, не
данные проекта. Два варианта:

1. **Read-only монтирование каталога платформы** (как у `1c_platform`): в
   рецепт `bsl-ls` добавить `platform_env`, в карточку/план — `platform_path`,
   в конфиг — `v8platform.binPath` = смонтированный путь. Проект не
   монтируется; 40 МБ статики, не 791 МБ проекта.
2. **Запечь HBK в образ** при сборке (named build context или копирование в
   build context). Образ +40 МБ, сборка зависит от пути платформы; зато
   вообще без монтирований.

Рекомендация — вариант 1: проще, обновляется вместе с платформой, не раздувает
образ. Если требование «никаких монтирований» — вариант 2.

## Тесты

- Юнит: валидация `module_type`/`owner_name`; генерация файлов workspace для
  Document/Catalog/InformationRegister/CommonModule/Configuration; слияние
  `config` с `v8platform.binPath`; запрет path traversal; ответ без
  `module_type` не меняется.
- Интеграционный (Docker + Java): плохой `ОбработкаПроведения` в документе →
  `EventHandlerInvalidSignature` Error; хороший — нет.
- Проверить, что при `module_type` без `owner_name` (для metadata-модуля) —
  понятная ошибка, а не пустая диагностика.

## Риски

- Минимальный XML может не покрыть экзотические виды метаданных; для них
  добавим шаблоны или вернём ошибку «вид модуля не поддержан».
- BSL LS может изменить формат контрактов; фиксируем версию BSL LS в образе.
- HBK-версия должна соответствовать проверяемой конфигурации; для 8.3.27
  подходит.
- Полные контекстные диагностики (по всей конфигурации) не заработают — это
  осознанное ограничение минимального workspace.

## Отложено

- `code-analyze.check_event_handlers.py` (экспортность, событие чужого вида
  модуля) — отдельная задача, если bsl_ls её не покрывает.
- Полный workspace-режим bsl_ls (монтирование проекта или persistent LSP).
