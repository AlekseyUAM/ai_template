"""Переносимая схема БД Фазы 1 (sqlite/postgres)."""


def init_schema(db) -> None:
    pk = db.autopk()
    ts = "DOUBLE PRECISION"     # в sqlite получает REAL-аффинность, в postgres — float8
    db.execute(f"""CREATE TABLE IF NOT EXISTS projects (
        id {pk}, name TEXT NOT NULL UNIQUE, path TEXT NOT NULL UNIQUE,
        identifier TEXT, email TEXT, platform_dir TEXT, platform_version TEXT,
        db_kind TEXT, db_connection TEXT, web_publication TEXT,
        env_version TEXT, created_at {ts})""")
    db.execute(f"""CREATE TABLE IF NOT EXISTS mcp_servers (
        id {pk}, name TEXT NOT NULL UNIQUE, purpose TEXT, kind TEXT NOT NULL,
        standard_key TEXT, connection_json TEXT, port INTEGER, token_env TEXT,
        mcp_name TEXT, url TEXT, db_name TEXT, catalog_dir TEXT, platform_path TEXT,
        created_at {ts})""")
    db.execute(f"""CREATE TABLE IF NOT EXISTS project_mcp (
        id {pk}, project_id INTEGER NOT NULL, mcp_id INTEGER NOT NULL,
        UNIQUE(project_id, mcp_id))""")
    db.execute(f"""CREATE TABLE IF NOT EXISTS tasks (
        id {pk}, project_id INTEGER NOT NULL, name TEXT NOT NULL,
        identifier TEXT, goal TEXT, plan TEXT, constraints TEXT, tests TEXT,
        stages_json TEXT, status TEXT NOT NULL DEFAULT 'planned',
        stage TEXT, started_at {ts}, finished_at {ts}, created_at {ts},
        kind TEXT NOT NULL DEFAULT 'real',
        update_db INTEGER NOT NULL DEFAULT 0,
        max_minutes INTEGER NOT NULL DEFAULT 60,
        interactive INTEGER NOT NULL DEFAULT 0,
        mark_changes INTEGER NOT NULL DEFAULT 0)""")
    db.execute(f"""CREATE TABLE IF NOT EXISTS stacks (
        id {pk}, name TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'idle',
        created_at {ts})""")
    db.execute(f"""CREATE TABLE IF NOT EXISTS stack_items (
        id {pk}, stack_id INTEGER NOT NULL, task_id INTEGER NOT NULL,
        position INTEGER NOT NULL,
        UNIQUE(task_id))""")
    db.execute(f"""CREATE TABLE IF NOT EXISTS runs (
        id {pk}, project_id INTEGER NOT NULL, task_id INTEGER, pid INTEGER NOT NULL,
        log_file TEXT, exit_file TEXT, status TEXT NOT NULL DEFAULT 'running',
        started_at {ts}, finished_at {ts}, exit_code INTEGER)""")

    # Миграции существующих БД: добавляем недостающие колонки идемпотентно.
    _ensure_columns(db, "mcp_servers", {
        "mcp_name": "TEXT", "url": "TEXT", "db_name": "TEXT",
        "catalog_dir": "TEXT", "platform_path": "TEXT",
    })
    _ensure_columns(db, "tasks", {
        "identifier": "TEXT",
        "update_db": "INTEGER DEFAULT 0",
        "max_minutes": "INTEGER DEFAULT 60",
        "interactive": "INTEGER DEFAULT 0",
        "mark_changes": "INTEGER DEFAULT 0",
    })

    _ensure_indexes(db)


def _ensure_indexes(db) -> None:
    """Индексы под частые выборки/каскадные удаления (идемпотентно).

    Переносимый SQL без partial-index-синтаксиса: CREATE INDEX IF NOT EXISTS
    поддержан и sqlite, и postgres. status в tasks есть всегда (NOT NULL DEFAULT),
    поэтому составной индекс (project_id, status) создаём безусловно.
    """
    indexes = [
        ("idx_tasks_project_id", "tasks(project_id)"),
        ("idx_tasks_project_id_status", "tasks(project_id, status)"),
        ("idx_runs_project_id", "runs(project_id)"),
        ("idx_runs_task_id", "runs(task_id)"),
        ("idx_runs_status", "runs(status)"),
        ("idx_stack_items_stack_id", "stack_items(stack_id)"),
        ("idx_project_mcp_project_id", "project_mcp(project_id)"),
        ("idx_project_mcp_mcp_id", "project_mcp(mcp_id)"),
    ]
    for name, target in indexes:
        db.execute(f"CREATE INDEX IF NOT EXISTS {name} ON {target}")


def _existing_columns(db, table: str) -> set[str]:
    if db.dialect == "sqlite":
        rows = db.query(f"PRAGMA table_info({table})")
        return {r["name"] for r in rows}
    rows = db.query(
        "SELECT column_name AS name FROM information_schema.columns "
        "WHERE table_name=?", [table])
    return {r["name"] for r in rows}


def _ensure_columns(db, table: str, columns: dict[str, str]) -> None:
    """Добавляет недостающие колонки в существующую таблицу (ADD COLUMN)."""
    have = _existing_columns(db, table)
    for col, coltype in columns.items():
        if col not in have:
            db.execute(f"ALTER TABLE {table} ADD COLUMN {col} {coltype}")
