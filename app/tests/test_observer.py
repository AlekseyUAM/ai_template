import logging

from agentmon.models import FileRef
from agentmon.observer import Observer


class FakeFiles:
    def __init__(self):
        self.data: dict[str, bytes] = {}
        self.meta: dict[str, tuple[str, str, float]] = {}   # path -> dir, sid, mtime

    def add(self, path, dir_name, session_id, mtime, body: str):
        self.data[path] = body.encode()
        self.meta[path] = (dir_name, session_id, mtime)

    def home_projects_dir(self):
        return "/home/u/.claude/projects"

    def list_files(self, projects_dir):
        return [
            FileRef(path=p, dir_name=d, session_id=s, size=len(self.data[p]), mtime=m)
            for p, (d, s, m) in self.meta.items()
        ]

    def read_from(self, path, offset):
        blob = self.data[path][offset:]
        return blob, offset + len(blob)


def assistant(cwd, inp, out, text, model="claude-opus-4-8"):
    return (
        '{"type":"assistant","cwd":"%s","message":{"model":"%s",'
        '"usage":{"input_tokens":%d,"output_tokens":%d,'
        '"cache_read_input_tokens":0,"cache_creation_input_tokens":0},'
        '"content":[{"type":"text","text":"%s"}]}}\n' % (cwd, model, inp, out, text)
    )


def test_snapshot_uses_cwd_as_project_path():
    f = FakeFiles()
    f.add("/p/-x/s1.jsonl", "-x", "s1", 100.0, assistant("/srv/demo", 10, 5, "hi"))
    obs = Observer(f, generating_window=10.0)
    obs.refresh()
    snap = obs.snapshot("/srv/demo", now=105.0)
    assert snap.project_path == "/srv/demo"
    assert snap.session_id == "s1"
    assert (snap.input_tokens, snap.output_tokens) == (10, 5)
    assert snap.model == "claude-opus-4-8"


def test_windows_path_is_matched_as_written_in_the_log():
    f = FakeFiles()
    body = assistant("C:\\\\work\\\\demo", 1, 1, "hi")
    f.add("/p/-x/s1.jsonl", "-x", "s1", 100.0, body)
    obs = Observer(f)
    obs.refresh()
    # Ключи хранятся в нормализованном виде, но журнал находится и по тому
    # написанию пути, которое лежит в самом журнале.
    assert obs.known_paths() == ["c:/work/demo"]
    assert obs.snapshot("C:\\work\\demo", now=101.0) is not None


def test_state_generating_inside_window():
    f = FakeFiles()
    f.add("/p/-x/s1.jsonl", "-x", "s1", 100.0, assistant("/srv/d", 1, 1, "hi"))
    obs = Observer(f, generating_window=10.0)
    obs.refresh()
    assert obs.snapshot("/srv/d", now=105.0).state == "generating"
    assert obs.snapshot("/srv/d", now=200.0).state == "idle"


def test_only_newest_file_per_directory_is_used():
    f = FakeFiles()
    f.add("/p/-x/old.jsonl", "-x", "old", 100.0, assistant("/srv/d", 1, 1, "старое"))
    f.add("/p/-x/new.jsonl", "-x", "new", 200.0, assistant("/srv/d", 2, 2, "новое"))
    obs = Observer(f)
    obs.refresh()
    snap = obs.snapshot("/srv/d", now=201.0)
    assert snap.session_id == "new"
    assert snap.input_tokens == 2


def test_directory_without_cwd_is_ignored():
    f = FakeFiles()
    f.add("/p/-x/s1.jsonl", "-x", "s1", 100.0,
          '{"type":"system","sessionId":"s1"}\n')
    obs = Observer(f)
    obs.refresh()
    assert obs.known_paths() == []
    assert obs.snapshot("/srv/d", now=1.0) is None


def test_transcript_returns_dialogue():
    f = FakeFiles()
    body = (
        '{"type":"user","cwd":"/srv/d","message":{"content":'
        '[{"type":"text","text":"привет"}]}}\n'
        '{"type":"assistant","message":{"content":[{"type":"text","text":"ответ"}]}}\n'
    )
    f.add("/p/-x/s1.jsonl", "-x", "s1", 100.0, body)
    obs = Observer(f)
    obs.refresh()
    assert obs.transcript("/srv/d") == [
        {"role": "user", "text": "привет"},
        {"role": "assistant", "text": "ответ"},
    ]


def test_transcript_for_unknown_project_is_empty():
    obs = Observer(FakeFiles())
    obs.refresh()
    assert obs.transcript("/nope") == []


def test_state_for_unknown_project_is_none():
    obs = Observer(FakeFiles())
    obs.refresh()
    assert obs.state("/nope", now=1.0) is None


