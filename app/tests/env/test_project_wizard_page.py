"""Lightweight content tests for project-wizard.html and project-wizard.js.

Asserts that the SSH backend UI elements and license-server field are present
in the source files — no server needed.
"""
import pathlib

# test file lives at app/tests/env/; web files live at app/web/
_WEB = pathlib.Path(__file__).resolve().parents[2] / "web"


def _html() -> str:
    return (_WEB / "project-wizard.html").read_text(encoding="utf-8")


def _js() -> str:
    return (_WEB / "project-wizard.js").read_text(encoding="utf-8")


# ── HTML assertions ──────────────────────────────────────────────────────────

def test_html_has_backend_select():
    assert 'id="backend"' in _html(), "Missing id=\"backend\" in project-wizard.html"


def test_html_has_ssh_fields_container():
    assert 'id="sshFields"' in _html(), "Missing id=\"sshFields\" in project-wizard.html"


def test_html_has_ssh_host_input():
    assert 'id="sshHost"' in _html(), "Missing id=\"sshHost\" in project-wizard.html"


def test_html_has_license_server_input():
    assert 'id="licenseServer"' in _html(), "Missing id=\"licenseServer\" in project-wizard.html"


# ── JS assertions ────────────────────────────────────────────────────────────

def test_js_has_backend_in_body():
    assert "backend:" in _js(), "Missing backend: key in project-wizard.js body"


def test_js_has_license_server_in_body():
    assert "license_server:" in _js(), "Missing license_server: key in project-wizard.js body"


def test_js_has_read_conn_helper():
    assert "readConn" in _js(), "Missing readConn helper in project-wizard.js"


def test_js_read_conn_used_in_check_db():
    """readConn() must be called in the check-db fetch body (DRY)."""
    js = _js()
    # conn: readConn() should appear at least twice (check-db + createProject)
    assert js.count("readConn()") >= 2, (
        "readConn() should be called at least twice (check-db and createProject)"
    )
