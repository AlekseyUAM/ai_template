"""API-роутер справочника MCP: CRUD, пресеты, подъём docker, скачивание расширения."""
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, StreamingResponse

from .mcp_catalog import CATALOG
from .mcp_types import types_payload, get_type
from .mcp_docker_recipes import recipe_for, launch_params, container_name
from . import mcp_docker


def build_mcp_router(store) -> APIRouter:
    """Строит APIRouter для /api/mcp/*.

    store — объект Db (P1.1) или None.
    Если store is None, все операции с БД возвращают 503.
    /api/mcp/standard работает всегда.
    """
    router = APIRouter()

    def require_repo():
        if store is None:
            raise HTTPException(status_code=503, detail="хранилище не настроено")
        from agentmon.store.mcp import McpRepo
        return McpRepo(store)

    # ── пресеты каталога ────────────────────────────────────────────────────
    @router.get("/api/mcp/standard")
    def list_standard():
        result = []
        for key, spec in CATALOG.items():
            result.append({
                "id": spec.id,
                "title": spec.title,
                "kind": spec.kind,
                "default_port": spec.default_port,
                "needs_token": spec.needs_token,
                "download": spec.download,
            })
        return {"standard": result}

    # ── виды MCP для справочника ─────────────────────────────────────────────
    @router.get("/api/mcp/types")
    def list_types():
        return {"types": types_payload()}

    # ── список всех MCP ─────────────────────────────────────────────────────
    @router.get("/api/mcp")
    def list_mcp():
        repo = require_repo()
        return {"mcp": repo.list()}

    # ── создать MCP ─────────────────────────────────────────────────────────
    @router.post("/api/mcp")
    def create_mcp(body: dict):
        repo = require_repo()
        name = body.get("name") or ""
        if not name:
            raise HTTPException(status_code=400, detail="не задано поле name")

        standard_key = body.get("standard_key")
        kind = body.get("kind")
        purpose = body.get("purpose", "")
        connection_json = body.get("connection_json")
        port = body.get("port")
        token_env = body.get("token_env")
        mcp_name = body.get("mcp_name")
        url = body.get("url")
        db_name = body.get("db_name")
        catalog_dir = body.get("catalog_dir")
        platform_path = body.get("platform_path")

        # если standard_key передан и kind не указан — взять из каталога
        if standard_key and standard_key in CATALOG and not kind:
            spec = CATALOG[standard_key]
            kind = spec.kind
            if not port:
                port = spec.default_port
            if not token_env and spec.needs_token:
                token_env = None   # оставим пустым, пользователь задаст позже
            if not purpose:
                purpose = spec.title

        if not kind:
            kind = "custom"

        mid = repo.add(
            name=name,
            purpose=purpose,
            kind=kind,
            standard_key=standard_key,
            connection_json=connection_json,
            port=port,
            token_env=token_env,
            mcp_name=mcp_name,
            url=url,
            db_name=db_name,
            catalog_dir=catalog_dir,
            platform_path=platform_path,
        )
        row = repo.get(mid)
        return {"mcp": row}

    # ── обновить MCP ─────────────────────────────────────────────────────────
    @router.put("/api/mcp/{mid}")
    def update_mcp(mid: int, body: dict):
        repo = require_repo()
        if repo.get(mid) is None:
            raise HTTPException(status_code=404, detail=f"нет MCP с id={mid}")
        allowed = {"name", "purpose", "kind", "standard_key",
                   "connection_json", "port", "token_env",
                   "mcp_name", "url", "db_name", "catalog_dir", "platform_path"}
        fields = {k: v for k, v in body.items() if k in allowed}
        repo.update(mid, **fields)
        return {"mcp": repo.get(mid)}

    # ── удалить MCP ──────────────────────────────────────────────────────────
    @router.delete("/api/mcp/{mid}")
    def delete_mcp(mid: int):
        repo = require_repo()
        row = repo.get(mid)
        if row is None:
            raise HTTPException(status_code=404, detail=f"нет MCP с id={mid}")
        # контейнер намеренно не трогаем: удаление из справочника убирает только
        # карточку, docker-контейнер остаётся (останавливать его — отдельное действие)
        repo.delete(mid)
        return {"ok": True}

    def _resolve_docker(mid: int, body: dict) -> dict:
        """Валидирует и собирает контекст запуска docker-вида MCP.

        Бросает HTTPException при ошибке ввода. Возвращает dict с полями:
        name, image, port, params, build_spec, need_build, repo_root.
        """
        repo = require_repo()
        row = repo.get(mid)
        if row is None:
            raise HTTPException(status_code=404, detail=f"нет MCP с id={mid}")

        # расширение не поднимается через docker
        if row.get("kind") == "extension" or row.get("standard_key") == "1c-md":
            raise HTTPException(status_code=400, detail="это расширение, скачайте cfe")

        type_key = row.get("standard_key")
        recipe = recipe_for(type_key)
        if recipe is None:
            raise HTTPException(status_code=400,
                                detail="для этого вида MCP нет docker-рецепта")

        port = body.get("port") or row.get("port")
        if not port:
            try:
                port = get_type(type_key).defaults.get("port")
            except KeyError:
                port = None
        if not port:
            raise HTTPException(status_code=400, detail="не задан порт")
        port = int(port)

        repo_root = Path(__file__).resolve().parents[4]  # app/ -> ai_template/
        state_dir = repo_root / ".ai1c" / "mcp-state" / str(mid)
        try:
            params = launch_params(
                type_key, port=port, token=body.get("token") or row.get("token_env"),
                catalog_dir=row.get("catalog_dir"), state_dir=str(state_dir),
                platform_path=row.get("platform_path"),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        return {
            "name": container_name(row),
            "image": params["image"],
            "port": port,
            "params": params,
            "build_spec": recipe.build,
            "need_build": not mcp_docker.image_exists(params["image"]),
            "repo_root": repo_root,
        }

    # ── подъём MCP (блокирующе, лог целиком) ──────────────────────────────────
    @router.post("/api/mcp/{mid}/launch")
    def launch_mcp(mid: int, body: dict):
        ctx = _resolve_docker(mid, body)
        log_parts: list[str] = []

        if ctx["need_build"]:
            b = ctx["build_spec"]
            if b is None:
                return {"ok": False,
                        "log": f"образ {ctx['image']} не найден; сборка недоступна — "
                               "соберите образ заранее"}
            rr = ctx["repo_root"]
            res_b = mcp_docker.build(ctx["image"], str(rr / b.dockerfile),
                                     str(rr / b.context), build_args=b.build_args)
            log_parts.append(res_b.get("log", ""))
            if not res_b["ok"]:
                return {"ok": False, "log": "\n".join(p for p in log_parts if p)}

        p = ctx["params"]
        res = mcp_docker.launch(name=ctx["name"], image=ctx["image"], port=ctx["port"],
                                internal_port=p["internal_port"],
                                env=p["env"], volumes=p["volumes"],
                                network=p.get("network"))
        log_parts.append(res.get("log", ""))
        res["log"] = "\n".join(x for x in log_parts if x)
        return res

    # ── подъём MCP со стримингом лога (сборка + запуск построчно) ──────────────
    @router.post("/api/mcp/{mid}/launch/stream")
    def launch_mcp_stream(mid: int, body: dict):
        ctx = _resolve_docker(mid, body)
        name, image, port, p = ctx["name"], ctx["image"], ctx["port"], ctx["params"]
        rr, b, need_build = ctx["repo_root"], ctx["build_spec"], ctx["need_build"]

        run_c = mcp_docker.launch_cmd(name, image, port,
                                      internal_port=p["internal_port"],
                                      env=p["env"], volumes=p["volumes"],
                                      network=p.get("network"))
        build_c = None
        if need_build and b is not None:
            build_c = mcp_docker.build_cmd(image, str(rr / b.dockerfile),
                                           str(rr / b.context), build_args=b.build_args)

        def _stream(cmd):
            """Отдаёт строки команды, возвращает код возврата через list-holder."""
            for line in mcp_docker.iter_output(cmd):
                code = mcp_docker.is_rc(line)
                if code is not None:
                    _stream.rc = code
                    continue
                yield line + "\n"
        _stream.rc = None

        def gen():
            yield f"▶ Развёртывание «{name}» (образ {image}, порт {port})\n"
            if need_build and b is None:
                yield (f"✗ образ {image} не найден; для этого вида сборка недоступна — "
                       "соберите образ заранее\n")
                return
            # снять прежний контейнер с тем же именем (тихо)
            for _ in mcp_docker.iter_output(["docker", "rm", "-f", name]):
                pass
            if build_c is not None:
                yield "\n=== Сборка образа ===\n"
                yield from _stream(build_c)
                if _stream.rc != 0:
                    yield f"\n✗ Ошибка сборки (код {_stream.rc})\n"
                    return
                yield "✓ Образ собран\n"
            yield "\n=== Запуск контейнера ===\n"
            yield from _stream(run_c)
            if _stream.rc == 0:
                yield f"\n✓ Контейнер запущен (http://127.0.0.1:{port})\n"
            else:
                yield f"\n✗ Ошибка запуска (код {_stream.rc})\n"

        return StreamingResponse(gen(), media_type="text/plain; charset=utf-8")

    # ── остановить MCP ───────────────────────────────────────────────────────
    @router.post("/api/mcp/{mid}/stop")
    def stop_mcp(mid: int):
        repo = require_repo()
        row = repo.get(mid)
        if row is None:
            raise HTTPException(status_code=404, detail=f"нет MCP с id={mid}")
        result = mcp_docker.stop(container_name(row))
        return result

    # ── скачать расширение ───────────────────────────────────────────────────
    @router.get("/api/mcp/{mid}/download")
    def download_mcp(mid: int):
        repo = require_repo()
        row = repo.get(mid)
        if row is None:
            raise HTTPException(status_code=404, detail=f"нет MCP с id={mid}")

        # путь к cfe берём из описания вида MCP (хранится в standard_key)
        standard_key = row.get("standard_key")
        rel = None
        try:
            t = get_type(standard_key)
            if t.action == "cfe":
                rel = t.cfe_path
        except KeyError:
            rel = None
        # обратная совместимость: старые записи 1c-md без вида в справочнике
        if rel is None and standard_key == "1c-md":
            rel = CATALOG["1c-md"].download
        if rel is None:
            raise HTTPException(status_code=404, detail="скачивание недоступно")

        # ищем от корня репозитория (несколько уровней вверх), затем от app/
        base = Path(__file__).resolve().parents[4]  # app/ -> ai_template/
        cfe_path = base / rel
        if not cfe_path.exists():
            cfe_path = Path(__file__).resolve().parents[3] / rel  # src/ -> app/
        if not cfe_path.exists():
            raise HTTPException(status_code=404, detail="файл расширения не найден")

        return FileResponse(str(cfe_path), filename=Path(rel).name)

    return router
