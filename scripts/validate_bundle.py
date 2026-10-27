"""Validate bundle structure, local links, Python syntax and isolated installation.

Uses Python 3.11+ standard library. No downloads, knowledge rebuild or game edits.
Tool-specific conversion/render dependencies and runtime tests are separate.
"""
import argparse
import ast
from contextlib import redirect_stdout
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from unittest.mock import patch
from urllib.parse import unquote, urlsplit

from install_skills import ROOT, SKILLS, files, skill_name


def require(condition, message):
    if not condition:
        raise ValueError(message)


def run(script, *args, expected=0):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTHONIOENCODING='utf-8')
    proc = subprocess.run([sys.executable, '-B', str(script), *map(str,args)],
                          capture_output=True, text=True, encoding='utf-8',
                          errors='replace', timeout=60, env=env)
    require(proc.returncode==expected, '{} {}: {}\n{}'.format(
        script,args,proc.returncode,proc.stdout+proc.stderr))
    return proc.stdout


def structure():
    manifest = json.loads((ROOT/'plugin.json').read_text(encoding='utf-8-sig'))
    compat = json.loads((ROOT/'.codex-plugin/plugin.json').read_text(encoding='utf-8-sig'))
    market = json.loads((ROOT/'.agents/plugins/marketplace.json').read_text(encoding='utf-8-sig'))
    require(manifest['name']==compat['name']==market['name']=='mc-be-hub-skills','Bundle name mismatch')
    require(manifest['version']==compat['version'],'Version mismatch')
    require((ROOT/'VERSION').read_text(encoding='utf-8').strip()==manifest['version'],'VERSION mismatch')
    require(compat['skills']=='./skills/','Incorrect skills directory')
    require((ROOT/manifest['extensions']['com.openai']['onboardingSkill']).is_file(),'Missing onboarding skill')
    require(len(market['plugins'])==1 and market['plugins'][0]['name']==manifest['name'],'Marketplace mismatch')
    require((ROOT/market['plugins'][0]['source']['path']).resolve()==ROOT,'Marketplace source mismatch')
    actual = tuple(sorted(p.name for p in (ROOT/'skills').iterdir() if p.is_dir()))
    require(actual==SKILLS,'Expected exactly the five skill directories')
    for name in SKILLS:
        folder = ROOT/'skills'/name
        require(skill_name(folder)==name,'Frontmatter name mismatch: '+name)
        text = (folder/'SKILL.md').read_text(encoding='utf-8-sig')
        require(text.startswith('---\n') and re.search(r'^description:\s*\S',text,re.M),'Missing frontmatter: '+name)
        require((folder/'agents/openai.yaml').is_file(),'Missing UI metadata: '+name)
    return dict(version=manifest['version'],skills=list(SKILLS))


def source_checks():
    scripts, links = 0, 0
    for path in ROOT.rglob('*.py'):
        ast.parse(path.read_text(encoding='utf-8-sig'),filename=str(path))
        scripts += 1
    for path in ROOT.rglob('*.md'):
        # Inline Markdown links outside fenced code, including sibling skill links.
        text = re.sub(r'(?ms)^```[^\n]*\n.*?^```[^\n]*$', '', path.read_text(encoding='utf-8-sig'))
        for target in re.findall(r'(?<!!)\[[^\]\n]+\]\(([^)\n]+)\)',text):
            target = target.strip()
            target = target[1:target.index('>')] if target.startswith('<') else target.split()[0]
            parsed = urlsplit(target)
            if parsed.scheme or parsed.netloc or not parsed.path:
                continue
            resolved = (path.parent/unquote(parsed.path)).resolve()
            require(resolved.is_relative_to(ROOT) and resolved.exists(),
                    'Broken or external relative link: {} -> {}'.format(path.relative_to(ROOT),target))
            links += 1
    return dict(python_scripts=scripts,relative_links=links)


