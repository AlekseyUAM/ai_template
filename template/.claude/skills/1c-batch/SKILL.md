---
name: 1c-batch
description: "Batch operations with the 1C:Enterprise 8 platform. Dump/load configurations and extensions to/from XML, build/unpack external data processors (.epf/.erf), dump/load infobases, create infobases, check configuration, merge/compare configurations, work with configuration properties. Use when you need to: work with a 1C configuration or extensions, build or unpack a data processor/report, dump or load an infobase, run 1C:Enterprise or Configurator."
---

# 1c-batch

Cross-platform Python tool for batch operations with the 1C:Enterprise 8 platform.

## Run

Run **from the project root** (where `.1c-devbase.json` lives).

In this project the tool runs through a **local-copy wrapper** - that way the version
from `.claude/skills` is used, not the globally installed one:

```bash
python .claude/skills/1c-batch/scripts/1c-batch.py <команда> [аргументы] [опции]
```

Below, examples write `1c-batch <команда>` for brevity - it is the same command;
substitute the wrapper call above. (The global pip command `1c-batch`, if installed,
runs an instance shared by all projects - not the project copy.)

---

## Working with data processors (EPF/ERF)

### dump-epf - unpack a data processor to XML

```bash
1c-batch dump-epf <XML_DIR> <EPF_FILE> [--format Plain|Hierarchical]
```

- `XML_DIR` - directory for the XML dump
- `EPF_FILE` - path to the source `.epf` or `.erf` data processor
- `--format` - dump format (Plain or Hierarchical)

### build-epf - build a data processor from XML

```bash
1c-batch build-epf <XML_DIR> <EPF_FILE>
```

- `XML_DIR` - directory with XML sources
- `EPF_FILE` - path to the resulting `.epf` or `.erf` file

---

## Working with configuration

### dump-config - dump configuration to XML

```bash
1c-batch dump-config <DIRECTORY> [--update] [--extension ИМЯ] [--all-extensions] [--format Plain|Hierarchical]
```

- `DIRECTORY` - dump directory
- `--update` - incremental dump (changes only, with -force)
- `--extension` - dump a specific extension
- `--all-extensions` - dump all extensions
- `--format` - dump format

### load-config - load configuration from XML

```bash
1c-batch load-config <DIRECTORY> [--files СПИСОК] [--list-file ФАЙЛ] [--format Plain|Hierarchical] [--partial] [--extension ИМЯ] [--skip-db-update]
```

- `DIRECTORY` - directory with XML files
- `--files` - comma-separated list of files for partial load
- `--list-file` - path to the list file
- `--format` - format (Plain or Hierarchical)
- `--partial` - partial load
- `--extension` - load into an extension
- `--skip-db-update` - do not update the DB configuration (updated by default)

Examples:
```bash
# Полная загрузка
1c-batch load-config src/cf

# Частичная загрузка одного модуля
1c-batch load-config src/cf --files "CommonModules/МойМодуль/Ext/Module.bsl"

# Загрузка без обновления БД
1c-batch load-config src/cf --skip-db-update
```

### dump-cfg - save configuration to .cf

```bash
1c-batch dump-cfg <FILEPATH> [--extension ИМЯ]
```

### load-cfg - load configuration from .cf

```bash
1c-batch load-cfg <FILEPATH> [--extension ИМЯ]
```

### update-db-cfg - update the DB configuration

```bash
1c-batch update-db-cfg [--dynamic +|-] [--server] [--extension ИМЯ]
```

---

## Working with extensions

### dump-extension - dump an extension to XML

```bash
1c-batch dump-extension <DIRECTORY> --name ИМЯ [--update] [--format Plain|Hierarchical]
```

### load-extension - load an extension from XML

```bash
1c-batch load-extension <DIRECTORY> --name ИМЯ [--skip-db-update]
```

By default, after loading, the extension is updated in the DB.

### dump-cfg-extension - save an extension to .cfe

```bash
1c-batch dump-cfg-extension <FILEPATH> --name ИМЯ
```

### load-cfg-extension - load an extension from .cfe

```bash
1c-batch load-cfg-extension <FILEPATH> --name ИМЯ
```

### delete-extension - delete an extension

```bash
1c-batch delete-extension --name ИМЯ
1c-batch delete-extension --all
```

### list-extensions - list extensions

```bash
1c-batch list-extensions
```

