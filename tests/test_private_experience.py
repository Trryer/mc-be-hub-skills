"""Protect external record storage and the public distribution boundary."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT=Path(__file__).resolve().parents[1]

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

experience=load('private_experience',ROOT/'skills/mc-bedrock-fast-code/scripts/experience.py')
package=load('public_package',ROOT/'scripts/package_bundle.py')

class PrivateRecords(unittest.TestCase):
    def test_direct_cli_uses_standard_python3_pathlib(self):
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'external'
            result=subprocess.run([sys.executable,'-B',str(experience.SKILL/'scripts/experience.py'),
                                   '--root',str(target),'path'],capture_output=True,text=True,encoding='utf8',
                                  env=dict(os.environ,PYTHONIOENCODING='utf-8'))
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertIs(json.loads(result.stdout)['available'],False)
            self.assertFalse(target.exists())

    def test_external_unicode_add_search_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)/'data'
            self.assertEqual(experience.search(root),[])
            self.assertFalse(root.exists())
            body=Path(folder)/'body.md'
            body.write_text('## 验证\n已确认的测试记录。',encoding='utf8')
            result=experience.add(root,'fixture','测试标题',body)
            self.assertTrue(Path(result['path']).is_file())
            self.assertEqual(len(experience.search(root,'确认')),1)
            self.assertEqual(experience.search(root,'absent'),[])
            with self.assertRaises(FileExistsError):
                experience.add(root,'fixture','替代标题',body)
            with self.assertRaises(ValueError):
                experience.add(root,'../escape','标题',body)

    def test_bundled_storage_rejected_and_snapshots_not_searched(self):
        for path in (ROOT,ROOT/'private',experience.SKILL/'notes'):
            with self.assertRaises(ValueError):
                experience.storage(path)
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            (root/'snapshots').mkdir()
            (root/'snapshots/private.md').write_text('fixture',encoding='utf8')
            self.assertEqual(experience.search(root),[])

    def test_public_archive_boundary(self):
        with tempfile.TemporaryDirectory() as folder:
            temp=Path(folder)
            root=temp/'source'
            (root/'skills/sample').mkdir(parents=True)
            (root/'skills/sample/SKILL.md').write_text('public capability',encoding='utf8')
            (root/'private').mkdir()
            (root/'private/record.md').write_text('not public',encoding='utf8')
            out=temp/'public.zip'
            package.build(out,root)
            with zipfile.ZipFile(out) as archive:
                self.assertEqual(archive.namelist(),['mc-be-hub-skills/skills/sample/SKILL.md'])
            (root/'skills/sample/references/experience').mkdir(parents=True)
            (root/'skills/sample/references/experience/record.md').write_text('record',encoding='utf8')
            with self.assertRaises(ValueError):
                package.build(out,root)

if __name__=='__main__':
    unittest.main()