def test_refresh_reads_only_the_tail_on_second_pass():
    f = FakeFiles()
    f.add("/p/-x/s1.jsonl", "-x", "s1", 100.0, assistant("/srv/d", 10, 5, "one"))
    reads = []
    original = f.read_from
    f.read_from = lambda path, offset: (reads.append(offset), original(path, offset))[1]
    obs = Observer(f)
    obs.refresh()
    body = f.data["/p/-x/s1.jsonl"] + assistant("/srv/d", 1, 1, "two").encode()
    f.data["/p/-x/s1.jsonl"] = body
    f.meta["/p/-x/s1.jsonl"] = ("-x", "s1", 200.0)
    obs.refresh()
    assert reads[-1] > 0
    assert obs.snapshot("/srv/d", now=201.0).input_tokens == 11


def test_cost_is_computed_from_model_and_tokens():
    f = FakeFiles()
    f.add("/p/-x/s1.jsonl", "-x", "s1", 100.0,
          assistant("/srv/d", 1_000_000, 0, "hi", model="claude-opus-4-8"))
    obs = Observer(f)
    obs.refresh()
    assert obs.snapshot("/srv/d", now=101.0).cost_usd > 0


def test_cwd_collision_resolved_by_mtime():
    # Два разных каталога журналов (-a и -b) дают один и тот же cwd — например,
    # каталог сессий переименовали или журналы с двух машин легли рядом.
    # Побеждает запись с бо́льшим mtime, независимо от порядка выдачи list_files.
    def run(reverse_order):
        f = FakeFiles()
        f.add("/p/-a/s1.jsonl", "-a", "s1", 100.0, assistant("/srv/d", 1, 1, "старое"))
        f.add("/p/-b/s2.jsonl", "-b", "s2", 200.0, assistant("/srv/d", 2, 2, "новое"))
        if reverse_order:
            original = f.list_files
            f.list_files = lambda projects_dir: list(reversed(original(projects_dir)))
        obs = Observer(f)
        obs.refresh()
        return obs.snapshot("/srv/d", now=201.0)

    for reverse_order in (False, True):
        snap = run(reverse_order)
        assert snap.session_id == "s2"
        assert snap.input_tokens == 2


def test_cwd_collision_logs_warning(caplog):
    f = FakeFiles()
    f.add("/p/-a/s1.jsonl", "-a", "s1", 100.0, assistant("/srv/d", 1, 1, "старое"))
    f.add("/p/-b/s2.jsonl", "-b", "s2", 200.0, assistant("/srv/d", 2, 2, "новое"))
    obs = Observer(f)
    with caplog.at_level(logging.WARNING, logger="agentmon.observer"):
        obs.refresh()
    assert any("/srv/d" in rec.message for rec in caplog.records)


def test_stale_cursor_state_is_forgotten_on_rotation():
    f = FakeFiles()
    f.add("/p/-x/s1.jsonl", "-x", "s1", 100.0, assistant("/srv/d", 1, 1, "one"))
    obs = Observer(f)
    obs.refresh()
    assert "/p/-x/s1.jsonl" in obs.cursor._states

    # Ротация журнала: каталог -x теперь содержит только новый файл s2.jsonl.
    del f.data["/p/-x/s1.jsonl"]
    del f.meta["/p/-x/s1.jsonl"]
    f.add("/p/-x/s2.jsonl", "-x", "s2", 200.0, assistant("/srv/d", 2, 2, "two"))
    obs.refresh()

    assert "/p/-x/s1.jsonl" not in obs.cursor._states
    assert "/p/-x/s2.jsonl" in obs.cursor._states


def test_cursor_update_failure_is_logged_and_others_still_processed(caplog):
    f = FakeFiles()
    f.add("/p/-bad/bad.jsonl", "-bad", "bad", 100.0, assistant("/srv/bad", 1, 1, "x"))
    f.add("/p/-ok/ok.jsonl", "-ok", "ok", 100.0, assistant("/srv/ok", 1, 1, "y"))

    original_read = f.read_from

    def flaky_read(path, offset):
        if path == "/p/-bad/bad.jsonl":
            raise RuntimeError("boom")
        return original_read(path, offset)

    f.read_from = flaky_read

    obs = Observer(f)
    with caplog.at_level(logging.WARNING, logger="agentmon.observer"):
        obs.refresh()

    assert obs.snapshot("/srv/bad", now=101.0) is None
    assert obs.snapshot("/srv/ok", now=101.0) is not None
    assert any("bad.jsonl" in rec.message and "boom" in rec.message
               for rec in caplog.records)


# --- Сопоставление журнала с проектом (Finding 4) ---


def test_trailing_slash_in_project_path_still_matches():
    f = FakeFiles()
    f.add("/p/-x/s1.jsonl", "-x", "s1", 100.0, assistant("/srv/demo", 3, 1, "hi"))
    obs = Observer(f)
    obs.refresh()
    snap = obs.snapshot("/srv/demo/", now=101.0)
    assert snap is not None
    assert snap.input_tokens == 3
    # Наружу отдаём путь, о котором спросили, а не нормализованный.
    assert snap.project_path == "/srv/demo/"
    assert obs.state("/srv/demo/", now=101.0) == "generating"


