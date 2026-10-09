"""Снимки сессий по журналам .jsonl целевой машины.

Путь проекта берётся из поля cwd записей журнала: имя каталога, которое
формирует Claude Code, необратимо и на Windows не разбирается вовсе.
"""

import logging
import re

from . import config
from .jsonl_cursor import JsonlCursor
from .models import SessionSnapshot
from .pricing import cost_for

logger = logging.getLogger(__name__)

_DRIVE_RE = re.compile(r"^[A-Za-z]:")


def normalize_path(path: str) -> str:
    """Привести путь к виду, пригодному для сопоставления журнала с проектом.

    Ключи журналов — это сырые cwd, записанные Claude Code, а ищут по ним
    путь, набранный пользователем в форме. Расхождение в стиле слэшей,
    хвостовой слэш или регистр буквы диска не должны означать «журнала нет»:
    иначе агент работает, панель показывает «idle · 0 tok», а диспетчер
    через no_log_seconds помечает все задачи проекта проваленными.

    Нормализация нужна только для сопоставления: наружу пути отдаются
    в том виде, в каком их задал вызывающий.
    """
    if not path:
        return path
    norm = path.replace("\\", "/")
    # Пустая строка ключом быть не может: "/" схлопывать нельзя.
    norm = norm.rstrip("/") or norm[:1]
    if _DRIVE_RE.match(norm):
        # Windows не различает регистр — и буквы диска, и остального пути.
        norm = norm.casefold()
    return norm


class Observer:
    def __init__(self, files, projects_dir=None,
                 generating_window=config.GENERATING_WINDOW):
        self.files = files
        self._projects_dir = projects_dir
        self.generating_window = generating_window
        self.cursor = JsonlCursor(files)
        self._latest: dict[str, tuple] = {}      # project_path -> (FileRef, CursorState)
        self._tracked: set[str] = set()          # пути файлов, за которыми следит cursor

    @property
    def projects_dir(self) -> str:
        """Каталог журналов на целевой машине.

        Спрашиваем бэкенд каждый раз, а не один раз в конструкторе: домашний
        каталог по SSH определяется лениво и неудачную попытку не кеширует,
        а наблюдатель обычно создаётся на первом тике диспетчера — когда VPN
        ещё может быть не поднят. Один вопрос навсегда пришпилил бы догадку
        (/root или /home/<user>) на весь срок жизни процесса, и при промахе
        list_files молча возвращал бы [] вечно. Успех бэкенд кеширует сам.
        """
        return self._projects_dir or self.files.home_projects_dir()

    def refresh(self) -> None:
        newest_by_dir = {}
        for ref in self.files.list_files(self.projects_dir):
            cur = newest_by_dir.get(ref.dir_name)
            if cur is None or ref.mtime > cur.mtime:
                newest_by_dir[ref.dir_name] = ref

        # Каталог без cwd в журналах всё равно остаётся "живым": иначе каждый
        # refresh перечитывал бы его заново вместо инкрементального дочитывания.
        #
        # Пустая выдача же — почти всегда обрыв связи (list_files по SSH глушит
        # отказ и возвращает []), а не исчезновение всех журналов разом. Забыв
        # по ней курсоры, мы после восстановления перечитали бы каждый журнал
        # с нуля по сети, поэтому на пустой выдаче не забываем ничего.
        if newest_by_dir:
            live = {ref.path for ref in newest_by_dir.values()}
            for path in self._tracked - live:
                self.cursor.forget(path)
            self._tracked = live

        latest = {}
        for ref in newest_by_dir.values():
            try:
                state = self.cursor.update(ref)
            except Exception as exc:
                logger.warning("не удалось прочитать журнал %s: %s", ref.path, exc)
                continue
            if not state.cwd:
                continue

            key = normalize_path(state.cwd)
            prev = latest.get(key)
            if prev is not None:
                prev_ref, _ = prev
                logger.warning(
                    "коллизия cwd %r: каталоги журналов %r и %r указывают на один "
                    "и тот же путь проекта",
                    state.cwd, prev_ref.dir_name, ref.dir_name,
                )
                if prev_ref.mtime >= ref.mtime:
                    continue
            latest[key] = (ref, state)
        self._latest = latest

    def known_paths(self) -> list[str]:
        """Пути проектов, для которых есть журнал, — в нормализованном виде."""
        return sorted(self._latest)

    def snapshot(self, project_path, now) -> SessionSnapshot | None:
        got = self._latest.get(normalize_path(project_path))
        if got is None:
            return None
        ref, st = got
        state = "generating" if (now - ref.mtime) <= self.generating_window else "idle"
        return SessionSnapshot(
            session_id=ref.session_id,
            project_path=project_path,
            model=st.model,
            input_tokens=st.input_tokens,
            output_tokens=st.output_tokens,
            cache_read_tokens=st.cache_read_tokens,
            cache_creation_tokens=st.cache_creation_tokens,
            cost_usd=cost_for(st.model, st.input_tokens, st.output_tokens,
                              st.cache_read_tokens, st.cache_creation_tokens),
            last_activity=ref.mtime,
            state=state,
            current_phase=st.current_phase,
        )

    def transcript(self, project_path) -> list[dict]:
        got = self._latest.get(normalize_path(project_path))
        return list(got[1].messages) if got else []

    def state(self, project_path, now) -> str | None:
        snap = self.snapshot(project_path, now)
        return snap.state if snap else None
