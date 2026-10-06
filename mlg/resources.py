"""Locate data in a source checkout or an installed wheel."""

from pathlib import Path


def data_directory(name):
    package = Path(__file__).resolve().parent
    bundled = package / name
    return bundled if bundled.is_dir() else package.parent / name