def test_trailing_slash_in_log_cwd_still_matches():
    f = FakeFiles()
    f.add("/p/-x/s1.jsonl", "-x", "s1", 100.0, assistant("/srv/demo/", 3, 1, "hi"))
    obs = Observer(f)
    obs.refresh()
    assert obs.snapshot("/srv/demo", now=101.0) is not None


def test_windows_path_typed_with_forward_slashes_matches():
    f = FakeFiles()
    body = assistant("C:\\\\work\\\\demo", 4, 1, "hi")
    f.add("/p/-x/s1.jsonl", "-x", "s1", 100.0, body)
    obs = Observer(f)
    obs.refresh()
    assert obs.snapshot("C:/work/demo", now=101.0) is not None


def test_drive_letter_case_does_not_matter():
    f = FakeFiles()
    body = assistant("C:\\\\work\\\\demo", 4, 1, "hi")
    f.add("/p/-x/s1.jsonl", "-x", "s1", 100.0, body)
    obs = Observer(f)
    obs.refresh()
    assert obs.snapshot("c:\\work\\demo", now=101.0) is not None
    assert obs.transcript("c:/work/Demo/") == [{"role": "assistant", "text": "hi"}]


def test_genuinely_different_path_still_does_not_match():
    f = FakeFiles()
    f.add("/p/-x/s1.jsonl", "-x", "s1", 100.0, assistant("/srv/demo", 1, 1, "hi"))
    obs = Observer(f)
    obs.refresh()
    assert obs.snapshot("/srv/demo2", now=101.0) is None
    assert obs.snapshot("/srv", now=101.0) is None
    # На POSIX регистр значим, и без буквы диска его складывать нельзя.
    assert obs.snapshot("/SRV/DEMO", now=101.0) is None


def test_root_path_is_not_normalized_to_empty_string():
    f = FakeFiles()
    f.add("/p/-x/s1.jsonl", "-x", "s1", 100.0, assistant("/", 1, 1, "hi"))
    obs = Observer(f)
    obs.refresh()
    assert obs.known_paths() == ["/"]
    assert obs.snapshot("/", now=101.0) is not None


# --- Домашний каталог и обрывы связи (Findings 3, 12) ---


def test_projects_dir_is_reasked_until_the_home_lookup_succeeds():
    """Первый тик может прийтись на момент, когда хост ещё недоступен."""
    f = FakeFiles()
    f.add("/real/-x/s1.jsonl", "-x", "s1", 100.0, assistant("/srv/d", 1, 1, "hi"))
    home = {"v": "/guess/.claude/projects"}
    asked = []

    def home_projects_dir():
        asked.append(home["v"])
        return home["v"]

    f.home_projects_dir = home_projects_dir
    f.list_files = lambda projects_dir: (
        [FileRef(path=p, dir_name=d, session_id=s, size=len(f.data[p]), mtime=m)
         for p, (d, s, m) in f.meta.items()]
        if projects_dir == "/real/.claude/projects" else []
    )

    obs = Observer(f)
    obs.refresh()
    assert obs.snapshot("/srv/d", now=101.0) is None   # спрашивали не тот каталог

    home["v"] = "/real/.claude/projects"               # связь восстановилась
    obs.refresh()
    assert obs.snapshot("/srv/d", now=101.0) is not None
    assert len(asked) == 2                             # спросили заново, а не один раз


def test_explicit_projects_dir_is_never_reasked():
    f = FakeFiles()
    f.home_projects_dir = lambda: (_ for _ in ()).throw(AssertionError("спросили"))
    obs = Observer(f, projects_dir="/explicit/projects")
    assert obs.projects_dir == "/explicit/projects"
    obs.refresh()


def test_empty_listing_does_not_discard_cursor_state():
    """Обрыв связи не должен стоить перечитывания всех журналов с нуля."""
    f = FakeFiles()
    f.add("/p/-x/s1.jsonl", "-x", "s1", 100.0, assistant("/srv/d", 1, 1, "one"))
    obs = Observer(f)
    obs.refresh()
    assert obs.cursor._states["/p/-x/s1.jsonl"].offset > 0

    original = f.list_files
    f.list_files = lambda projects_dir: []      # хост "пропал"
    obs.refresh()
    assert "/p/-x/s1.jsonl" in obs.cursor._states

    f.list_files = original                     # связь восстановилась
    reads = []
    original_read = f.read_from
    f.read_from = lambda path, offset: (reads.append(offset),
                                        original_read(path, offset))[1]
    f.meta["/p/-x/s1.jsonl"] = ("-x", "s1", 200.0)
    obs.refresh()
    assert reads == [len(f.data["/p/-x/s1.jsonl"])]   # дочитали хвост, не всё
