# app/src/agentmon/env/api.py
from dataclasses import asdict

from fastapi import APIRouter, HTTPException

from .config_schema import EnvConfig
from .installer import install_environment


def build_env_router(registry) -> APIRouter:
    router = APIRouter()

    def register(config: EnvConfig) -> None:
        for p in registry.list():
            if p.path == config.project_dir:
                return                  # уже зарегистрирован — идемпотентно
        registry.add(name=config.project_name, path=config.project_dir,
                     backend="local", conn=None, claude_cmd=None)

    @router.post("/api/environment/create")
    def create_environment(body: dict):
        try:
            config = EnvConfig.from_dict(body["config"])
        except (KeyError, TypeError) as exc:
            raise HTTPException(status_code=400, detail=f"плохой config: {exc}")
        events = list(install_environment(
            config,
            update=bool(body.get("update")),
            register=register,
            dump_cf=bool(body.get("dump_cf")),
            dump_cfe=bool(body.get("dump_cfe")),
            install_tools=bool(body.get("install_tools")),
        ))
        ok = bool(events) and events[-1].status == "ok"
        return {"ok": ok, "events": [asdict(e) for e in events]}

    return router
