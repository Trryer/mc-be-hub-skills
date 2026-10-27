#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import print_function
"""Compile-check project Python files and remove generated pyc caches."""

import argparse
import os
import py_compile
import shutil
import subprocess
import sys
from pathlib import Path


def iter_py_files(project):
    skip_dirs = set(['.git', '__pycache__'])
    for root, dirs, files in os.walk(str(project)):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        for name in files:
            if name.endswith('.py'):
                yield Path(root) / name


def cleanup_pyc(project):
    removed = 0
    pycache_dirs = []
    for root, dirs, files in os.walk(str(project)):
        for name in files:
            if name.endswith(('.pyc', '.pyo')):
                try:
                    os.remove(os.path.join(root, name))
                    removed += 1
                except OSError:
                    pass
        for dirname in dirs:
            if dirname == '__pycache__':
                pycache_dirs.append(os.path.join(root, dirname))
    for dirname in sorted(pycache_dirs, reverse=True):
        try:
            shutil.rmtree(dirname)
        except OSError:
            pass
    return removed


def rel(path, root):
    return str(path.relative_to(root)).replace('\\', '/')


def compile_files(project):
    errors = []
    checked = 0
    for path in iter_py_files(project):
        checked += 1
        try:
            py_compile.compile(str(path), doraise=True)
        except Exception as exc:
            errors.append((rel(path, project), str(exc)))
    removed = cleanup_pyc(project)
    return checked, removed, errors


def rerun_with_python(python, args):
    cmd = [python, __file__, '--project', args.project]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = proc.communicate()
    if stdout:
        sys.stdout.write(stdout.decode('utf-8', 'replace') if not isinstance(stdout, str) else stdout)
    if stderr:
        sys.stderr.write(stderr.decode('utf-8', 'replace') if not isinstance(stderr, str) else stderr)
    return proc.returncode


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', required=True, help='Project directory to compile-check.')
    parser.add_argument('--python', help='Preferred Python executable. Use Python 2.7 for ModSDK syntax checks when available.')
    return parser.parse_args()


def main():
    args = parse_args()
    if args.python and os.path.abspath(args.python) != os.path.abspath(sys.executable):
        return rerun_with_python(args.python, args)
    project = Path(args.project).resolve()
    checked, removed, errors = compile_files(project)
    for path, error in errors:
        print('ERROR: {}: {}'.format(path, error))
    print('Checked Python files: {}'.format(checked))
    print('Removed pyc/pyo caches: {}'.format(removed))
    if errors:
        return 1
    print('OK: Python syntax compile check passed.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
