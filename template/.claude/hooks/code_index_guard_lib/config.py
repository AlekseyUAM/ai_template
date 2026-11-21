"""code-index-guard hook config (port of main.rs: GuardConfig and TOML parsers).

The format is TOML-like, parsed line by line: top-level
string keys and [[local]] / [[paths]] sections with path and alias keys are supported.
Full TOML is not needed, and parse errors are treated as "no settings":
without paths the hook intercepts nothing.
"""
import os
from dataclasses import dataclass, field
from pathlib import Path

from .paths import norm_prefix

DEFAULT_MCP_PREFIX = "mcp__code_index__"
# How many consecutive denials are allowed for one (session, tool, input) before
# letting the native call through. 0 - never yield (previous behavior).
DEFAULT_MAX_DENIES = 2


@dataclass
class GuardConfig:
    daemon_toml: str | None = None
    local: list[tuple[str, str]] = field(default_factory=list)
    mcp_prefix: str = DEFAULT_MCP_PREFIX
    max_denies: int = DEFAULT_MAX_DENIES


def guard_config_path() -> Path:
    env = os.environ.get("CODE_INDEX_GUARD_CONFIG")
    if env:
        return Path(env)
    return Path(__file__).resolve().parent.parent / "code-index-guard.toml"


def load_guard_config() -> GuardConfig:
    path = guard_config_path()
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        content = ""
    return GuardConfig(
        daemon_toml=parse_top_level_string(content, "daemon_toml"),
        local=parse_path_blocks(content, "[[local]]"),
        mcp_prefix=parse_top_level_string(content, "mcp_prefix") or DEFAULT_MCP_PREFIX,
        max_denies=parse_top_level_int(content, "max_denies", DEFAULT_MAX_DENIES),
    )


def daemon_toml_path(cfg: GuardConfig) -> str | None:
    return os.environ.get("CODE_INDEX_DAEMON_TOML") or cfg.daemon_toml


def indexed_paths(cfg: GuardConfig, *, case_insensitive: bool | None = None
                  ) -> list[tuple[str, str]]:
    """[(norm_prefix, alias)]: repos from daemon.toml, then [[local]] without duplicate paths.

    daemon.toml takes priority: its alias is kept when the path matches.
    """
    v: list[tuple[str, str]] = []
    seen: set[str] = set()
    path = daemon_toml_path(cfg)
    if path:
        try:
            content = Path(path).read_text(encoding="utf-8")
        except OSError:
            content = ""
        for p, a in parse_path_blocks(content, "[[paths]]"):
            norm = norm_prefix(p, case_insensitive)
            if norm and norm not in seen:
                seen.add(norm)
                v.append((norm, a))
    for p, a in cfg.local:
        norm = norm_prefix(p, case_insensitive)
        if norm and norm not in seen:
            seen.add(norm)
            v.append((norm, a))
    return v


def parse_path_blocks(content: str, header: str) -> list[tuple[str, str]]:
    """header sections (e.g. "[[local]]") -> [(path, alias)].

    alias defaults to the last path segment in lower case,
    spaces replaced with `_`.
    """
    out: list[tuple[str, str]] = []
    for block in content.split(header)[1:]:
        path: str | None = None
        alias: str | None = None
        for line in block.splitlines():
            l = line.strip()
            if l.startswith("["):
                break  # next section - end of block
            v = kv(l, "path")
            if v is not None:
                if path is None:
                    path = v
            else:
                v = kv(l, "alias")
                if v is not None and alias is None:
                    alias = v
        if path is not None:
            if alias is None:
                alias = (path.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
                         .lower().replace(" ", "_"))
            out.append((path, alias))
    return out


def kv(line: str, key: str) -> str | None:
    """Line `key = "value"` -> value without quotes and unescaped.

    Returns None if the line does not start with key: comments and keys nested
    in sections do not interfere with top-level parsing.
    """
    rest = line.lstrip()
    if not rest.startswith(key):
        return None
    rest = rest[len(key):].lstrip()
    if not rest.startswith("="):
        return None
    rest = rest[1:].lstrip()
    if not rest.startswith('"'):
        return None
    rest = rest[1:]
    # The closing quote is the first unescaped one.
    i = 0
    while i < len(rest):
        c = rest[i]
        if c == "\\":
            i += 2
            continue
        if c == '"':
            return unescape_toml(rest[:i])
        i += 1
    return None


def unescape_toml(s: str) -> str:
    """`\\` -> `\\`, `\"` -> `"`, `\\/` -> `/`; other sequences as is."""
    out: list[str] = []
    i = 0
    while i < len(s):
        c = s[i]
        if c != "\\":
            out.append(c)
            i += 1
            continue
        nxt = s[i + 1] if i + 1 < len(s) else None
        if nxt is None:
            out.append("\\")
            i += 1
        elif nxt in "\\\"/":
            out.append(nxt)
            i += 2
        else:
            out.append("\\")
            out.append(nxt)
            i += 2
    return "".join(out)


def parse_top_level_string(content: str, key: str) -> str | None:
    """First value of top-level key `key = "value"`."""
    for line in content.splitlines():
        v = kv(line.strip(), key)
        if v is not None:
            return v
    return None


def parse_top_level_int(content: str, key: str, default: int) -> int:
    """First integer value of top-level key `key = N` (negative -> 0)."""
    for line in content.splitlines():
        rest = line.strip()
        if not rest.startswith(key):
            continue
        rest = rest[len(key):].lstrip()
        if not rest.startswith("="):
            continue
        value = rest[1:].strip().split("#", 1)[0].strip()
        try:
            return max(0, int(value))
        except ValueError:
            return default
    return default
