"""Фейковый Provisioner для тестов code-index и подготовки агента."""
from agentmon.backends import RunResult


class FakeProvisioner:
    def __init__(self):
        self.writes = {}
        self.runs = []
        self.detached = []
        self.copies = []
        self.dirs = []
        self.home = "/root"
        self.run_results = {}       # подстрока argv → RunResult

    def write_text(self, path, content):
        self.writes[path] = content

    def read_text(self, path):
        return self.writes.get(path, "")

    def exists(self, path):
        return path in self.writes

    def mkdirs(self, paths):
        self.dirs.extend(paths)

    def run(self, cmd, cwd=None, timeout=None, env=None):
        self.runs.append({"argv": list(cmd), "cwd": cwd, "env": dict(env or {})})
        joined = " ".join(cmd)
        if 'printf %s "$HOME"' in joined:
            return RunResult(0, self.home, "")
        for key, result in self.run_results.items():
            if key in joined:
                return result
        return RunResult(0, "", "")

    def exec_detached(self, argv, cwd=None, env=None):
        self.detached.append({"argv": list(argv), "cwd": cwd,
                              "env": dict(env or {})})
        return RunResult(0, "", "")

    def copy_in(self, local_path, dst):
        self.copies.append((str(local_path), dst))
        return RunResult(0, "", "")
