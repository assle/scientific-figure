"""Scientific Figure Builder Core runtime package."""

from importlib.metadata import PackageNotFoundError, version


try:
    __version__ = version("scientific-figure-builder")
except PackageNotFoundError:  # Source checkout without an installed distribution.
    __version__ = "0.0.0+uninstalled"
