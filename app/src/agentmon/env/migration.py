from .config_schema import SCHEMA_VERSION


def _to_v1(data: dict) -> dict:
    # Версия 0 (конфиг без schema_version) → 1: просто проставляем версию.
    data["schema_version"] = 1
    return data


# Ключ — версия, С которой мигрируем; значение — функция до следующей версии.
_MIGRATIONS = {
    0: _to_v1,
}


def migrate(data: dict) -> dict:
    version = int(data.get("schema_version", 0))
    if version > SCHEMA_VERSION:
        raise ValueError(
            f"конфиг версии {version} новее поддерживаемой {SCHEMA_VERSION} — "
            "обновите приложение")
    while version < SCHEMA_VERSION:
        step = _MIGRATIONS.get(version)
        if step is None:
            raise ValueError(f"нет миграции с версии {version}")
        data = step(data)
        version = int(data["schema_version"])
    return data
