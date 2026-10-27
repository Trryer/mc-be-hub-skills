"""Build the public bundle from a fixed source boundary, excluding private data."""
import argparse
import hashlib
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DIRECTORIES = {'.agents','.codex-plugin','skills','scripts','tests'}
FILES = {'.gitignore','build_public_index.py','CHANGELOG.md','LICENSE','NOTICE.md',
         'plugin.json','README.md','README.zh-CN.md','VERSION'}
PRIVATE_NAMES = {'private','private-experience','experience-records','snapshots','archives'}

def sources(root=ROOT):
    for path in sorted(root.rglob('*')):
        rel = path.relative_to(root)
        if rel.parts[0] not in DIRECTORIES and rel.as_posix() not in FILES:
            continue
        if any(p in {'.git','__pycache__'} for p in rel.parts) or path.suffix in {'.pyc','.pyo'}:
            continue
        if path.is_symlink():
            raise ValueError('Linked source is not distributable: '+str(rel))
        if not path.is_file():
            continue
        if any(part in PRIVATE_NAMES for part in rel.parts) or 'experience' in rel.parts:
            raise ValueError('Private record directory found in public source: '+str(rel))
        yield path,rel

def build(output,root=ROOT):
    entries = list(sources(root))
    if not entries:
        raise ValueError('No public sources found')
    if any(path.resolve()==output.resolve() for path,_ in entries):
        raise ValueError('Output would overwrite a source file')
    output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for path,rel in entries:
            archive.write(path,Path('mc-be-hub-skills')/rel)
    with zipfile.ZipFile(output) as archive:
        if archive.testzip() is not None:
            raise ValueError('Archive CRC check failed')
    return dict(files=len(entries),sha256=hashlib.sha256(output.read_bytes()).hexdigest())

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,default=ROOT.parent/'mc-be-hub-skills.zip')
    args=parser.parse_args()
    print(build(args.out))
