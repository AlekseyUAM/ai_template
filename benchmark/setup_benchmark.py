#!/usr/bin/env python3
"""Одна команда подготовки benchmark-окружения AgentMon.

Запуск из корня репозитория (после python bootstrap.py):

    .venv/bin/python benchmark/setup_benchmark.py [--env benchmark/test.env]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

# Windows-консоль часто cp1251/cp866: «✓» и «→» в логах роняют print.
# line_buffering — прогресс виден сразу и при перенаправлении вывода в файл:
# docker-размещение идёт минутами, буфер 8 КБ скрывал ход установки.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace",
                            line_buffering=True)
    except (AttributeError, ValueError):
        pass

ROOT = Path(__file__).resolve().parents[1]

_LOCK_MARK = "Ошибка исключительной блокировки информационной базы"

# Ключи профиля, которые печатаем после записи settings.local.json.
_SETTINGS_SUMMARY_KEYS = (
    "CLAUDE_CODE_EFFORT_LEVEL",
    "MAX_MCP_OUTPUT_TOKENS",
    "BASH_MAX_OUTPUT_LENGTH",
    "CLAUDE_CODE_MAX_OUTPUT_TOKENS",
    "CLAUDE_CODE_AUTO_COMPACT_WINDOW",
)


def settings_summary(settings: dict) -> str:
    """Короткая строка действующего профиля (без секретов)."""
    env = settings.get("env") if isinstance(settings, dict) else None
    if not isinstance(env, dict):
        return "—"
    return ", ".join(f"{key}={env[key]}" for key in _SETTINGS_SUMMARY_KEYS
                     if key in env)


def apply_settings(cfg, *, fetch=None, build=None, write=None, log=print):
    """Записать settings.local.json в существующий проект без пересоздания.

    Профиль собирает `build_strata_settings` из `agentmon.env.bench_setup`
    (умеренные лимиты вывода, claudeMdExcludes для review/test). Проект,
    store и реестр не трогаются — это безопасный способ обновить настройки
    после сбоя setup.
    """
    from agentmon.env.bench_setup import (
        SetupError, build_strata_settings, fetch_strata_env,
        write_strata_settings)
    if not cfg.strata_settings:
        raise SetupError(
            "BENCH_STRATA_SETTINGS=1 не задан: профиль настроек не из чего "
            "собрать. Включите его в test.env или настройте "
            "settings.local.json вручную.")
    if getattr(cfg, "placement", "local") == "docker":
        env = (fetch or fetch_strata_env)(cfg.strata_cmd)
        settings = (build or build_strata_settings)(env)
        log(f"  профиль: {settings_summary(settings)}")
        from bench_docker import write_text
        path = f"{cfg.project_dir}/.claude/settings.local.json"
        write_text(cfg.project_dir, path,
                   json.dumps(settings, ensure_ascii=False, indent=2) + "\n")
        log(f"✓ настройки записаны в контейнер: {path}")
        return Path(path)
    if not Path(cfg.project_dir).is_dir():
        raise SetupError(f"каталог проекта не найден: {cfg.project_dir}")
    env = (fetch or fetch_strata_env)(cfg.strata_cmd)
    settings = (build or build_strata_settings)(env)
    log(f"  профиль: {settings_summary(settings)}")
    return (write or write_strata_settings)(cfg.project_dir, settings, log=log)


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


class _DockerOps:
    """Операции docker-размещения, которые нужны установщику.

    Проект лежит в томе контейнера (`/workspace`), файлов на хосте нет:
    задачи заливаются в контейнер, code-index запускается внутри.
    """

    def __init__(self, project_dir, repo_root, image, host_cmd):
        self.project_dir = str(project_dir)
        self.repo_root = repo_root
        self.image = image
        self.host_cmd = host_cmd

    def container(self):
        from bench_docker import container_for
        return container_for(self.project_dir, self.repo_root,
                             self.image, self.host_cmd)

    def remove_project(self, project_dir, log=print):
        from bench_docker import remove_project
        remove_project(project_dir)

    def push_tree(self, local_src, dst):
        from bench_docker import copy_tree_in
        copy_tree_in(self.project_dir, Path(local_src), dst)

    def prepare_project(self):
        """Создать контейнер с чистыми томами и отдать их пользователю.

        Вызывается после remove_project: Docker создаёт корень тома от root,
        поэтому нужен chown, иначе установка не сможет писать в /workspace.
        """
        from bench_docker import fix_ownership
        self.container().ensure()
        fix_ownership(self.project_dir)

    def start_index(self, *, code_index_dir, catalog_dir, alias, port,
                    host="127.0.0.1", run=None, log=print):
        from bench_docker import start_code_index
        return start_code_index(
            self.project_dir, code_index_dir=code_index_dir,
            catalog_dir=catalog_dir, alias=alias, port=port, host=host,
            log=log)

    def wait_index(self, index, *, wait_minutes, host, port, run=None,
                   sleep=None, clock=None, log=print):
        import time
        from bench_docker import wait_code_index_ready
        return wait_code_index_ready(
            index, project_dir=self.project_dir, wait_minutes=wait_minutes,
            host=host, port=port, sleep=sleep or time.sleep,
            clock=clock or time.monotonic, log=log)

    def kill_leftovers(self):
        """Погасить code-index и агента в старом контейнере перед удалением."""
        from bench_docker import kill_agent, stop_code_index
        try:
            stop_code_index(self.project_dir)
            kill_agent(self.project_dir)
        except Exception:                               # noqa: BLE001
            pass

    def write_settings(self, settings):
        """Записать .claude/settings.local.json внутрь контейнера."""
        from bench_docker import write_text
        write_text(self.project_dir,
                   f"{self.project_dir}/.claude/settings.local.json",
                   json.dumps(settings, ensure_ascii=False, indent=2) + "\n")
        print(f"✓ настройки Strata записаны в контейнер: "
              f"{self.project_dir}/.claude/settings.local.json")


def _docker_provisioner(cfg):
    """(provisioner, docker_ops) для benchmark-проекта в контейнере."""
    from agentmon.backends.docker import DockerProvisioner
    from bench_docker import host_argv, image_present

    image = cfg.docker_image
    if not image_present(image):
        raise SetupError(
            f"образ {image} не найден в Docker. Соберите его в мастере "
            "AgentMon (бэкенд «В Docker-контейнере») или через docker build "
            "app/docker/agent-image/Dockerfile.")
    host_cmd = None
    if cfg.claude_cmd:
        try:
            host_cmd = host_argv(cfg.claude_cmd)
        except FileNotFoundError:
            print(f"⚠ команда агента не найдена ({cfg.claude_cmd}): обёртка "
                  "не будет смонтирована в контейнер", file=sys.stderr)
    ops = _DockerOps(cfg.project_dir, ROOT, image, host_cmd)
    container = ops.container()
    print(f"✓ Docker: контейнер {container.name}, образ {image}, "
          f"проект в томе {container.name}-work:{cfg.project_dir}")
    return DockerProvisioner(container, workdir=cfg.project_dir), ops


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Подготовка benchmark-окружения AgentMon")
    parser.add_argument(
        "--env", default=str(ROOT / "benchmark" / "test.env"),
        help="путь к test.env (по умолчанию benchmark/test.env)")
    parser.add_argument(
        "--settings-only", action="store_true",
        help="только записать <проект>/.claude/settings.local.json "
             "и выйти, не пересоздавая проект (нужен BENCH_STRATA_SETTINGS=1)")
    args = parser.parse_args(argv)

    os.chdir(ROOT)
    load_repo_env()

    try:
        from agentmon import config
        from agentmon.backends.local import LocalProvisioner
        from agentmon.env.bench_setup import (SetupError, build_strata_settings,
                                               fetch_strata_env, load_config,
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

    if args.settings_only:
        try:
            path = apply_settings(cfg)
        except SetupError as exc:
            print(f"✗ {exc}", file=sys.stderr)
            return 1
        print(f"✓ настройки записаны: {path}")
        return 0

    strata_env = None
    strata_settings = None
    if cfg.strata_settings:
        try:
            strata_env = fetch_strata_env(cfg.strata_cmd)
            strata_settings = build_strata_settings(strata_env)
        except SetupError as exc:
            print(f"✗ {exc}", file=sys.stderr)
            return 1
        print(f"✓ Strata: модель {strata_env.get('ANTHROPIC_MODEL', '—')}, "
              f"контекст "
              f"{strata_env.get('CLAUDE_CODE_MAX_CONTEXT_TOKENS', '—')}")
        print(f"  профиль: {settings_summary(strata_settings)}")

    problem = docker_problem()
    if problem:
        print(f"✗ Docker недоступен: {problem}", file=sys.stderr)
        print("  MCP-серверы benchmark (bsl_ls, 1c_platform) запускаются "
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

    prov = LocalProvisioner()
    docker_ops = None
    index_kwargs = {}
    if cfg.placement == "docker":
        try:
            prov, docker_ops = _docker_provisioner(cfg)
        except SetupError as exc:
            print(f"✗ {exc}", file=sys.stderr)
            return 1
        index_kwargs = {"launch_index": docker_ops.start_index,
                        "wait_index": docker_ops.wait_index}

    try:
        result = run_setup_with_lock_retry(
            lambda: run_setup(
                cfg, repo_root=ROOT, store=store, registry=registry,
                prov=prov, strata_env=strata_env,
                strata_settings=strata_settings, recreate=True,
                docker_ops=docker_ops, **index_kwargs),
            log=print)
    except SetupError as exc:
        print(f"✗ {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("✗ прервано пользователем", file=sys.stderr)
        return 130

    print("\n✓ Готово")
    print(f"  проект:      #{result.project_id} {cfg.project_name}")
    print(f"  размещение:  {cfg.placement}"
          + (f" (образ {cfg.docker_image})" if cfg.placement == "docker" else ""))
    print(f"  каталог:     {result.project_dir}")
    print(f"  задачи:      {', '.join(f'#{tid}' for tid in result.task_ids)}")
    print(f"  code_index:  {result.code_index} (native)")
    print(f"  bsl_ls:      {cfg.bsl_ls_url}")
    print(f"  1c_platform: {cfg.platform_url}")
    if cfg.one_c_md_url:
        print(f"  1c-md:       {cfg.one_c_md_url}")
    if cfg.one_c_naparnic_url:
        print(f"  1c_naparnic: {cfg.one_c_naparnic_url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
