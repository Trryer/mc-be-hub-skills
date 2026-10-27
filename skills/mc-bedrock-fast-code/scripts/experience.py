"""Manage external private Markdown records; no network or Git operations."""
import argparse
from datetime import date
import json
import os
import sys

# This Python 3 tool must not import the sibling Python 2 pathlib compatibility shim.
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path = [p for p in sys.path if os.path.abspath(p) != _SCRIPT_DIR]
from pathlib import Path
import re

SKILL = Path(__file__).resolve().parents[1]
DEFAULT = Path.home()/'.codex/mc-bedrock-fast-code-data/private/experience/mc-be-hub-skills'
SKIP = {'.git','__pycache__','snapshots','archives'}

def storage(value):
    root = Path(value).expanduser().resolve()
    if any((parent/'SKILL.md').is_file() for parent in (root,*root.parents)):
        raise ValueError('Keep private records outside installed skills: '+str(root))
    forbidden = [SKILL]
    for parent in SKILL.parents:
        if (parent/'plugin.json').is_file():
            forbidden.append(parent)
            break
    for folder in forbidden:
        if root.is_relative_to(folder) or folder.is_relative_to(root):
            raise ValueError('Keep private records outside skill/bundle directories: '+str(root))
    return root

def records(root):
    if not root.exists():
        return
    for base,dirs,names in os.walk(root,followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in SKIP and not (Path(base)/d).is_symlink())
        for name in sorted(names):
            path = Path(base)/name
            if path.suffix.lower()=='.md' and not path.is_symlink():
                yield path

def search(root,query=None):
    result = []
    for path in records(root):
        text = path.read_text(encoding='utf-8-sig')
        title = next((line.lstrip('# ').strip() for line in text.splitlines() if line.startswith('#')),path.stem)
        item = dict(path=str(path),title=title)
        if query is not None:
            matches = [dict(line=i,excerpt=line[:500]) for i,line in enumerate(text.splitlines(),1)
                       if query.casefold() in line.casefold()]
            if not matches:
                continue
            item['matches'] = matches[:10]
        result.append(item)
    return result

def add(root,slug,title,body_file):
    if not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,79}',slug):
        raise ValueError('Slug must contain 1-80 lowercase letters, digits, underscores or hyphens')
    if not title.strip() or '\n' in title or '\r' in title:
        raise ValueError('Title must be a nonempty single line')
    body = body_file.read_text(encoding='utf-8-sig')
    if not body.strip():
        raise ValueError('Record body is empty')
    folder = root/'records'
    folder.mkdir(parents=True,exist_ok=True)
    if not folder.resolve().is_relative_to(root):
        raise ValueError('Record directory escaped storage root')
    path = folder/(slug+'.md')
    with path.open('x',encoding='utf-8',newline='\n') as stream:
        stream.write('# '+title.strip()+'\n\nRecorded: '+date.today().isoformat()+'\n\n'+body.rstrip()+'\n')
    return dict(path=str(path),created=True,network_used=False)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',default=os.environ.get('MC_BE_EXPERIENCE_ROOT',str(DEFAULT)))
    sub = parser.add_subparsers(dest='command',required=True)
    sub.add_parser('path')
    sub.add_parser('list')
    lookup = sub.add_parser('search')
    lookup.add_argument('query')
    create = sub.add_parser('add')
    create.add_argument('--slug',required=True)
    create.add_argument('--title',required=True)
    create.add_argument('--body-file',required=True,type=Path)
    args = parser.parse_args()
    try:
        root = storage(args.root)
        if args.command=='add':
            result = add(root,args.slug,args.title,args.body_file)
        elif args.command=='path':
            result = dict(path=str(root),available=root.is_dir())
        else:
            if args.command=='search' and not args.query.strip():
                raise ValueError('Search query is empty')
            result = dict(root=str(root),available=root.is_dir(),
                          records=search(root,args.query if args.command=='search' else None))
    except (OSError,ValueError) as error:
        print(json.dumps(dict(error=str(error)),ensure_ascii=False),file=sys.stderr)
        return 2
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0

if __name__=='__main__':
    raise SystemExit(main())
