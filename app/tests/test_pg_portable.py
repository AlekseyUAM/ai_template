"""Тесты pg_portable: URL платформ, argv команд, идемпотентность, provision.

Все тесты используют фейки download/extract/run — без сети и реального PostgreSQL.
Импорт pg_portable выполняется через sys.path (корень репо), как в test_bootstrap_env.py.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

# Вставляем корень репо в путь (pg_portable.py лежит там же, где bootstrap.py)
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO_ROOT))

import pg_portable  # noqa: E402


# ---------------------------------------------------------------------------
# Вспомогательные фейки
# ---------------------------------------------------------------------------

class FakeRun:
    """Фейк subprocess.run: записывает аргументы, возвращает настраиваемый rc.

    По умолчанию rc=0 для всех вызовов. Можно задать последовательность rc
    через конструктор (список int) — каждый вызов потребляет следующий.
    Для status-запросов rc задаётся через атрибут status_rc.
    """

    def __init__(self, rc: int | list[int] = 0):
        self.calls: list[list[str]] = []
        self._rcs: list[int] = [rc] if isinstance(rc, int) else list(rc)
        self._default_rc: int = 0

    def __call__(self, cmd, **kwargs) -> Any:
        self.calls.append(list(cmd))
        rc = self._rcs.pop(0) if self._rcs else self._default_rc
        # Создаём минималистичный результат
        result = subprocess.CompletedProcess(cmd, rc, stdout=b"", stderr=b"")
        return result

    def argv(self, index: int) -> list[str]:
        """Возвращает аргументы i-го вызова."""
        return self.calls[index]

    def last_argv(self) -> list[str]:
        return self.calls[-1]


class FakeRunWithStdout:
    """Фейк run, возвращающий заданный stdout при нужном вызове."""

    def __init__(self, stdout_map: dict[int, bytes] | None = None):
        self.calls: list[list[str]] = []
        self._stdout_map: dict[int, bytes] = stdout_map or {}

    def __call__(self, cmd, **kwargs) -> Any:
        idx = len(self.calls)
        self.calls.append(list(cmd))
        stdout = self._stdout_map.get(idx, b"")
        return subprocess.CompletedProcess(cmd, 0, stdout=stdout, stderr=b"")


def fake_download(recorded: list) -> Any:
    """Фабрика фейк-download: создаёт пустой zip-файл, записывает (url, dest)."""
    def _download(url: str, dest: str) -> None:
        recorded.append((url, dest))
        # Создаём файл-заглушку (реальный zip не нужен — extract тоже фейк)
        Path(dest).parent.mkdir(parents=True, exist_ok=True)
        Path(dest).write_bytes(b"FAKE_ZIP")
    return _download


def fake_extract_factory(create_exe: bool = True):
    """Фабрика фейк-extract: имитирует распаковку EDB-архива.

    Создаёт <dest>/pgsql/bin/initdb[.exe], чтобы ensure_binaries считал успех.
    """
    def _extract(zip_path: str, dest: str) -> None:
        import sys as _sys
        bin_dir = Path(dest) / "pgsql" / "bin"
        bin_dir.mkdir(parents=True, exist_ok=True)
        if create_exe:
            exe = "initdb.exe" if _sys.platform == "win32" else "initdb"
            (bin_dir / exe).write_bytes(b"FAKE_INITDB")
            pg_ctl = "pg_ctl.exe" if _sys.platform == "win32" else "pg_ctl"
            (bin_dir / pg_ctl).write_bytes(b"FAKE_PG_CTL")
            psql = "psql.exe" if _sys.platform == "win32" else "psql"
            (bin_dir / psql).write_bytes(b"FAKE_PSQL")
    return _extract


def _initdb_exe() -> str:
    """Имя initdb с учётом платформы."""
    return "initdb.exe" if sys.platform == "win32" else "initdb"


def _pg_ctl_exe() -> str:
    return "pg_ctl.exe" if sys.platform == "win32" else "pg_ctl"


def _psql_exe() -> str:
    return "psql.exe" if sys.platform == "win32" else "psql"


# ---------------------------------------------------------------------------
# binaries_url
# ---------------------------------------------------------------------------

class TestBinariesUrl:
    def test_windows_x64(self):
        url = pg_portable.binaries_url("Windows", "AMD64")
        assert url.startswith(pg_portable.EDB_BASE_URL)
        assert "windows-x64" in url
        assert pg_portable.PG_VERSION in url
        assert url.endswith(".zip")

    def test_linux_x64(self):
        url = pg_portable.binaries_url("Linux", "x86_64")
        assert "linux-x64" in url
        assert pg_portable.PG_VERSION in url

    def test_osx_arm(self):
        # osx-архив один для всех архитектур
        url = pg_portable.binaries_url("Darwin", "arm64")
        assert "osx" in url
        assert pg_portable.PG_VERSION in url

    def test_osx_x64(self):
        url = pg_portable.binaries_url("Darwin", "x86_64")
        assert "osx" in url

    def test_unsupported_system_raises(self):
        with pytest.raises(RuntimeError, match="Неподдерживаемая платформа"):
            pg_portable.binaries_url("FreeBSD", "x86_64")

    def test_unsupported_arch_raises(self):
        with pytest.raises(RuntimeError, match="Неподдерживаемая архитектура"):
            pg_portable.binaries_url("Linux", "arm64")

    def test_url_contains_base(self):
        url = pg_portable.binaries_url("Windows", "AMD64")
        assert url.startswith("https://get.enterprisedb.com/postgresql/")

    def test_linux_case_insensitive(self):
        # system передаётся из platform.system() — именно такой регистр
        url = pg_portable.binaries_url("Linux", "x86_64")
        assert "linux" in url.lower()


# ---------------------------------------------------------------------------
# bin_exe
# ---------------------------------------------------------------------------

class TestBinExe:
    def test_on_win32(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "win32")
        assert pg_portable.bin_exe("initdb") == "initdb.exe"

    def test_on_linux(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")
        assert pg_portable.bin_exe("initdb") == "initdb"

    def test_on_darwin(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "darwin")
        assert pg_portable.bin_exe("pg_ctl") == "pg_ctl"


# ---------------------------------------------------------------------------
# ensure_binaries
# ---------------------------------------------------------------------------

class TestEnsureBinaries:
    def test_skip_when_initdb_present(self, tmp_path):
        """Если initdb уже существует — download/extract не вызываются."""
        version_dir = tmp_path / pg_portable.PG_DIR / pg_portable.PG_VERSION / "pgsql" / "bin"
        version_dir.mkdir(parents=True)
        (version_dir / _initdb_exe()).write_bytes(b"fake")

        downloaded: list = []
        extracted: list = []

        bin_dir = pg_portable.ensure_binaries(
            tmp_path,
            system="Linux",
            arch="x86_64",
            download=lambda u, d: downloaded.append((u, d)),
            extract=lambda z, d: extracted.append((z, d)),
        )

        assert downloaded == []
        assert extracted == []
        assert bin_dir == str(version_dir)

    def test_downloads_and_extracts_when_absent(self, tmp_path):
        """Если initdb отсутствует — скачивает и распаковывает."""
        downloaded: list = []
        extract = fake_extract_factory(create_exe=True)

        bin_dir = pg_portable.ensure_binaries(
            tmp_path,
            system="Linux",
            arch="x86_64",
            download=fake_download(downloaded),
            extract=extract,
        )

        assert len(downloaded) == 1
        url, dest = downloaded[0]
        assert "linux-x64" in url
        assert dest.endswith(".zip")
        assert _initdb_exe() in bin_dir or str(bin_dir).endswith("bin")

    def test_returns_bin_dir_path(self, tmp_path):
        """Возвращает путь к каталогу bin."""
        pg_portable.ensure_binaries(
            tmp_path,
            system="Linux",
            arch="x86_64",
            download=fake_download([]),
            extract=fake_extract_factory(True),
        )
        expected_bin = (
            tmp_path / pg_portable.PG_DIR / pg_portable.PG_VERSION / "pgsql" / "bin"
        )
        assert expected_bin.exists()

    def test_download_url_matches_platform(self, tmp_path):
        """URL в download() соответствует платформе Windows."""
        downloaded: list = []
        pg_portable.ensure_binaries(
            tmp_path,
            system="Windows",
            arch="AMD64",
            download=fake_download(downloaded),
            extract=fake_extract_factory(True),
        )
        url, _ = downloaded[0]
        assert "windows-x64" in url


# ---------------------------------------------------------------------------
# initdb
# ---------------------------------------------------------------------------

class TestInitdb:
    def test_runs_correct_argv(self, tmp_path):
        """Проверяем флаги: -D, -U postgres, -A trust, --encoding=UTF8."""
        fake = FakeRun(rc=0)
        bin_dir = tmp_path / "bin"
        datadir = tmp_path / "pgdata"
        pg_portable.initdb(str(bin_dir), str(datadir), run=fake)

        assert len(fake.calls) == 1
        argv = fake.calls[0]
        assert argv[0].endswith(_initdb_exe())
        assert "-D" in argv
        assert str(datadir) in argv
        assert "-U" in argv
        assert pg_portable.SUPERUSER in argv
        assert "-A" in argv
        assert "trust" in argv
        assert "--encoding=UTF8" in argv

    def test_skips_when_pg_version_exists(self, tmp_path):
        """Если datadir/PG_VERSION существует — initdb не запускается."""
        datadir = tmp_path / "pgdata"
        datadir.mkdir()
        (datadir / "PG_VERSION").write_text("16\n")

        fake = FakeRun(rc=0)
        pg_portable.initdb(tmp_path / "bin", datadir, run=fake)
        assert fake.calls == []

    def test_raises_on_nonzero_rc(self, tmp_path):
        fake = FakeRun(rc=1)
        with pytest.raises(subprocess.CalledProcessError):
            pg_portable.initdb(tmp_path / "bin", tmp_path / "pgdata", run=fake)


# ---------------------------------------------------------------------------
# start
# ---------------------------------------------------------------------------

class TestStart:
    def test_correct_argv(self, tmp_path):
        """Проверяем флаги pg_ctl start: -D, -o, -p/-h, -l, -w."""
        fake = FakeRun(rc=0)
        bin_dir = tmp_path / "bin"
        datadir = tmp_path / "pgdata"
        logfile = tmp_path / "pg.log"

        pg_portable.start(str(bin_dir), str(datadir), 5432, str(logfile), run=fake)

        assert len(fake.calls) == 1
        argv = fake.calls[0]
        assert argv[0].endswith(_pg_ctl_exe())
        assert "-D" in argv
        assert str(datadir) in argv
        assert "-o" in argv
        # Опция для pg_ctl: порт и хост
        pg_ctl_opts = argv[argv.index("-o") + 1]
        assert "5432" in pg_ctl_opts
        assert "127.0.0.1" in pg_ctl_opts
        assert "-l" in argv
        assert str(logfile) in argv
        assert "-w" in argv
        assert "start" in argv

    def test_raises_on_nonzero_rc(self, tmp_path):
        fake = FakeRun(rc=1)
        with pytest.raises(subprocess.CalledProcessError):
            pg_portable.start(
                tmp_path / "bin",
                tmp_path / "pgdata",
                5432,
                tmp_path / "pg.log",
                run=fake,
            )


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------

class TestStatus:
    def test_returns_true_when_rc_zero(self, tmp_path):
        fake = FakeRun(rc=0)
        result = pg_portable.status(tmp_path / "bin", tmp_path / "pgdata", run=fake)
        assert result is True

    def test_returns_false_when_rc_nonzero(self, tmp_path):
        fake = FakeRun(rc=1)
        result = pg_portable.status(tmp_path / "bin", tmp_path / "pgdata", run=fake)
        assert result is False

    def test_correct_argv(self, tmp_path):
        """pg_ctl status должен содержать 'status' и '-D <datadir>'."""
        fake = FakeRun(rc=0)
        datadir = tmp_path / "pgdata"
        pg_portable.status(tmp_path / "bin", datadir, run=fake)

        argv = fake.calls[0]
        assert argv[0].endswith(_pg_ctl_exe())
        assert "-D" in argv
        assert str(datadir) in argv
        assert "status" in argv


# ---------------------------------------------------------------------------
# stop
# ---------------------------------------------------------------------------

class TestStop:
    def test_correct_argv(self, tmp_path):
        fake = FakeRun(rc=0)
        datadir = tmp_path / "pgdata"
        pg_portable.stop(tmp_path / "bin", datadir, run=fake)

        argv = fake.calls[0]
        assert argv[0].endswith(_pg_ctl_exe())
        assert "-D" in argv
        assert str(datadir) in argv
        assert "stop" in argv

    def test_does_not_raise_on_nonzero(self, tmp_path):
        """stop() не должен поднимать исключение при уже остановленном сервере."""
        fake = FakeRun(rc=1)
        pg_portable.stop(tmp_path / "bin", tmp_path / "pgdata", run=fake)


# ---------------------------------------------------------------------------
# ensure_role_db
# ---------------------------------------------------------------------------

class TestEnsureRoleDb:
    def test_issues_role_sql(self, tmp_path):
        """Проверяем, что первый вызов psql содержит DO-блок для роли."""
        # Второй вызов — проверка наличия БД (возвращаем пустой stdout → БД нет)
        # Третий вызов — CREATE DATABASE
        fake = FakeRunWithStdout(stdout_map={1: b""})
        bin_dir = tmp_path / "bin"
        pg_portable.ensure_role_db(str(bin_dir), 5432, run=fake)

        assert len(fake.calls) >= 1
        first_argv = fake.calls[0]
        assert first_argv[0].endswith(_psql_exe())
        # Проверяем ключевые аргументы psql
        joined = " ".join(first_argv)
        assert "DO" in joined or "do" in joined.lower() or any(
            "DO" in a for a in first_argv
        )
        assert "-h" in first_argv
        assert "127.0.0.1" in first_argv
        assert "-p" in first_argv
        assert "5432" in first_argv
        assert "-U" in first_argv
        assert pg_portable.SUPERUSER in first_argv

    def test_issues_db_creation_when_absent(self, tmp_path):
        """Если БД не существует — вызывается CREATE DATABASE."""
        # calls: [0]=role, [1]=check db (stdout пустой → нет), [2]=create db
        fake = FakeRunWithStdout(stdout_map={1: b""})
        pg_portable.ensure_role_db(str(tmp_path / "bin"), 5432, run=fake)
        # Должно быть 3 вызова psql
        assert len(fake.calls) == 3
        create_argv = fake.calls[2]
        joined = " ".join(create_argv)
        assert "CREATE DATABASE" in joined

    def test_skips_db_creation_when_present(self, tmp_path):
        """Если БД уже существует (stdout содержит '1') — CREATE DATABASE не вызывается."""
        # calls: [0]=role, [1]=check db (stdout='1' → есть)
        fake = FakeRunWithStdout(stdout_map={1: b" 1\n"})
        pg_portable.ensure_role_db(str(tmp_path / "bin"), 5432, run=fake)
        assert len(fake.calls) == 2  # только роль + проверка БД

    def test_uses_custom_user_and_db(self, tmp_path):
        """Пользовательские имя/база передаются в SQL."""
        fake = FakeRunWithStdout(stdout_map={1: b""})
        pg_portable.ensure_role_db(
            str(tmp_path / "bin"), 5432, user="myuser", db="mydb", run=fake
        )
        role_sql = " ".join(fake.calls[0])
        assert "myuser" in role_sql
        db_create_sql = " ".join(fake.calls[2])
        assert "mydb" in db_create_sql

    def test_raises_on_role_error(self, tmp_path):
        """Ошибка при создании роли → CalledProcessError."""
        fake = FakeRun(rc=1)
        with pytest.raises(subprocess.CalledProcessError):
            pg_portable.ensure_role_db(str(tmp_path / "bin"), 5432, run=fake)

    def test_invalid_user_raises_value_error(self, tmp_path):
        """Недопустимый идентификатор user → ValueError (защитный барьер)."""
        fake = FakeRunWithStdout()
        with pytest.raises(ValueError, match="недопустимый идентификатор"):
            pg_portable.ensure_role_db(
                str(tmp_path / "bin"), 5432, user="a; DROP TABLE", run=fake
            )
        # Псевдоним с кавычкой тоже запрещён
        with pytest.raises(ValueError, match="недопустимый идентификатор"):
            pg_portable.ensure_role_db(
                str(tmp_path / "bin"), 5432, user="a'b", run=fake
            )
        # psql не должен был вызываться
        assert fake.calls == []

    def test_password_single_quote_is_doubled(self, tmp_path):
        """Одинарная кавычка в пароле удваивается в SQL-литерале."""
        fake = FakeRunWithStdout(stdout_map={1: b" 1\n"})  # БД уже есть → 2 вызова
        pg_portable.ensure_role_db(
            str(tmp_path / "bin"), 5432, password="pa'ss'word", run=fake
        )
        role_sql_argv = " ".join(fake.calls[0])
        # Проверяем, что кавычка удвоена
        assert "pa''ss''word" in role_sql_argv
        # И оригинальная незащищённая строка отсутствует в виде pa'ss
        assert "pa'ss" not in role_sql_argv.replace("pa''ss", "")

    def test_valid_ai1c_identifiers_work(self, tmp_path):
        """Стандартные константы ai1c проходят валидацию без ошибок."""
        fake = FakeRunWithStdout(stdout_map={1: b" 1\n"})
        pg_portable.ensure_role_db(
            str(tmp_path / "bin"), 5432,
            user="ai1c", password="ai1c", db="ai1c",
            run=fake,
        )
        assert len(fake.calls) == 2  # роль + check (БД есть, create пропущен)


# ---------------------------------------------------------------------------
# dsn
# ---------------------------------------------------------------------------

class TestDsn:
    def test_default_values(self):
        result = pg_portable.dsn(5432)
        assert result == "postgresql://ai1c:ai1c@127.0.0.1:5432/ai1c"

    def test_custom_port(self):
        result = pg_portable.dsn(5433)
        assert "5433" in result

    def test_custom_user_password_db(self):
        result = pg_portable.dsn(5432, user="bob", password="s3cr3t", db="mydb")
        assert result == "postgresql://bob:s3cr3t@127.0.0.1:5432/mydb"

    def test_format(self):
        result = pg_portable.dsn(5432)
        assert result.startswith("postgresql://")
        assert "@127.0.0.1:" in result


# ---------------------------------------------------------------------------
# free_port
# ---------------------------------------------------------------------------

class TestFreePort:
    def test_returns_int(self):
        port = pg_portable.free_port()
        assert isinstance(port, int)

    def test_in_range(self):
        port = pg_portable.free_port(5432, 5460)
        # Может вернуть start если все заняты — допустимо
        assert 5432 <= port < 5460 or port == 5432

    def test_custom_range(self):
        port = pg_portable.free_port(9000, 9010)
        assert 9000 <= port < 9010 or port == 9000


# ---------------------------------------------------------------------------
# provision — полный флоу
# ---------------------------------------------------------------------------

class TestProvision:
    """Интеграционные тесты provision: полный happy-path и повторный (идемпотентный)."""

    def _make_fakes(self, tmp_path, status_rcs: list[int] | None = None):
        """Создаёт набор фейков для provision.

        status_rcs — список rc для вызовов pg_ctl status.
        По умолчанию первый status возвращает 1 (не запущен) → start вызывается.
        """
        downloaded: list = []
        extract = fake_extract_factory(True)

        # Порядок вызовов run в provision:
        # 0: initdb
        # 1: status  (→ 1 означает «не запущен», тогда будет start)
        # 2: start   (если status=1)
        # 3: ensure_role_db[0] роль
        # 4: ensure_role_db[1] check db
        # 5: ensure_role_db[2] create db

        if status_rcs is None:
            rcs = [0, 1, 0, 0, 0, 0]  # initdb ok, status=not running, start ok, role ok, check=no db, create db ok
        else:
            rcs = status_rcs

        calls: list[list[str]] = []

        # Для ensure_role_db нам нужен stdout при проверке наличия БД.
        # Используем кастомный run с поддержкой stdout_map по индексу среди всех вызовов.
        # call index 4 = ensure_role_db[1] = check db → stdout пустой → создаём БД.
        call_count = [0]
        stdout_map = {4: b""}  # check db — нет записей

        completed_results = {i: rc for i, rc in enumerate(rcs)}

        def _run(cmd, **kwargs):
            idx = call_count[0]
            call_count[0] += 1
            calls.append(list(cmd))
            rc = completed_results.get(idx, 0)
            stdout = stdout_map.get(idx, b"")
            return subprocess.CompletedProcess(cmd, rc, stdout=stdout, stderr=b"")

        return downloaded, extract, _run, calls

    def test_happy_path_calls_order(self, tmp_path):
        """provision вызывает download, initdb, status, start, ensure_role_db и возвращает DSN."""
        downloaded, extract, fake_run, calls = self._make_fakes(tmp_path)

        result = pg_portable.provision(
            tmp_path,
            port=5432,
            system="Linux",
            arch="x86_64",
            download=fake_download(downloaded),
            extract=extract,
            run=fake_run,
        )

        assert result == "postgresql://ai1c:ai1c@127.0.0.1:5432/ai1c"
        assert len(downloaded) == 1  # скачали архив

        # Проверяем порядок: initdb → status → start → psql (роль) → psql (check db) → psql (create db)
        assert len(calls) >= 4
        cmds = [c[0] for c in calls]

        # initdb — первый
        assert _initdb_exe() in cmds[0] or cmds[0].endswith(_initdb_exe())
        # pg_ctl появляется до psql
        pg_ctl_indices = [i for i, c in enumerate(cmds) if _pg_ctl_exe() in c or c.endswith(_pg_ctl_exe())]
        psql_indices = [i for i, c in enumerate(cmds) if _psql_exe() in c or c.endswith(_psql_exe())]
        assert pg_ctl_indices, "pg_ctl должен вызываться"
        assert psql_indices, "psql должен вызываться"
        assert max(pg_ctl_indices) < max(psql_indices), "pg_ctl до psql"

    def test_returns_dsn(self, tmp_path):
        _, extract, fake_run, _ = self._make_fakes(tmp_path)
        result = pg_portable.provision(
            tmp_path,
            port=5432,
            system="Linux",
            arch="x86_64",
            download=fake_download([]),
            extract=extract,
            run=fake_run,
        )
        assert result.startswith("postgresql://")
        assert "5432" in result

    def test_idempotent_rerun_skips_initdb_and_start(self, tmp_path):
        """Повторный запуск: initdb пропущен (PG_VERSION есть), start пропущен (status=0)."""
        downloaded, extract, fake_run_1, calls_1 = self._make_fakes(tmp_path)

        # Первый запуск
        pg_portable.provision(
            tmp_path,
            port=5432,
            system="Linux",
            arch="x86_64",
            download=fake_download(downloaded),
            extract=extract,
            run=fake_run_1,
        )

        # Создаём PG_VERSION файл (имитируем уже инициализированный кластер)
        datadir = tmp_path / pg_portable.PGDATA
        datadir.mkdir(parents=True, exist_ok=True)
        (datadir / "PG_VERSION").write_text("16\n")

        # Второй запуск: status=0 → сервер уже запущен → start не нужен
        # Порядок: initdb (skip), status(0 → running), ensure_role_db × 3
        rcs_2 = [0, 0, 0, 0]  # status=0, роль, check_db, create_db
        call_count_2 = [0]
        calls_2: list[list[str]] = []
        stdout_map_2 = {1: b""}  # check db пустой (index 1 в rcs_2 это check db т.к. initdb skip)

        def _run_2(cmd, **kwargs):
            idx = call_count_2[0]
            call_count_2[0] += 1
            calls_2.append(list(cmd))
            rc = rcs_2[idx] if idx < len(rcs_2) else 0
            stdout = stdout_map_2.get(idx, b"")
            return subprocess.CompletedProcess(cmd, rc, stdout=stdout, stderr=b"")

        result_2 = pg_portable.provision(
            tmp_path,
            port=5432,
            system="Linux",
            arch="x86_64",
            download=fake_download([]),  # не должно скачивать (initdb.exe уже есть)
            extract=extract,
            run=_run_2,
        )

        assert result_2 == "postgresql://ai1c:ai1c@127.0.0.1:5432/ai1c"

        # initdb не должен вызываться (PG_VERSION файл существует)
        cmds_2 = [c[0] for c in calls_2]
        assert not any(_initdb_exe() in c or c.endswith(_initdb_exe()) for c in cmds_2), \
            "initdb не должен вызываться при повторном запуске (PG_VERSION существует)"

        # start не должен вызываться (status вернул 0)
        # Проверяем: среди pg_ctl вызовов нет 'start'
        pg_ctl_calls = [c for c in calls_2 if _pg_ctl_exe() in c[0] or c[0].endswith(_pg_ctl_exe())]
        for call in pg_ctl_calls:
            assert "start" not in call, f"start не должен вызываться: {call}"

    def test_port_saved_to_file(self, tmp_path):
        """provision сохраняет порт в <datadir>/ai1c.port."""
        _, extract, fake_run, _ = self._make_fakes(tmp_path)
        pg_portable.provision(
            tmp_path,
            port=5435,
            system="Linux",
            arch="x86_64",
            download=fake_download([]),
            extract=extract,
            run=fake_run,
        )
        port_file = tmp_path / pg_portable.PGDATA / "ai1c.port"
        assert port_file.exists()
        assert port_file.read_text(encoding="utf-8").strip() == "5435"

    def test_free_port_fn_injected_when_no_port_and_no_file(self, tmp_path):
        """free_port_fn инъектируется: реальный socket bind не вызывается в тесте."""
        _, extract, fake_run, calls = self._make_fakes(tmp_path)

        result = pg_portable.provision(
            tmp_path,
            # port НЕ передаётся, файла ai1c.port тоже нет
            system="Linux",
            arch="x86_64",
            download=fake_download([]),
            extract=extract,
            run=fake_run,
            free_port_fn=lambda: 5599,
        )

        # DSN должен содержать инъектированный порт 5599
        assert "5599" in result
        # start вызывался с портом 5599
        pg_ctl_start_calls = [c for c in calls if _pg_ctl_exe() in c[0] or c[0].endswith(_pg_ctl_exe())]
        start_call = next((c for c in pg_ctl_start_calls if "start" in c), None)
        assert start_call is not None, "pg_ctl start должен вызываться"
        assert any("5599" in arg for arg in start_call), f"порт 5599 не найден в argv start: {start_call}"

    def test_port_loaded_from_file_on_rerun(self, tmp_path):
        """При повторном запуске без явного порта читает порт из ai1c.port."""
        # Создаём PG_VERSION и ai1c.port вручную
        datadir = tmp_path / pg_portable.PGDATA
        datadir.mkdir(parents=True, exist_ok=True)
        (datadir / "PG_VERSION").write_text("16\n")
        (datadir / "ai1c.port").write_text("5440")

        # ensure_binaries: initdb.exe уже есть
        bin_dir = (
            tmp_path / pg_portable.PG_DIR / pg_portable.PG_VERSION / "pgsql" / "bin"
        )
        bin_dir.mkdir(parents=True, exist_ok=True)
        (bin_dir / _initdb_exe()).write_bytes(b"fake")

        rcs = [0, 0, 0, 0]  # status=0 (running), psql×3
        call_count = [0]
        calls: list[list[str]] = []
        stdout_map = {1: b""}  # check db index 1

        def _run(cmd, **kwargs):
            idx = call_count[0]
            call_count[0] += 1
            calls.append(list(cmd))
            rc = rcs[idx] if idx < len(rcs) else 0
            stdout = stdout_map.get(idx, b"")
            return subprocess.CompletedProcess(cmd, rc, stdout=stdout, stderr=b"")

        result = pg_portable.provision(
            tmp_path,
            system="Linux",
            arch="x86_64",
            download=fake_download([]),
            extract=fake_extract_factory(False),
            run=_run,
        )
        # Порт из файла 5440
        assert "5440" in result
