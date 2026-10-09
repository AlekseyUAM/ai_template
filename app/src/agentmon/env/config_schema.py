from dataclasses import dataclass, asdict

SCHEMA_VERSION = 1


@dataclass
class McpSelection:
    id: str
    enabled: bool
    mode: str                       # "managed" | "external"
    endpoint: str | None = None     # external: url или команда
    secret_env: str | None = None   # managed: имя env-переменной с секретом
    connection: str | None = None   # фрагмент "<имя>": {...} из справочника MCP


@dataclass
class AgentModel:
    agent: str
    model: str
    effort: str


@dataclass
class EnvConfig:
    schema_version: int
    project_name: str
    project_dir: str
    developer_id: str
    developer_email: str
    platform_dir: str
    platform_version: str
    db_kind: str                    # "server" | "file"
    db_connection: str
    web_publication: str
    mcp: list[McpSelection]
    agents: list[AgentModel]

    def to_dict(self) -> dict:
        data = asdict(self)
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "EnvConfig":
        data = dict(data)
        data["mcp"] = [McpSelection(**m) for m in data.get("mcp", [])]
        data["agents"] = [AgentModel(**a) for a in data.get("agents", [])]
        return cls(**data)
