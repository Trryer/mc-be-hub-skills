"""Small portable regressions for custom atlas contract checking."""
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

from check_shader_contract import check


class ContractChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root/'field.json').write_text(json.dumps({
            'atlas':{'columns':12,'size':[64,32]}}),encoding='utf-8')
        (self.root/'atlas.png').write_bytes(
            b'\x89PNG\r\n\x1a\n'+struct.pack('>I',13)+b'IHDR'+struct.pack('>II',64,32))
        self.contract = self.root/'contract.json'
        self.contract.write_text(json.dumps({'metadata':'field.json',
            'constants':{'UV_COLUMNS':'atlas.columns','UV_SIZE':'atlas.size'},
            'textures':[{'file':'atlas.png','size':'atlas.size'}]}),encoding='utf-8')
        self.shader = self.root/'model.fragment'

    def write_shader(self, columns):
        self.shader.write_text('const float COLUMNS=%s;\n'
            'const float UV_COLUMNS=COLUMNS;\n'
            'const vec2 UV_SIZE=vec2(64,32);\n'%columns,encoding='utf-8')

    def test_wrong_slice_columns_fail_and_corrected_columns_pass(self):
        self.write_shader(10)
        before=check(self.contract,self.shader,1e-6)
        self.assertEqual(before['status'],'FAIL')
        self.assertEqual([row['constant'] for row in before['checks'] if not row['pass']],['UV_COLUMNS'])
        self.write_shader(12)
        self.assertEqual(check(self.contract,self.shader,1e-6)['status'],'PASS')

    def test_png_size_mismatch_fails(self):
        self.write_shader(12)
        (self.root/'atlas.png').write_bytes(
            b'\x89PNG\r\n\x1a\n'+struct.pack('>I',13)+b'IHDR'+struct.pack('>II',32,64))
        report=check(self.contract,self.shader,1e-6)
        self.assertEqual(report['status'],'FAIL')
        self.assertFalse(report['checks'][-1]['pass'])

    def test_unknown_expression_is_not_silently_accepted(self):
        self.write_shader('6*2')
        report=check(self.contract,self.shader,1e-6)
        self.assertEqual(report['status'],'FAIL')
        self.assertIn('Unsupported expression',report['checks'][0]['error'])

    def test_cli_exit_codes_and_report(self):
        script=Path(__file__).with_name('check_shader_contract.py')
        for columns,expected in [(10,1),(12,0)]:
            self.write_shader(columns)
            process=subprocess.run([sys.executable,'-B',str(script),'--contract',str(self.contract),
                                    '--shader',str(self.shader)],capture_output=True,text=True,encoding='utf-8')
            self.assertEqual(process.returncode,expected,process.stderr)
            self.assertEqual(json.loads(process.stdout)['status'],'PASS' if expected==0 else 'FAIL')


if __name__=='__main__':
    unittest.main()
