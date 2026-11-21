#!/usr/bin/env python3
"""Одна команда подготовки benchmark-окружения AgentMon.

Запуск из корня репозитория (после python bootstrap.py):

    .venv/bin/python benchmark/setup_benchmark.py [--env benchmark/test.env]
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

_LOCK_MARK = "Ошибка исключительной блокировки информационной базы"


def run_setup_with_lock_retry(run_setup, *, attempts: int = 2,
                              delay: float = 30.0, sleep=time.sleep,
                              log=print):
    """Повторить `run_setup` при транзиентной блокировке ИБ.

    Повторяем только ошибки с маркером исключительной блокировки; остальные
    пробрасываем сразу. Проект пересоздаётся (`recreate=True`), поэтому
    частично созданный каталог не мешает повтору.
    """
    for attempt in range(1, attempts + 1):
        try:
            return run_setup()
        except Exception as exc:            # noqa: BLE001 — текст важнее типа
            if _LOCK_MARK not in str(exc) or attempt >= attempts:
                raise
            log(f"⚠ ИБ заблокирована — повтор setup "
                f"{attempt}/{attempts - 1} через {delay:g} с")
            sleep(delay)
    raise AssertionError("недостижимо")


def load_repo_env() -> None:
    """Прочитать .ai1c.env в os.environ до импорта agentmon.config.

    Семантика как у run.py: значения файла перезаписывают уже заданные ключи.
    """
    sys.path.insert(0, str(ROOT / "app" / "src"))
    try:
        from agentmon.env.bench_setup import load_env_file
    finally:
        sys.path.remove(str(ROOT / "app" / "src"))
    load_env_file(ROOT / ".ai1c.env", os.environ)


def docker_problem(timeout: float = 10.0) -> str | None:
    """Проверить доступность демона Docker.

    Возвращает None, если демон отвечает, иначе — короткое описание проблемы.
    Вызов ограничен таймаутом: `docker info` не должен подвешивать скрипт,
    пока Docker Desktop ещё стартует.
    """
    try:
        result = subprocess.run(
            ["docker", "info"], stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, timeout=timeout)
    except FileNotFoundError:
        return "не найден CLI docker (установите Docker Desktop)"
    except subprocess.TimeoutExpired:
        return f"демон не ответил за {timeout:g} с"
    except OSError as exc:
        return f"не удалось запустить docker: {exc}"
    if result.returncode != 0:
        return "демон не отвечает (docker info завершился с ошибкой)"
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Подготовка benchmark-окружения AgentMon")
    parser.add_argument(
        "--env", default=str(ROOT / "benchmark" / "test.env"),
        help="путь к test.env (по умолчанию benchmark/test.env)")
    args = parser.parse_args(argv)

    os.chdir(ROOT)
    load_repo_env()

    try:
        from agentmon import config
        from agentmon.backends.local import LocalProvisioner
        from agentmon.env.bench_setup import (SetupError, load_config,
                                               run_setup)
        from agentmon.registry import ProjectRegistry, open_db
        from agentmon.store.db import connect
        from agentmon.store.schema import init_schema
    except ModuleNotFoundError as exc:
        print(f"✗ не удалось импортировать agentmon: {exc}", file=sys.stderr)
        print("Запустите из .venv репозитория: python bootstrap.py",
              file=sys.stderr)
        return 1

    env_path = Path(args.env).expanduser()
    if not env_path.is_absolute():
        env_path = ROOT / env_path

    try:
        cfg = load_config(env_path, repo_root=ROOT)
    except SetupError as exc:
        print(f"✗ {exc}", file=sys.stderr)
        return 1

    problem = docker_problem()
    if problem:
        print(f"✗ Docker недоступен: {problem}", file=sys.stderr)
        print("  benchmark-окружение поднимает MCP-серверы и code_index "
              "в Docker,", file=sys.stderr)
        print("  поэтому подготовка без Docker невозможна. Запустите "
              "Docker Desktop", file=sys.stderr)
        print("  и повторите запуск.", file=sys.stderr)
        return 1

    # libpq без таймаута может ждать недоступную БД бесконечно: например,
    # когда Docker остановлен, а порт 5432 ещё держит прокси Docker Desktop.
    os.environ.setdefault("PGCONNECT_TIMEOUT", "10")

    try:
        store = connect(config.DSN)
        init_schema(store)
    except Exception as exc:                           # noqa: BLE001
        print(f"✗ не удалось открыть store {config.DSN}: {exc}",
              file=sys.stderr)
        if (os.environ.get("AI1C_PG_MODE") or "").strip().lower() == "docker":
            print("  PostgreSQL настроена в Docker (AI1C_PG_MODE=docker): "
                  "проверьте,", file=sys.stderr)
            print("  что контейнер ai1c-postgres запущен.", file=sys.stderr)
        return 1
    try:
        registry = ProjectRegistry(open_db(config.DB_PATH))
    except Exception as exc:                           # noqa: BLE001
        print(f"✗ не удалось открыть реестр {config.DB_PATH}: {exc}",
              file=sys.stderr)
        return 1

    try:
        result = run_setup_with_lock_retry(
            lambda: run_setup(
                cfg, repo_root=ROOT, store=store, registry=registry,
                prov=LocalProvisioner(), recreate=True),
            log=print)
    except SetupError as exc:
        print(f"✗ {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("✗ прервано пользователем", file=sys.stderr)
        return 130

    print("\n✓ Готово")
    print(f"  проект:      #{result.project_id} {cfg.project_name}")
    print(f"  каталог:     {result.project_dir}")
    print(f"  задачи:      {', '.join(f'#{tid}' for tid in result.task_ids)}")
    print(f"  code_index:  {result.container} "
          f"(порт {cfg.code_index_port})")
    print(f"  bsl_ls:      {cfg.bsl_ls_url}")
    print(f"  1c_platform: {cfg.platform_url}")
    if cfg.one_c_md_url:
        print(f"  1c-md:       {cfg.one_c_md_url}")
    if cfg.one_c_naparnic_url:
        print(f"  1c_naparnic: {cfg.one_c_naparnic_url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