---

## Running 1C

### run-enterprise - start 1C:Enterprise

```bash
1c-batch run-enterprise [EPF_FILE] [-C СТРОКА]
```

- `EPF_FILE` - data processor to auto-run (optional)
- `-C`, `--c` - value of the `/C` launch parameter, passed to the configuration
  (`ПараметрЗапуска`). The value is not quoted manually - the OS does the quoting.

```bash
# Запуск с параметром /C (например, автозапуск юнит-тестов)
1c-batch run-enterprise -C "ВыполнитьЗапускЮнитТестов=/abs/configs/test.json"
```

### run-designer - start Configurator

```bash
1c-batch run-designer
```

---

## Database

### dump-ib - dump the infobase to .dt

```bash
1c-batch dump-ib <FILEPATH>
```

### restore-ib - restore the infobase from .dt

```bash
1c-batch restore-ib <FILEPATH> [--jobs-count N]
```

### create-infobase - create an infobase

```bash
1c-batch create-infobase --path /путь/к/базе [--add-to-list ИМЯ] [--use-template ШАБЛОН]
```

### ib-restore-integrity - restore the infobase structure

```bash
1c-batch ib-restore-integrity
```

### ib-check-and-repair - test and repair the infobase

```bash
1c-batch ib-check-and-repair [--reindex] [--log-integrity] [--recalc-totals] [--ib-compression] [--rebuild]
```

---

## Checks

### check-config - check the configuration

```bash
1c-batch check-config [--config-log-integrity] [--incorrect-references] [--thin-client] [--server] [--extension ИМЯ] [--all-extensions]
```

### check-modules - check modules

```bash
1c-batch check-modules [--thin-client] [--server] [--extension ИМЯ] [--all-extensions]
```

---

## Comparison and merging

### merge-cfg - merge configurations

```bash
1c-batch merge-cfg <FILEPATH> [--settings ФАЙЛ_НАСТРОЕК] [--force]
```

### compare-cfg - compare configurations

```bash
1c-batch compare-cfg --first-type ТИП --second-type ТИП [--report-format ФОРМАТ] [--report-file ФАЙЛ]
```

---

## Configuration properties

### dump-config-files - dump properties

```bash
1c-batch dump-config-files <DIRECTORY> [--module] [--template] [--help-flag] [--all-writable] [--picture] [--right] [--extension ИМЯ]
```

### load-config-files - load properties

```bash
1c-batch load-config-files <DIRECTORY> [--module] [--template] [--help-flag] [--all-writable] [--picture] [--right] [--extension ИМЯ]
```

---

## Maintenance

### reduce-event-log - reduce the event log

```bash
1c-batch reduce-event-log <ДАТА>
```

- `ДАТА` - date in YYYYMMDD format

---

## Usage scenarios

### Fix a bug in a data processor

1. Unpack: `1c-batch dump-epf src/epf/МояОбработка.xml Исходная.epf`
2. Edit the BSL files in `src/epf/МояОбработка/`
3. Build: `1c-batch build-epf src/epf/МояОбработка.xml build/МояОбработка.epf`
4. Check: `1c-batch run-enterprise build/МояОбработка.epf`

### Load a modified module

```bash
1c-batch load-config src/cf --files "CommonModules/МойМодуль/Ext/Module.bsl"
```

### Update an extension

1. Dump: `1c-batch dump-extension src/cfe/МоёРасширение --name МоёРасширение`
2. Make changes to the XML files
3. Load: `1c-batch load-extension src/cfe/МоёРасширение --name МоёРасширение`

### Dump/load the infobase (backup)

1. Dump: `1c-batch dump-ib backup.dt`
2. Load: `1c-batch restore-ib backup.dt`

### Save configuration to .cf

```bash
1c-batch dump-cfg backup.cf
1c-batch load-cfg backup.cf
```

---

## Usage rules

**When dumping a configuration or extension:** if the user did not explicitly specify the dump type (full or incremental), ask before executing:
- Full dump - dumps all objects from scratch
- Incremental (`--update`) - dumps only changed objects (faster)

---

## Important

- **Data processors:** the first argument is the XML directory, the second is the .epf/.erf file
- **Configuration/extensions:** the first argument is the directory
- On error - non-zero return code
- Logs are saved in the `logs/` directory
- Connection configuration is in `.1c-devbase.json` in the project root
