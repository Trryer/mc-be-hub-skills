"""Read-only, selected-source knowledge status. Never downloads or rebuilds."""
import argparse
import json
from pathlib import Path

KEYS = ('api_references','demo_index','vanilla_indexes','minecraft_json_docs',
        'remote_public_indexes','custom_project_indexes')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path.home()/'.codex/mc-bedrock-fast-code-data')
    parser.add_argument('--registry',type=Path)
    parser.add_argument('--require',choices=KEYS,action='append',default=[])
    args = parser.parse_args()
    registry = (args.registry or args.root/'knowledge_registry.json').expanduser().resolve()
    result = dict(registry=str(registry),checked=list(dict.fromkeys(args.require)),sources={},read_only=True)
    data = {}
    if registry.is_file():
        try:
            data = json.loads(registry.read_text(encoding='utf-8-sig'))
            if not isinstance(data,dict):
                raise ValueError('Registry must be a JSON object')
        except (OSError,ValueError) as error:
            data = {}
            result['error'] = str(error)
    else:
        result['error'] = 'Registry missing; prepare only the requested source'
    result['registered_sources'] = [key for key in KEYS if data.get(key)]
    for key in result['checked']:
        value = data.get(key)
        paths = []
        if key=='custom_project_indexes':
            paths = [Path(v['index']).expanduser() for v in value or [] if isinstance(v,dict) and v.get('index')]
        elif isinstance(value,str) and value:
            base = Path(value).expanduser()
            if key=='api_references':
                paths = [base/'api-index.md']
            elif key=='demo_index':
                paths = [base/'demo_index.json']
            elif key=='minecraft_json_docs':
                paths = [base/name for name in ('pages.jsonl','index.json','search.sqlite3')]
            elif key=='vanilla_indexes':
                paths = list(base.glob('*/index.json'))
            else:
                paths = list(base.rglob('*.json')) if base.is_dir() else []
        present = bool(paths) and all(p.is_file() for p in paths)
        result['sources'][key] = dict(status='PRESENT' if present else 'MISSING',files=[str(p) for p in paths])
    missing = [key for key,row in result['sources'].items() if row['status']=='MISSING']
    result['status'] = 'MISSING' if missing or result.get('error') else 'READY'
    result['missing_required'] = missing
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 1 if result['status']=='MISSING' else 0

if __name__=='__main__':
    raise SystemExit(main())
