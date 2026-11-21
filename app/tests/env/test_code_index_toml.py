from agentmon.env.code_index_toml import (ensure_sections, merge_path,
                                          render_daemon_toml)


def test_render_has_one_path_and_sections():
    text = render_daemon_toml("a", "/a", 8005)
    assert text.count("[[paths]]") == 1
    assert 'alias = "a"' in text and 'path = "/a"' in text
    assert "[mcp]" in text and "mass_mode_tools" in text
    assert "http://127.0.0.1:8005" in text


def test_merge_preserves_other_paths_and_sections():
    text = render_daemon_toml("a", "/a", 8005)
    out = merge_path(text, alias="b", path="/b")
    assert out.count("[[paths]]") == 2
    assert 'alias = "a"' in out and 'alias = "b"' in out
    assert "mass_mode_tools" in out
    assert "http://127.0.0.1:8005" in out


def test_merge_updates_existing_alias():
    text = render_daemon_toml("a", "/old", 8005)
    out = merge_path(text, alias="a", path="/new")
    assert out.count('alias = "a"') == 1
    assert 'path = "/new"' in out and 'path = "/old"' not in out


def test_merge_appends_to_text_without_paths():
    out = merge_path("[daemon]\nhttp_port = 0\n", alias="a", path="/a")
    assert out.startswith("[daemon]")
    assert "[[paths]]" in out and 'alias = "a"' in out


def test_merge_escapes_quotes_and_backslashes():
    out = merge_path("", alias='a"b', path="C:\\x")
    assert 'alias = "a\\"b"' in out
    assert 'path = "C:\\\\x"' in out


_WITH_EXTRAS = ('[daemon]\nhttp_port = 0\n\n'
                '[[paths]]\npath = "/old"\nalias = "a"\nlanguage = "bsl"\n'
                'git = true\ndebounce_ms = 500  # keep me\n\n'
                '[[paths]]\npath = "/b"\nalias = "b"\nlanguage = "bsl"\n'
                'git = true\n')


def test_merge_keeps_comments_and_extra_keys():
    out = merge_path(_WITH_EXTRAS, alias="a", path="/new", language="bsl")
    assert "# keep me" in out
    assert "debounce_ms = 500" in out
    assert out.count("git = true") == 2
    assert 'path = "/new"' in out and 'path = "/old"' not in out


def test_merge_updates_alias_block_in_place():
    out = merge_path(_WITH_EXTRAS, alias="a", path="/new", language="python")
    block = out.split("[[paths]]")[1]
    assert 'alias = "a"' in block
    assert "git = true" in block and "debounce_ms = 500" in block
    assert 'path = "/new"' in block and 'language = "python"' in block


def test_merge_leaves_other_block_with_same_key_untouched():
    out = merge_path(_WITH_EXTRAS, alias="a", path="/new", language="bsl")
    other = out.split("[[paths]]")[2]
    assert other == _WITH_EXTRAS.split("[[paths]]")[2]


def test_merge_adds_missing_path_and_language_keys():
    text = '[[paths]]\nalias = "a"\ngit = true\n'
    out = merge_path(text, alias="a", path="/new", language="python")
    assert out.count("[[paths]]") == 1
    assert 'path = "/new"' in out and 'language = "python"' in out
    assert 'alias = "a"' in out and "git = true" in out


def test_merge_with_extras_idempotent():
    once = merge_path(_WITH_EXTRAS, alias="a", path="/new", language="bsl")
    twice = merge_path(once, alias="a", path="/new", language="bsl")
    assert once == twice


def test_ensure_sections_adds_missing_and_is_idempotent():
    out = ensure_sections('[[paths]]\nalias = "a"\n', 8005)
    assert "[mcp]" in out and "mass_mode_tools" in out
    assert "[[cache_targets]]" in out
    assert out.count("[[cache_targets]]") == 1
    assert ensure_sections(out, 8005).count("[[cache_targets]]") == 1


def test_ensure_sections_replaces_single_target_url():
    text = render_daemon_toml("a", "/a", 8005)
    out = ensure_sections(merge_path(text, alias="b", path="/b"), 9000)
    assert out.count("[[cache_targets]]") == 1
    assert "http://127.0.0.1:9000" in out
    assert "8005" not in out
    assert 'alias = "b"' in out


def test_ensure_sections_keeps_extra_keys_of_target_block():
    text = ('[daemon]\nhttp_port = 0\n\n'
            '[[cache_targets]]\nurl = "http://127.0.0.1:8005"\n'
            'mode = "read"  # keep me\n\n'
            '[[paths]]\npath = "/a"\nalias = "a"\nlanguage = "bsl"\n')
    out = ensure_sections(text, 9000)
    assert out.count("[[cache_targets]]") == 1
    assert 'url = "http://127.0.0.1:9000"' in out
    assert "# keep me" in out and 'mode = "read"' in out


def test_ensure_sections_does_not_append_duplicate_on_multiple_blocks():
    text = ('[[cache_targets]]\nurl = "http://127.0.0.1:8005"\n\n'
            '[[cache_targets]]\nurl = "http://other:9000"\n\n'
            '[[paths]]\npath = "/a"\nalias = "a"\nlanguage = "bsl"\n')
    out = ensure_sections(text, 8005)
    assert out.count("[[cache_targets]]") == 2
    out = ensure_sections(text, 9100)
    assert out.count("[[cache_targets]]") == 3
    assert "http://127.0.0.1:9100" in out
