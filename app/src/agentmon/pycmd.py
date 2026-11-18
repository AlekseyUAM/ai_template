"""Имя интерпретатора Python для генерируемых команд.

На Windows `python3` часто оказывается заглушкой Microsoft Store, которая
завершается сразу и печатает предложение установить Python. На POSIX-системах,
наоборот, может отсутствовать `python` — там стандартен `python3`.
"""
import os

PYTHON_CMD = "python" if os.name == "nt" else "python3"