def install_smoke(temp):
    installer = ROOT/'scripts/install_skills.py'
    dest = temp/'codex/skills'
    dry = json.loads(run(installer,'--dest',dest,'--dry-run'))
    require(len(dry['install'])==5 and not dest.exists(),'Dry-run wrote files')
    first = json.loads(run(installer,'--dest',dest))
    require(len(first['install'])==5,'First install incomplete')
    for name in SKILLS:
        require(files(ROOT/'skills'/name)==files(dest/name),'Installed content mismatch: '+name)
    second = json.loads(run(installer,'--dest',dest))
    require(not second['install'] and len(second['unchanged'])==5,'Repeat install not idempotent')
    (dest/SKILLS[0]/'old-local-file.txt').write_text('preserve in backup',encoding='utf-8')
    third = json.loads(run(installer,'--dest',dest))
    require(third['install']==[SKILLS[0]],'Unexpected replacements')
    require((Path(third['backup'])/SKILLS[0]/'old-local-file.txt').read_text()=='preserve in backup','Backup missing')
    run(installer,'--dest',ROOT/'skills',expected=2)
    other = temp/'unrelated/skills'/SKILLS[0]
    other.mkdir(parents=True)
    (other/'important.txt').write_text('keep',encoding='utf-8')
    run(installer,'--dest',other.parent,expected=2)
    require((other/'important.txt').read_text()=='keep','Unrelated directory overwritten')
    linked_parent = temp/'linked/skills'
    linked_parent.mkdir(parents=True)
    linked = linked_parent/SKILLS[0]
    symlink_checked = False
    try:
        os.symlink(ROOT/'skills'/SKILLS[0],linked,target_is_directory=True)
    except (OSError,NotImplementedError):
        pass
    else:
        symlink_checked = True
        run(installer,'--dest',linked_parent,expected=2)
        require(linked.is_symlink(),'Installer replaced a linked skill directory')

    # Fail during the second staged replacement; every replaced folder must return.
    spec = importlib.util.spec_from_file_location('bundle_installer_test',installer)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for name in SKILLS[:2]:
        (dest/name/'rollback.txt').write_text(name,encoding='utf-8')
    before = {name:files(dest/name) for name in SKILLS}
    original_move = module.shutil.move
    replacements = 0
    def fail_move(src, dst, *args, **kwargs):
        nonlocal replacements
        if Path(src).parent.name.startswith('mc-be-hub-stage-'):
            replacements += 1
            if replacements==2:
                raise OSError('injected staged replacement failure')
        return original_move(src,dst,*args,**kwargs)
    with patch.object(sys,'argv',[str(installer),'--dest',str(dest)]), patch.object(module.shutil,'move',side_effect=fail_move), redirect_stdout(io.StringIO()):
        try:
            module.main()
        except OSError as error:
            require(str(error)=='injected staged replacement failure','Unexpected rollback failure')
        else:
            raise ValueError('Injected failure did not occur')
    require(before=={name:files(dest/name) for name in SKILLS},'Rollback changed installed content')
    return dict(first_install=5,repeat_unchanged=5,backup=True,unsafe_target_rejected=True,
                symlink_target_tested=symlink_checked,rollback=True)


