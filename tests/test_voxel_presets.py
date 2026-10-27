"""Verify preset/custom CLI behavior independently of Blender imports."""
import ast
import argparse
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
CONVERTER=ROOT/'skills/mc-model-animation-to-blockbench/scripts/asset_to_bbmodel/convert.py'

class VoxelPresets(unittest.TestCase):
    def test_default_four_presets_and_custom_resolution(self):
        source=ast.parse(CONVERTER.read_text(encoding='utf8'))
        parser_fn=next(n for n in source.body if isinstance(n,ast.FunctionDef) and n.name=='parser')
        module=ast.Module(body=[parser_fn],type_ignores=[])
        scope={'argparse':argparse,'Path':Path,'__doc__':'CLI fixture'}
        exec(compile(module,str(CONVERTER),'exec'),scope)
        parser=scope['parser']()
        self.assertEqual(parser.parse_args(['source.obj','output']).voxel_resolution,80)
        for resolution in (48,80,112,144,96,160):
            with self.subTest(resolution=resolution):
                result=parser.parse_args(['source.obj','output','--voxel-resolution',str(resolution)])
                self.assertEqual(result.voxel_resolution,resolution)
                self.assertEqual(result.max_voxel_cells,4000000)

if __name__=='__main__':
    unittest.main()
