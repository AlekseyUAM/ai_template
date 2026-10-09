import json
from dataclasses import dataclass, field

from .models import FileRef


@dataclass
class CursorState:
    """Накопленное состояние одного журнала сессии."""
    size: int = 0
    mtime: float = 0.0
    offset: int = 0
    tail: bytes = b""              # незавершённая последняя строка
    model: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    current_phase: str | None = None
    cwd: str | None = None
    messages: list[dict] = field(default_factory=list)


def _text_from_content(content) -> str:
    """Собрать текст из content сообщения (строка или список блоков)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            b.get("text", "")
            for b in content
            if isinstance(b, dict) and b.get("type") == "text"
        )
    return ""


class JsonlCursor:
    """Читает .jsonl только с последнего смещения и копит результат.

    Записи в журнале лишь дописываются, поэтому дочитывание хвоста даёт тот же
    результат, что и полное чтение. Уменьшение размера или откат mtime трактуем
    как пересоздание файла и начинаем заново.
    """

    def __init__(self, files):
        self._files = files
        self._states: dict[str, CursorState] = {}

    def update(self, ref: FileRef) -> CursorState:
        st = self._states.get(ref.path)
        if st is None or ref.size < st.size or ref.mtime < st.mtime:
            st = CursorState()
            self._states[ref.path] = st
        elif ref.size == st.size and ref.mtime == st.mtime:
            return st

        data, new_offset = self._files.read_from(ref.path, st.offset)
        buf = st.tail + data
        parts = buf.split(b"\n")
        st.tail = parts.pop()
        for raw in parts:
            self._apply(st, raw)
        st.offset = new_offset
        st.size = ref.size
        st.mtime = ref.mtime
        return st

    def forget(self, path: str) -> None:
        self._states.pop(path, None)

    def _apply(self, st: CursorState, raw: bytes) -> None:
        line = raw.strip()
        if not line:
            return
        try:
            d = json.loads(line.decode("utf-8", "replace"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return
        if not isinstance(d, dict):
            return

        if st.cwd is None and isinstance(d.get("cwd"), str):
            st.cwd = d["cwd"]

        kind = d.get("type")
        if kind not in ("user", "assistant"):
            return

        msg = d.get("message") or {}
        text = _text_from_content(msg.get("content")).strip()
        if text:
            st.messages.append({"role": kind, "text": text})

        if kind != "assistant":
            return

        if msg.get("model"):
            st.model = msg["model"]
        usage = msg.get("usage") or {}
        st.input_tokens += int(usage.get("input_tokens", 0) or 0)
        st.output_tokens += int(usage.get("output_tokens", 0) or 0)
        st.cache_read_tokens += int(usage.get("cache_read_input_tokens", 0) or 0)
        st.cache_creation_tokens += int(usage.get("cache_creation_input_tokens", 0) or 0)

        # Фаза не накопительная: сбрасывается на каждом ответе ассистента и
        # выставляется, только если в нём есть вызов Task с subagent_type.
        st.current_phase = None
        content = msg.get("content")
        if isinstance(content, list):
            for block in content:
                if (isinstance(block, dict) and block.get("type") == "tool_use"
                        and block.get("name") == "Task"):
                    sub = (block.get("input") or {}).get("subagent_type")
                    if sub:
                        st.current_phase = sub