def cli_smoke(temp):
    dev = ROOT/'skills/mc-bedrock-fast-code/scripts'
    setup = ROOT/'skills/mc-bedrock-knowledge-setup/scripts'
    help_scripts = ['fast_code.py','query_knowledge.py','lint_project.py','detect_project.py','check_python_syntax.py','experience.py']
    help_count = 0
    for name in help_scripts:
        run(dev/name,'--help')
        help_count += 1
    for path in sorted(setup.glob('*.py')):
        if path.name not in ('compat.py','pathlib.py'):
            run(path,'--help')
            help_count += 1
    run(ROOT/'skills/mc-shader-reconstruction/scripts/model_to_shader/convert.py','--help')
    help_count += 1
    run(ROOT/'skills/mc-shader-reconstruction/scripts/model_to_shader/rigid_animation.py','--help')
    help_count += 1
    pack = temp/'generated-pack'
    run(dev/'fast_code.py','create-pack','--namespace','bundle_test','--out',pack,'--with-ui')
    for command, key in [('add-item','sample_item'),('add-block','sample_block'),('add-entity','sample_entity'),('add-animation','walk')]:
        run(dev/'fast_code.py',command,'--project',pack,'--namespace','bundle_test','--id',key)
    lint = run(dev/'lint_project.py','--project',pack)
    require('ERROR:' not in lint,'Generated pack failed lint')
    warnings = [line for line in lint.splitlines() if line.startswith('WARN:')]
    require(len(warnings)==2 and all(token in '\n'.join(warnings) for token in
            ('references geometry geometry.sample_entity','references texture textures/entity/sample_entity/sample_entity')),
            'Generated starter pack has unexpected lint warnings: '+lint)
    api = temp/'api'
    api.mkdir()
    (api/'api-index.md').write_text('Fixture API index',encoding='utf-8')
    (api/'interfaces.md').write_text('GetPos fixture official API entry',encoding='utf-8')
    registry = temp/'knowledge_registry.json'
    registry.write_text(json.dumps({'api_references':str(api)}),encoding='utf-8')
    digest_before = registry.read_bytes()
    ready = json.loads(run(setup/'knowledge_status.py','--registry',registry,'--require','api_references'))
    require(ready['status']=='READY','Selected source not recognized')
    missing = json.loads(run(setup/'knowledge_status.py','--registry',registry,'--require','demo_index',expected=1))
    require(missing['missing_required']==['demo_index'],'Missing source status incorrect')
    query = run(dev/'query_knowledge.py','GetPos','--source','api','--api-only','--registry',registry)
    require('GetPos' in query,'Query disconnected from existing registry')
    require(registry.read_bytes()==digest_before,'Read-only query/status changed registry')
    registry.write_text('[]',encoding='utf-8')
    invalid = json.loads(run(setup/'knowledge_status.py','--registry',registry,expected=1))
    require('error' in invalid,'Invalid registry lacks diagnostic')
    # Exercise relocated index orchestration on the tiny generated pack only.
    index_root = temp/'index-data'
    run(setup/'prepare_knowledge.py','--root',index_root,'--demo-source',pack,'--pretty')
    built_registry = index_root/'knowledge_registry.json'
    demo_query = run(dev/'query_knowledge.py','bundle_test','--source','demo','--registry',built_registry)
    require('bundle_test' in demo_query,'Relocated demo indexing/query failed')
    run(setup/'index_custom_project.py','--project',pack,'--root',index_root,'--pretty')
    custom_query = run(dev/'query_knowledge.py','bundle_test','--source','custom','--registry',built_registry)
    require('bundle_test' in custom_query,'Relocated custom indexing/query failed')
    built = json.loads(built_registry.read_text(encoding='utf-8'))
    require(built.get('demo_index') and built.get('custom_project_indexes'),'Registry sources were lost during update')
    return dict(help_scripts=help_count,scaffold=True,lint='PASS_WITH_EXPECTED_MISSING_STARTER_MODEL_AND_TEXTURE',
                fixture_query=True,selected_source=True,invalid_registry=True,local_index_roundtrip=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report',type=Path,help='Optional JSON report outside the bundle')
    args = parser.parse_args()
    result = dict(bundle='mc-be-hub-skills',status='RUNNING',knowledge_modified=False,
                  minecraft_runtime_tested=False,client_ui_tested=False)
    try:
        result['structure'] = structure()
        result['sources'] = source_checks()
        with tempfile.TemporaryDirectory(prefix='mc-be-hub-check-') as folder:
            temp = Path(folder)
            result['installation'] = install_smoke(temp)
            result['cli'] = cli_smoke(temp)
        result['status'] = 'PASS'
    except (ValueError,OSError,SyntaxError,subprocess.SubprocessError) as error:
        result['status'] = 'FAIL'
        result['error'] = str(error)
    if args.report:
        require(not args.report.resolve().is_relative_to(ROOT),'Write reports outside the distributable bundle')
        args.report.parent.mkdir(parents=True,exist_ok=True)
        args.report.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if result['status']=='PASS' else 1


if __name__=='__main__':
    raise SystemExit(main())
