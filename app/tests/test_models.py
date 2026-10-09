from agentmon.models import FileRef, Project, SessionSnapshot, Task


def test_project_key_built_from_backend_host_and_path():
    p = Project(id=1, name="demo", path="/srv/demo", backend="ssh",
                conn={"host": "srv", "port": 22, "user": "root", "key_path": None},
                claude_cmd=None, created_at=0.0)
    assert p.key == "ssh|srv|/srv/demo"


def test_local_project_key_has_empty_host():
    p = Project(id=2, name="d", path="C:\\work\\d", backend="local", conn=None,
                claude_cmd=None, created_at=0.0)
    assert p.key == "local||C:\\work\\d"


def test_project_host_is_none_without_conn():
    p = Project(id=3, name="d", path="/x", backend="local", conn=None,
                claude_cmd=None, created_at=0.0)
    assert p.host is None


def test_fileref_carries_dir_and_session_id():
    ref = FileRef(path="/home/u/.claude/projects/-x/abc.jsonl", dir_name="-x",
                  session_id="abc", size=10, mtime=5.0)
    assert (ref.dir_name, ref.session_id) == ("-x", "abc")


def test_task_has_project_id():
    t = Task(id=1, project_id=7, text="do", status="queued", created_at=0.0,
             started_at=None, finished_at=None, session_id=None)
    assert t.project_id == 7


def test_snapshot_uses_project_path():
    s = SessionSnapshot(session_id="s", project_path="/srv/demo", model="m",
                        input_tokens=1, output_tokens=2, cache_read_tokens=0,
                        cache_creation_tokens=0, cost_usd=0.0, last_activity=1.0,
                        state="idle", current_phase=None)
    assert s.project_path == "/srv/demo"
