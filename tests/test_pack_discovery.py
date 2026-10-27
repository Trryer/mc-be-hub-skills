import json
import io
import sys
import tempfile
import unittest
import uuid
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock


SCRIPTS = Path(__file__).resolve().parents[1] / 'skills' / 'mc-bedrock-fast-code' / 'scripts'
sys.path.insert(0, str(SCRIPTS))

import pack_discovery  # noqa: E402
import lint_project  # noqa: E402


def write_manifest(folder, module_type, header_name=None, header_uuid=None, filename='manifest.json'):
    folder.mkdir(parents=True, exist_ok=True)
    data = {
        'header': {
            'name': header_name if header_name is not None else folder.name,
            'uuid': header_uuid or str(uuid.uuid4()),
        },
        'modules': [{'type': module_type}],
    }
    (folder / filename).write_text(json.dumps(data), encoding='utf-8')


class PackDiscoveryTests(unittest.TestCase):
    def test_discovers_arbitrary_folder_names_by_manifest_content(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            write_manifest(root / 'gameplay_files', 'data', filename='pack_manifest.json')
            write_manifest(root / 'visual_files', 'resources')

            result = pack_discovery.discover_packs(root)

            self.assertEqual(['gameplay_files'], [pack['folder'] for pack in result['packs']['behavior']])
            self.assertEqual(['visual_files'], [pack['folder'] for pack in result['packs']['resource']])

    def test_rejects_header_name_mismatch(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            write_manifest(root / 'actual_folder', 'data', header_name='wrong_folder')

            result = pack_discovery.discover_packs(root)

            self.assertEqual([], result['packs']['behavior'])
            self.assertIn('does not match folder name', result['manifests'][0]['errors'][0])

    def test_scans_pack_folders_at_depth_two_but_not_depth_three(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            write_manifest(root / 'wrapper' / 'depth_two_pack', 'resources')
            write_manifest(root / 'one' / 'two' / 'depth_three_pack', 'data')

            result = pack_discovery.discover_packs(root, max_depth=2)

            self.assertEqual(['depth_two_pack'], [pack['folder'] for pack in result['packs']['resource']])
            self.assertEqual([], result['packs']['behavior'])
            self.assertEqual(1, len(result['manifests']))

    def test_rejects_unknown_module_type(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            write_manifest(root / 'script_pack', 'script')

            result = pack_discovery.discover_packs(root)

            self.assertEqual([], result['packs']['behavior'])
            self.assertEqual([], result['packs']['resource'])
            self.assertIn('unsupported modules[].type', result['manifests'][0]['errors'][0])

    def test_generic_web_manifest_is_not_a_pack_manifest(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'manifest.json').write_text(json.dumps({'name': 'web app'}), encoding='utf-8')

            result = pack_discovery.discover_packs(root)

            self.assertFalse(result['manifests'][0]['is_pack_manifest'])
            self.assertEqual([], result['packs']['behavior'])
            self.assertEqual([], result['packs']['resource'])

    def test_linter_accepts_multiple_packs_of_each_type(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            write_manifest(root / 'behavior_one', 'data')
            write_manifest(root / 'behavior_two', 'data')
            write_manifest(root / 'resource_one', 'resources')
            write_manifest(root / 'resource_two', 'resources')
            discovery = pack_discovery.discover_packs(root)
            errors = []

            behaviors = lint_project.select_packs(discovery, 'behavior', errors)
            resources = lint_project.select_packs(discovery, 'resource', errors)

            self.assertEqual(2, len(behaviors))
            self.assertEqual(2, len(resources))
            self.assertEqual([], errors)

    def test_linter_accepts_a_single_pack_type(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            write_manifest(root / 'behavior_only', 'data')
            discovery = pack_discovery.discover_packs(root)
            errors = []

            behaviors = lint_project.select_packs(discovery, 'behavior', errors)
            resources = lint_project.select_packs(discovery, 'resource', errors)

            self.assertEqual(1, len(behaviors))
            self.assertEqual([], resources)
            self.assertEqual([], errors)

    def test_two_manifest_filenames_in_one_folder_count_as_one_pack(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            folder = root / 'shared_pack'
            write_manifest(folder, 'data', filename='manifest.json')
            write_manifest(folder, 'data', filename='pack_manifest.json')

            result = pack_discovery.discover_packs(root)

            self.assertEqual(1, len(result['packs']['behavior']))

    def test_rejects_duplicate_header_uuid_across_pack_folders(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            shared_uuid = str(uuid.uuid4())
            write_manifest(root / 'behavior_one', 'data', header_uuid=shared_uuid)
            write_manifest(root / 'resource_one', 'resources', header_uuid=shared_uuid)

            result = pack_discovery.discover_packs(root)

            self.assertEqual([], result['packs']['behavior'])
            self.assertEqual([], result['packs']['resource'])
            self.assertTrue(all('duplicated across pack folders' in item['errors'][-1] for item in result['manifests']))

    def test_linter_fails_for_duplicate_header_uuid(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            shared_uuid = str(uuid.uuid4())
            write_manifest(root / 'behavior_one', 'data', header_uuid=shared_uuid)
            write_manifest(root / 'resource_one', 'resources', header_uuid=shared_uuid)
            output = io.StringIO()

            with mock.patch.object(sys, 'argv', ['lint_project.py', '--project', str(root)]):
                with redirect_stdout(output):
                    exit_code = lint_project.main()

            self.assertEqual(1, exit_code)
            self.assertIn('duplicated across pack folders', output.getvalue())


if __name__ == '__main__':
    unittest.main()
