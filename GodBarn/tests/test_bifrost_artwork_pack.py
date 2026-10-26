"""Artwork supplements use reviewed Barn metadata and local Barn copies only."""
import copy
import gzip
import importlib.util
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/pack_bifrost_artwork.py'
SPEC = importlib.util.spec_from_file_location('barn_artwork_pack_tests', SCRIPT)
packer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(packer)


class BarnArtworkPackTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='barn-artwork-pack-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve() / 'GodBarn'
        (self.root / '.build').mkdir(parents=True)
        self.output = self.root / '.build/artwork.tar.gz'
        self.copies = {
            'static/assets/items/' + 'a' * 32 + '.PNG': b'exact selected first artwork\x00\xff',
            'static/assets/items/' + 'b' * 64 + '.webp': b'exact selected second artwork',
            'static/assets/items/' + 'c' * 32 + '.png': b'unselected later duplicate artwork',
        }
        self.records = []
        self.rows = []
        self.mapping = {}
        for index, (path, contents) in enumerate(self.copies.items()):
            source = self.root / path
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_bytes(contents)
            record = {'path': path, 'sha256': packer.digest(contents), 'bytes': len(contents),
                      'assetPath': 'animals/' + Path(path).name}
            self.records.append(record)
            self.mapping[path] = record['assetPath']
            self.rows.append({'name': 'first' if index in (0, 2) else 'second', 'image': '/' + path,
                              'artwork': {'status': 'exact', 'sha256': record['sha256'],
                                          'bytes': record['bytes']}})
        self.bundle = self.root / '.build' / packer.BUNDLE_NAME
        self.make_bundle()
        self.wanted = {'schema': 1, 'bundleSha256': self.bundle_sha,
                       'items': copy.deepcopy(self.records[:2])}

    def make_bundle(self):
        metadata = {
            'GodBarn/data/catalog.json.gz': gzip.compress(json.dumps(self.rows).encode()),
            'GodBarn/data/asset-map.json': json.dumps(self.mapping).encode(),
        }
        with tarfile.open(self.bundle, 'w:gz') as archive:
            for name, contents in metadata.items():
                member = tarfile.TarInfo(name)
                member.size = len(contents)
                archive.addfile(member, io.BytesIO(contents))
        self.bundle_sha = packer.digest(self.bundle.read_bytes())

    def pack(self, wanted=None, output=None):
        return packer.pack_artwork(self.wanted if wanted is None else wanted,
                                   self.output if output is None else output,
                                   barn_root=self.root, expected_bundle_sha256=self.bundle_sha)

    def test_only_requested_images_are_written_as_exact_regular_members(self):
        wanted = copy.deepcopy(self.wanted)
        wanted['items'] = wanted['items'][1:]
        result = self.pack(wanted)
        with tarfile.open(self.output, 'r:gz') as archive:
            members = archive.getmembers()
            self.assertEqual([member.name for member in members], ['GodBarn/' + self.records[1]['path']])
            self.assertTrue(members[0].isfile())
            self.assertEqual(archive.extractfile(members[0]).read(), self.copies[self.records[1]['path']])
            self.assertEqual(members[0].mtime, 0)
            self.assertEqual((members[0].uid, members[0].gid, members[0].mode), (0, 0, 0o644))
        self.assertEqual(result['items'], 1)
        self.assertEqual(result['bytes'], self.records[1]['bytes'])
        self.assertEqual(result['sha256'], packer.digest(self.output.read_bytes()))
        self.assertEqual(Path(str(self.output) + '.sha256').read_text(),
                         result['sha256'] + '  artwork.tar.gz\n')
        for path, contents in self.copies.items():
            self.assertEqual((self.root / path).read_bytes(), contents)

    def test_archives_are_deterministic_across_request_order_and_output_names(self):
        self.pack()
        first = self.output.read_bytes()
        wanted = copy.deepcopy(self.wanted)
        wanted['items'].reverse()
        other = self.output.with_name('second.tar.gz')
        self.pack(wanted, other)
        self.assertEqual(other.read_bytes(), first)

    def test_empty_request_produces_valid_empty_archive(self):
        wanted = copy.deepcopy(self.wanted)
        wanted['items'] = []
        result = self.pack(wanted)
        self.assertEqual(result['items'], 0)
        with tarfile.open(self.output, 'r:gz') as archive:
            self.assertEqual(archive.getmembers(), [])

    def test_wrong_request_identity_never_reads_local_image_copies(self):
        variants = []
        for field, value in (('sha256', '0' * 64), ('bytes', self.records[0]['bytes'] + 1),
                             ('bytes', True), ('assetPath', 'animals/some-other-art.png'),
                             ('assetPath', '../private.png'),
                             ('path', 'static/assets/items/../private.png'),
                             ('path', '/static/assets/items/' + 'a' * 32 + '.PNG'),
                             ('path', 'static/assets/items/' + 'a' * 32 + '.svg')):
            wanted = copy.deepcopy(self.wanted)
            wanted['items'][0][field] = value
            variants.append(wanted)
        wanted = copy.deepcopy(self.wanted)
        wanted['bundleSha256'] = '0' * 64
        variants.append(wanted)
        wanted = copy.deepcopy(self.wanted)
        wanted['schema'] = True
        variants.append(wanted)
        for wanted in variants:
            with self.subTest(wanted=wanted):
                with mock.patch.object(packer, 'read_regular', wraps=packer.read_regular) as read:
                    with self.assertRaises(ValueError):
                        self.pack(wanted)
                self.assertEqual([call.args[0] for call in read.call_args_list], [self.bundle])
                self.assertFalse(self.output.exists())

    def test_duplicate_requested_files_are_rejected(self):
        wanted = copy.deepcopy(self.wanted)
        wanted['items'] = [self.records[0], self.records[0]]
        with self.assertRaisesRegex(ValueError, 'Duplicate requested'):
            self.pack(wanted)
        self.assertFalse(self.output.exists())

    def test_later_name_duplicate_cannot_authorize_different_artwork(self):
        wanted = copy.deepcopy(self.wanted)
        wanted['items'] = [self.records[2]]
        with self.assertRaisesRegex(ValueError, 'differs from the reviewed catalog'):
            self.pack(wanted)
        self.assertFalse(self.output.exists())

    def test_edited_local_metadata_cannot_authorize_other_images(self):
        local_data = self.root / 'data'
        local_data.mkdir()
        (local_data / 'catalog.json').write_text(json.dumps(self.rows[::-1]))
        (local_data / 'asset-map.json').write_text(json.dumps({'arbitrary': '/etc/passwd'}))
        wanted = copy.deepcopy(self.wanted)
        wanted['items'] = [self.records[2]]
        with self.assertRaisesRegex(ValueError, 'differs from the reviewed catalog'):
            self.pack(wanted)

    def test_changed_prepared_bundle_is_rejected_before_reading_image_sources(self):
        original = self.bundle_sha
        self.bundle.write_bytes(self.bundle.read_bytes() + b'modified')
        self.assertEqual(self.bundle_sha, original)
        with mock.patch.object(packer, 'read_regular', wraps=packer.read_regular) as read:
            with self.assertRaisesRegex(ValueError, 'does not match its reviewed SHA256'):
                self.pack()
        self.assertEqual([call.args[0] for call in read.call_args_list], [self.bundle])

    def test_image_corruption_leaves_existing_output_and_checksum_unchanged(self):
        self.output.write_bytes(b'previous output')
        checksum = Path(str(self.output) + '.sha256')
        checksum.write_bytes(b'previous checksum')
        (self.root / self.records[1]['path']).write_bytes(b'broken')
        with self.assertRaisesRegex(ValueError, 'does not match the reviewed catalog'):
            self.pack()
        self.assertEqual(self.output.read_bytes(), b'previous output')
        self.assertEqual(checksum.read_bytes(), b'previous checksum')
        self.assertEqual(sorted(path.name for path in self.output.parent.iterdir()),
                         sorted([packer.BUNDLE_NAME, 'artwork.tar.gz', 'artwork.tar.gz.sha256']))

    def test_image_file_and_parent_links_cannot_read_outside_barn(self):
        outside = self.root.parent / 'outside-image'
        outside.write_bytes(self.copies[self.records[0]['path']])
        path = self.root / self.records[0]['path']
        path.unlink()
        path.symlink_to(outside)
        with self.assertRaisesRegex(ValueError, 'symbolic link'):
            self.pack()
        self.assertFalse(self.output.exists())
        path.unlink()
        path.write_bytes(outside.read_bytes())
        directory = path.parent
        moved = directory.with_name('moved-items')
        directory.rename(moved)
        directory.symlink_to(moved, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'symbolic link'):
            self.pack()
        self.assertFalse(self.output.exists())

    def test_bundle_and_output_links_are_rejected(self):
        moved = self.bundle.with_suffix('.original')
        self.bundle.rename(moved)
        self.bundle.symlink_to(moved)
        with self.assertRaisesRegex(ValueError, 'symbolic link'):
            self.pack()
        self.bundle.unlink()
        moved.rename(self.bundle)
        victim = self.output.with_name('victim')
        victim.write_bytes(b'untouched')
        self.output.symlink_to(victim)
        with self.assertRaisesRegex(ValueError, 'symbolic link'):
            self.pack()
        self.assertEqual(victim.read_bytes(), b'untouched')

    def test_base_bundle_and_source_images_cannot_be_output_targets(self):
        for path in (self.bundle, self.root / self.records[0]['path'],
                     self.root / self.records[2]['path']):
            with self.subTest(path=path):
                before = path.read_bytes()
                with self.assertRaises(ValueError):
                    self.pack(output=path)
                self.assertEqual(path.read_bytes(), before)

    def test_parent_traversal_cannot_alias_the_prepared_bundle_as_output(self):
        alias = self.bundle.parent / '..' / '.build' / self.bundle.name
        before = self.bundle.read_bytes()
        with self.assertRaisesRegex(ValueError, 'Unsafe supplement output'):
            self.pack(output=alias)
        self.assertEqual(self.bundle.read_bytes(), before)

    def test_duplicate_json_fields_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Duplicate JSON field'):
            packer.json_without_duplicate_keys('{"schema": 1, "schema": 1}')


if __name__ == '__main__':
    unittest.main()
