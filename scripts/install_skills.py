"""Install every bundled skill locally, backing up replaced skill folders."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ('mc-bedrock-fast-code','mc-bedrock-knowledge-setup',
          'mc-model-animation-to-blockbench','mc-shader-offscreen-rendering',
          'mc-shader-reconstruction')

def skill_name(folder):
    path = folder/'SKILL.md'
    if not path.is_file():
        return None
    match = re.search(r'^name:\s*([a-z0-9-]+)\s*$',path.read_text(encoding='utf-8-sig'),re.M)
    return match.group(1) if match else None

def files(folder):
    return {str(f.relative_to(folder)):hashlib.sha256(f.read_bytes()).hexdigest()
            for f in folder.rglob('*') if f.is_file() and '__pycache__' not in f.parts and f.suffix!='.pyc'}

def child(path,parent):
    candidate = Path(os.path.abspath(path))
    base = Path(os.path.abspath(parent))
    real_base = base.resolve()
    resolved = candidate.resolve()
    if candidate.name=='' or candidate==base or candidate.parent.resolve()!=real_base or resolved.parent!=real_base or candidate.is_symlink():
        raise ValueError('Path escaped intended directory: '+str(path))
    return candidate

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    default = Path(os.environ.get('CODEX_HOME',str(Path.home()/'.codex')))/'skills'
    parser.add_argument('--dest',type=Path,default=default)
    parser.add_argument('--dry-run',action='store_true')
    args = parser.parse_args()
    dest = args.dest.expanduser().resolve()
    source = ROOT/'skills'
    if source.is_relative_to(dest) or dest.is_relative_to(ROOT):
        parser.error('Installation directory must be outside the bundle and must not contain it')
    skills = sorted(p for p in source.iterdir() if p.is_dir() and (p/'SKILL.md').is_file())
    if tuple(p.name for p in skills)!=SKILLS or any(skill_name(p)!=p.name for p in skills):
        parser.error('Expected the complete five-skill bundle')
    changes,skipped = [],[]
    for skill in skills:
        try:
            target = child(dest/skill.name,dest)
        except ValueError as error:
            parser.error(str(error))
        if target.is_symlink() or (target.exists() and not target.is_dir()):
            parser.error('Refusing non-directory or linked skill: '+str(target))
        if target.exists() and skill_name(target)!=skill.name:
            parser.error('Refusing to replace a directory without the matching SKILL.md: '+str(target))
        if target.exists() and files(target)==files(skill):
            skipped.append(skill.name)
        else:
            changes.append(skill)
    result = dict(bundle='mc-be-hub-skills',destination=str(dest),dry_run=args.dry_run,
                  install=[p.name for p in changes],unchanged=skipped,backup=None,knowledge_modified=False)
    if args.dry_run or not changes:
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 0
    dest.mkdir(parents=True,exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    backup = dest.parent/'skill-backups/mc-be-hub-skills'/stamp
    completed = []
    with tempfile.TemporaryDirectory(prefix='mc-be-hub-stage-',dir=dest.parent) as temp:
        stage = Path(temp)
        for skill in changes:
            shutil.copytree(skill,stage/skill.name,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
        try:
            for skill in changes:
                target = child(dest/skill.name,dest)
                old = child(backup/skill.name,backup)
                had_old = target.exists()
                if had_old:
                    backup.mkdir(parents=True,exist_ok=True)
                    shutil.move(str(target),str(old))
                completed.append((target,old,had_old))
                shutil.move(str(child(stage/skill.name,stage)),str(target))
        except Exception:
            for target,old,had_old in reversed(completed):
                if target.exists():
                    shutil.rmtree(child(target,dest))
                if had_old and old.exists():
                    shutil.move(str(old),str(child(target,dest)))
            raise
    if backup.exists():
        result['backup'] = str(backup)
    report = dest.parent/'mc-be-hub-skills-install.json'
    result['report'] = str(report)
    report.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0

if __name__=='__main__':
    raise SystemExit(main())
