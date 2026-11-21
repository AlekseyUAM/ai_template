"""1c-batch - a cross-platform tool for batch operations with 1C:Enterprise 8."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("1c-batch")
except PackageNotFoundError:
    __version__ = "0.0.0+unknown"
