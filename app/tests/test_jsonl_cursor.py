from agentmon.jsonl_cursor import JsonlCursor
from agentmon.models import FileRef


class FakeFiles:
    """Файлы в памяти; считает вызовы чтения и объём переданных байт."""

    def __init__(self):
        self.data: dict[str, bytes] = {}
        self.bytes_read = 0

    def read_from(self, path, offset):
        blob = self.data[path][offset:]
        self.bytes_read += len(blob)
        return blob, offset + len(blob)


def ref_for(files, path="/log/a.jsonl", mtime=1.0):
    return FileRef(path=path, dir_name="log", session_id="a",
                   size=len(files.data[path]), mtime=mtime)


ASSISTANT = (
    '{"type":"assistant","message":{"model":"claude-opus-4-8",'
    '"usage":{"input_tokens":%d,"output_tokens":%d,'
    '"cache_read_input_tokens":0,"cache_creation_input_tokens":0},'
    '"content":[{"type":"text","text":"%s"}]}}\n'
)


def test_accumulates_tokens_and_messages():
    f = FakeFiles()
    f.data["/log/a.jsonl"] = ((ASSISTANT % (10, 5, "one")) +
                              (ASSISTANT % (20, 7, "two"))).encode()
    st = JsonlCursor(f).update(ref_for(f))
    assert (st.input_tokens, st.output_tokens) == (30, 12)
    assert [m["text"] for m in st.messages] == ["one", "two"]
    assert st.model == "claude-opus-4-8"


def test_second_update_reads_only_the_tail():
    f = FakeFiles()
    f.data["/log/a.jsonl"] = (ASSISTANT % (10, 5, "one")).encode()
    cur = JsonlCursor(f)
    cur.update(ref_for(f))
    first = f.bytes_read
    f.data["/log/a.jsonl"] += (ASSISTANT % (1, 1, "two")).encode()
    st = cur.update(ref_for(f, mtime=2.0))
    assert f.bytes_read - first == len(ASSISTANT % (1, 1, "two"))
    assert (st.input_tokens, st.output_tokens) == (11, 6)
    assert [m["text"] for m in st.messages] == ["one", "two"]


def test_unchanged_file_is_not_read_again():
    f = FakeFiles()
    f.data["/log/a.jsonl"] = (ASSISTANT % (10, 5, "one")).encode()
    cur = JsonlCursor(f)
    cur.update(ref_for(f))
    before = f.bytes_read
    cur.update(ref_for(f))
    assert f.bytes_read == before


def test_partial_last_line_is_completed_on_next_update():
    f = FakeFiles()
    whole = (ASSISTANT % (10, 5, "one")).encode()
    f.data["/log/a.jsonl"] = whole[:-12]          # строка оборвана
    cur = JsonlCursor(f)
    st = cur.update(ref_for(f))
    assert st.messages == []
    f.data["/log/a.jsonl"] = whole
    st = cur.update(ref_for(f, mtime=2.0))
    assert [m["text"] for m in st.messages] == ["one"]
    assert st.input_tokens == 10


def test_truncated_file_resets_state():
    f = FakeFiles()
    f.data["/log/a.jsonl"] = ((ASSISTANT % (10, 5, "one")) +
                              (ASSISTANT % (10, 5, "two"))).encode()
    cur = JsonlCursor(f)
    cur.update(ref_for(f))
    f.data["/log/a.jsonl"] = (ASSISTANT % (3, 2, "fresh")).encode()
    st = cur.update(ref_for(f, mtime=2.0))
    assert (st.input_tokens, st.output_tokens) == (3, 2)
    assert [m["text"] for m in st.messages] == ["fresh"]


def test_broken_line_is_skipped():
    f = FakeFiles()
    f.data["/log/a.jsonl"] = (b"not json at all\n" +
                              (ASSISTANT % (4, 2, "ok")).encode())
    st = JsonlCursor(f).update(ref_for(f))
    assert st.input_tokens == 4
    assert [m["text"] for m in st.messages] == ["ok"]


def test_cwd_is_picked_up_from_any_record():
    f = FakeFiles()
    f.data["/log/a.jsonl"] = (
        b'{"type":"system","sessionId":"s"}\n'
        b'{"type":"user","cwd":"/home/u/proj",'
        b'"message":{"content":[{"type":"text","text":"hi"}]}}\n'
    )
    st = JsonlCursor(f).update(ref_for(f))
    assert st.cwd == "/home/u/proj"
    assert [m["role"] for m in st.messages] == ["user"]


def test_current_phase_taken_from_last_assistant_record():
    f = FakeFiles()
    f.data["/log/a.jsonl"] = (
        '{"type":"assistant","message":{"content":[{"type":"tool_use",'
        '"name":"Task","input":{"subagent_type":"architect"}}]}}\n'
        '{"type":"assistant","message":{"content":[{"type":"text","text":"done"}]}}\n'
    ).encode()
    st = JsonlCursor(f).update(ref_for(f))
    assert st.current_phase is None


def test_current_phase_survives_until_next_assistant_record():
    f = FakeFiles()
    f.data["/log/a.jsonl"] = (
        '{"type":"assistant","message":{"content":[{"type":"tool_use",'
        '"name":"Task","input":{"subagent_type":"architect"}}]}}\n'
    ).encode()
    st = JsonlCursor(f).update(ref_for(f))
    assert st.current_phase == "architect"
