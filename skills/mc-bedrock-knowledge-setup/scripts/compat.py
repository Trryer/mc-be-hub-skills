# -*- coding: utf-8 -*-
"""Small Python 2/3 compatibility helpers for mc-bedrock-fast-code scripts."""

from __future__ import print_function

import datetime
import io
import json
import os
import re
import subprocess
import sys

PY2 = sys.version_info[0] == 2

try:
    from urllib.request import Request, urlopen
    from urllib.parse import quote, urljoin, urlparse
except ImportError:  # pragma: no cover - Python 2 path
    from urllib2 import Request, urlopen
    from urllib import quote
    from urlparse import urljoin, urlparse


class CompletedProcess(object):
    def __init__(self, args, returncode, stdout="", stderr=""):
        self.args = args
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def as_text(value, encoding="utf-8"):
    if value is None:
        return ""
    if PY2:
        if isinstance(value, unicode):  # noqa: F821  # pragma: no cover
            return value
        return value.decode(encoding, "replace")
    if isinstance(value, bytes):
        return value.decode(encoding, "replace")
    return str(value)


def read_text(path, encoding="utf-8-sig", errors="replace"):
    with io.open(str(path), "r", encoding=encoding, errors=errors) as fh:
        return fh.read()


def write_text(path, text, encoding="utf-8"):
    parent = os.path.dirname(os.path.abspath(str(path)))
    if parent and not os.path.isdir(parent):
        os.makedirs(parent)
    with io.open(str(path), "w", encoding=encoding, newline="") as fh:
        fh.write(as_text(text))


def read_bytes(path):
    with io.open(str(path), "rb") as fh:
        return fh.read()


def write_bytes(path, data):
    parent = os.path.dirname(os.path.abspath(str(path)))
    if parent and not os.path.isdir(parent):
        os.makedirs(parent)
    with io.open(str(path), "wb") as fh:
        fh.write(data)


def utcnow_iso():
    return datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def run_command(cmd, timeout=None):
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = proc.communicate()
    return CompletedProcess(
        cmd,
        proc.returncode,
        as_text(stdout).strip(),
        as_text(stderr).strip(),
    )


def which(name):
    paths = os.environ.get("PATH", "").split(os.pathsep)
    exts = [""]
    if os.name == "nt":
        exts = os.environ.get("PATHEXT", ".EXE;.BAT;.CMD").split(os.pathsep)
        exts.append("")
    for directory in paths:
        candidate = os.path.join(directory, name)
        for ext in exts:
            path = candidate if candidate.lower().endswith(ext.lower()) else candidate + ext
            if os.path.isfile(path) and os.access(path, os.X_OK):
                return path
    return None


def strip_json_comments(text):
    """Remove // and /* */ comments plus trailing commas from JSON-like files."""
    out = []
    i = 0
    in_string = False
    quote_char = ""
    escape = False
    while i < len(text):
        ch = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""
        if in_string:
            out.append(ch)
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == quote_char:
                in_string = False
            i += 1
            continue
        if ch in ('"', "'"):
            in_string = True
            quote_char = ch
            out.append(ch)
            i += 1
            continue
        if ch == "/" and nxt == "/":
            i += 2
            while i < len(text) and text[i] not in "\r\n":
                i += 1
            continue
        if ch == "/" and nxt == "*":
            i += 2
            while i + 1 < len(text) and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            i += 2
            continue
        out.append(ch)
        i += 1
    return re.sub(r",\s*([}\]])", r"\1", "".join(out))


def load_json(path):
    text = read_text(path)
    try:
        return json.loads(text)
    except ValueError:
        return json.loads(strip_json_comments(text))


def try_load_json(path):
    try:
        return load_json(path)
    except Exception:
        return None


def _merge_dicts(*items):
    merged = {}
    for item in items:
        if item:
            merged.update(item)
    return merged
