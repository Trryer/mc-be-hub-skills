# -*- coding: utf-8 -*-
"""Tiny pathlib subset used so bundled scripts can run on Python 2.7."""

from __future__ import print_function

import fnmatch
import io
import os
import sys

PY2 = sys.version_info[0] == 2


def _text(value):
    if PY2:
        if isinstance(value, unicode):  # noqa: F821  # pragma: no cover
            return value
        return value.decode("utf-8", "replace")
    return value


class Path(object):
    def __init__(self, *parts):
        raw = []
        for part in parts:
            if isinstance(part, Path):
                raw.append(part.path)
            else:
                raw.append(str(part))
        self.path = os.path.join(*raw) if raw else "."

    def __str__(self):
        return self.path

    def __repr__(self):
        return "Path({0!r})".format(self.path)

    def __fspath__(self):
        return self.path

    def __eq__(self, other):
        return os.path.normcase(os.path.abspath(self.path)) == os.path.normcase(os.path.abspath(str(other)))

    def __lt__(self, other):
        return str(self) < str(other)

    def __hash__(self):
        return hash(os.path.normcase(os.path.abspath(self.path)))

    def __div__(self, other):
        return Path(self.path, other)

    def __truediv__(self, other):
        return Path(self.path, other)

    @classmethod
    def cwd(cls):
        return cls(os.getcwd())

    @classmethod
    def home(cls):
        return cls(os.path.expanduser("~"))

    @property
    def name(self):
        return os.path.basename(self.path.rstrip("\\/"))

    @property
    def parent(self):
        return Path(os.path.dirname(self.path.rstrip("\\/")) or ".")

    @property
    def suffix(self):
        return os.path.splitext(self.name)[1]

    @property
    def stem(self):
        return os.path.splitext(self.name)[0]

    @property
    def parts(self):
        drive, tail = os.path.splitdrive(os.path.normpath(self.path))
        parts = []
        while tail and tail not in (os.sep, os.altsep):
            head, name = os.path.split(tail)
            if name:
                parts.insert(0, name)
            if head == tail:
                break
            tail = head
        if drive:
            parts.insert(0, drive)
        return tuple(parts)

    def as_posix(self):
        return self.path.replace(os.sep, "/")

    def resolve(self):
        return Path(os.path.realpath(os.path.abspath(self.path)))

    def expanduser(self):
        return Path(os.path.expanduser(self.path))

    def exists(self):
        return os.path.exists(self.path)

    def is_dir(self):
        return os.path.isdir(self.path)

    def is_file(self):
        return os.path.isfile(self.path)

    def stat(self):
        return os.stat(self.path)

    def iterdir(self):
        for name in os.listdir(self.path):
            yield Path(self.path, name)

    def glob(self, pattern):
        import glob
        for item in glob.glob(os.path.join(self.path, pattern)):
            yield Path(item)

    def rglob(self, pattern):
        for root, _dirs, files in os.walk(self.path):
            if pattern == "*":
                names = list(_dirs) + list(files)
            else:
                names = [name for name in files if fnmatch.fnmatch(name, pattern)]
            for name in names:
                yield Path(root, name)

    def mkdir(self, parents=False, exist_ok=False):
        if self.exists():
            if exist_ok:
                return
            raise OSError("directory exists: {0}".format(self.path))
        if parents:
            os.makedirs(self.path)
        else:
            os.mkdir(self.path)

    def open(self, mode="r", encoding=None, errors=None):
        if "b" in mode:
            return io.open(self.path, mode)
        return io.open(self.path, mode, encoding=encoding or "utf-8", errors=errors or "strict")

    def read_text(self, encoding="utf-8", errors="strict"):
        with self.open("r", encoding=encoding, errors=errors) as fh:
            return fh.read()

    def write_text(self, text, encoding="utf-8"):
        if not self.parent.exists():
            self.parent.mkdir(parents=True, exist_ok=True)
        with self.open("w", encoding=encoding) as fh:
            fh.write(_text(text))

    def read_bytes(self):
        with self.open("rb") as fh:
            return fh.read()

    def write_bytes(self, data):
        if not self.parent.exists():
            self.parent.mkdir(parents=True, exist_ok=True)
        with self.open("wb") as fh:
            fh.write(data)

    def unlink(self):
        os.unlink(self.path)

    def rmdir(self):
        os.rmdir(self.path)

    def relative_to(self, other):
        return Path(os.path.relpath(self.path, str(other)))

    def startswith(self, other):
        return self.path.startswith(other)


PurePath = Path
