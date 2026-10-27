"""Rigid motion interchange: rotations, corrupt data, budgets and CLI contract."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

try:
    import numpy as np
    from PIL import Image
except ImportError:
    np = None

TOOL = Path(__file__).resolve().parents[1]/'skills/mc-shader-reconstruction/scripts/model_to_shader/rigid_animation.py'
if np is not None:
    spec = importlib.util.spec_from_file_location('rigid_animation_test', TOOL)
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)


@unittest.skipIf(np is None, 'Install model_to_shader requirements (NumPy, Pillow)')
class RigidAnimation(unittest.TestCase):
    def fixture(self):
        # Independent known rotations exercise all matrix->quaternion branches,
        # including sign continuity across 180 degrees and a nonidentity start.
        matrices = np.broadcast_to(np.eye(4), (5, 4, 4, 4)).copy()
        angles = np.radians([170, 175, 180, 185, 190])
        for axis in range(3):
            i, j = (axis+1) % 3, (axis+2) % 3
            matrices[:, axis, i, i] = matrices[:, axis, j, j] = np.cos(angles)
            matrices[:, axis, i, j] = -np.sin(angles)
            matrices[:, axis, j, i] = np.sin(angles)
        matrices[:, :, :3, 3] = np.arange(5)[:, None, None]*np.array([.2, -.4, .7])
        return np.linspace(2, 3, 5), matrices

    def test_roundtrip_rotations_and_all_frames(self):
        times, matrices = self.fixture()
        pixels, report = tool.encode(times, matrices)
        q, t = tool.decode(pixels, len(times), 4, report['translation_range'])
        vectors = np.broadcast_to(np.array([.3, -.7, 1.2]), (5, 4, 3))
        rotated = vectors+2*np.cross(q[:, :, :3], np.cross(q[:, :, :3], vectors)+q[:, :, 3:]*vectors)
        expected = np.einsum('...ij,...j->...i', matrices[:, :, :3, :3], vectors)
        self.assertTrue(np.allclose(rotated, expected, atol=1e-4))
        self.assertTrue(np.allclose(t, matrices[:, :, :3, 3], atol=1e-4))
        self.assertTrue(np.all(np.sum(q[:-1]*q[1:], axis=-1)>0))
        self.assertEqual(report['atlas'], [8, 16])
        self.assertLess(report['angular_quantization_error_degrees'], .01)
        self.assertAlmostEqual(report['duration_seconds'], 1)
        self.assertTrue(np.all(np.array(report['endpoint_rotation_degrees'])[:3] > 19.99))

    def test_reject_nonrigid_and_unrepresentable_data(self):
        times, matrices = self.fixture()
        for value in (1.1, -1):
            altered = matrices.copy()
            altered[0, 3, 0, 0] = value
            with self.assertRaisesRegex(ValueError, 'Rigid tracks'):
                tool.encode(times, altered)
        with self.assertRaisesRegex(ValueError, 'uniformly'):
            tool.encode([0, .1, .2, .5, 1], matrices)
        with self.assertRaisesRegex(ValueError, 'translation-range'):
            tool.encode(times, matrices, translation_range=.1)
        with self.assertRaisesRegex(ValueError, 'budget'):
            tool.encode(times, matrices, max_atlas=4)
        with self.assertRaisesRegex(ValueError, 'budget'):
            tool.encode(times, matrices, max_mib=.00001)
        altered = matrices.copy()
        altered[0, 0, 0, 0] = float('nan')
        with self.assertRaisesRegex(ValueError, 'non-finite'):
            tool.encode(times, altered)

    def test_cli_outputs_and_preserves_existing_work(self):
        times, matrices = self.fixture()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source, output = root/'motion.npz', root/'encoded'
            np.savez_compressed(source, times=times, transforms=matrices)
            command = [sys.executable, '-B', str(TOOL), str(source), str(output)]
            run = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            report = json.loads((output/'report.json').read_text(encoding='utf8'))
            self.assertEqual(report['status'], 'ENCODED')
            self.assertFalse(report['minecraft_runtime_tested'])
            with Image.open(output/'animation.png') as image:
                self.assertEqual(image.size, (8, 16))
            self.assertIn('msaPose', (output/'animation.glsl').read_text())
            before = (output/'animation.png').read_bytes()
            again = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(again.returncode, 0)
            self.assertEqual((output/'animation.png').read_bytes(), before)
            failed = subprocess.run(command[:4]+[str(root/'too-small'), '--translation-range', '.01'],
                                    capture_output=True, text=True)
            self.assertNotEqual(failed.returncode, 0)
            self.assertEqual(json.loads((root/'too-small/report.json').read_text())['status'], 'ERROR')


if __name__=='__main__':
    unittest.main()
