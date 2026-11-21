# CommonModule, ScheduledJob, EventSubscription (code-bound objects)

## CommonModule (Общий модуль)

Execution context flags (all bool, `false` by default). Creates an empty `Ext/Module.bsl`.

| Key | Default | Values |
|------|-----------|----------|
| `context` | - | flag shortcut (see below) |
| `global` | `false` | bool |
| `server` | `false` | bool |
| `serverCall` | `false` | bool (server call) |
| `clientManagedApplication` | `false` | bool (managed application client) |
| `clientOrdinaryApplication` | `false` | bool (ordinary application client) |
| `externalConnection` | `false` | bool |
| `privileged` | `false` | bool |
| `returnValuesReuse` | `DontUse` | `DontUse` / `DuringRequest` / `DuringSession` |

The `context` shortcut: `"server"` -> Server+ServerCall; `"client"` -> ClientManagedApplication;
`"serverClient"` -> Server+ClientManagedApplication.

```json
{ "type": "CommonModule", "name": "ОбменДаннымиСервер", "context": "server", "returnValuesReuse": "DuringRequest" }
```

## ScheduledJob (Регламентное задание)

| Key | Default | Values |
|------|-----------|----------|
| `methodName` | empty | handler method `"МодульСервер.Процедура"` (completed to `CommonModule.…`) |
| `description` | empty | job name |
| `key` | empty | key |
| `use` | `false` | bool (use) |
| `predefined` | `false` | bool (predefined) |
| `restartCountOnFailure` | `3` | number of retries on failure |
| `restartIntervalOnFailure` | `10` | retry interval, sec |

```json
{ "type": "ScheduledJob", "name": "ОбменДанными", "methodName": "ОбменДаннымиСервер.Выполнить", "use": true }
```

## EventSubscription (Подписка на событие)

| Key | Default | Values |
|------|-----------|----------|
| `source` | `[]` | source objects: `["CatalogObject.Контрагенты", "DocumentObject.Реализация"]` |
| `event` | `BeforeWrite` | `BeforeWrite` / `OnWrite` / `BeforeDelete` / `OnReadAtServer` / `FillCheckProcessing` … |
| `handler` | empty | handler method `"МодульСервер.Процедура"` (completed to `CommonModule.…`) |

```json
{ "type": "EventSubscription", "name": "ПередЗаписьюКонтрагента",
  "source": ["CatalogObject.Контрагенты"], "event": "BeforeWrite",
  "handler": "ОбщегоНазначенияСервер.ПередЗаписьюКонтрагента" }
```

> The handler procedure (`methodName` / `handler`) must exist in the specified common module (exported).
