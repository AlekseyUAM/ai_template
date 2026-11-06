from agentmon.paths import normalize_path, same_path


def test_windows_path_normalized_to_forward_slashes_and_casefold():
    assert normalize_path(r"C:\Work\Demo") == "c:/work/demo"


def test_windows_path_styles_are_same_path():
    assert same_path(r"C:\Work\Demo", "c:/work/demo/")


def test_posix_paths_keep_case():
    assert not same_path("/srv/Proj", "/srv/proj")


def test_trailing_slash_ignored():
    assert same_path("/srv/p/", "/srv/p")


def test_root_and_empty_paths_survive():
    assert normalize_path("/") == "/"
    assert normalize_path("") == ""
