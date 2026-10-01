"""Synthetic archive fixtures only; tests never execute source or payloads."""
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import struct
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import rc_consumer_archive as archive
from rc_consumer_io import ConsumerError, PrivateRoot


def synthetic_tar(entries=None):
    elf = b'\x7fELF\x02\x01' + b'\0' * 12 + b'\x3e\x00' + b'synthetic ELF, never execute'
    manifest = {'binaries': {name: {'size': len(elf), 'sha256': hashlib.sha256(elf).hexdigest()}
                             for name in archive.BINS}}
    if entries is None:
        entries = [(name, elf if name.startswith('bin/') else
                    json.dumps(manifest).encode() if name == 'manifest.json' else b'synthetic documentation')
                   for name in sorted(archive.CLOUD_MEMBERS)]
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode='w', format=tarfile.USTAR_FORMAT) as target:
        for name, data in entries:
            info = tarfile.TarInfo(name)
            info.mode = 0o755 if name.startswith('bin/') else 0o644
            info.size = len(data)
            target.addfile(info, io.BytesIO(data))
    return stream.getvalue(), manifest


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.parent = Path(self.temp.name)
        self.source = self.parent / 'checkout'
        self.source.mkdir()
        (self.source / 'unchanged').write_bytes(b'unchanged')
        self.number = 0

    def root(self):
        result = PrivateRoot(self.parent, 'extract-', source_root=self.source)
        self.addCleanup(result.close)
        return result

    def file(self, data):
        self.number += 1
        path = self.parent / str(self.number)
        path.write_bytes(data)
        return path

    def zip(self, entries, compression=zipfile.ZIP_DEFLATED, zip64=False):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w', compression) as target:
            for name, data in entries:
                if zip64:
                    with target.open(name, 'w', force_zip64=True) as output:
                        output.write(data)
                else:
                    target.writestr(name, data)
        return self.file(stream.getvalue())

    def extract_zip(self, path):
        root = self.root()
        archive.extract_bounded_zip(path, root, {'payload.exe'})
        return root

    def reject_zip(self, path, code=None):
        with self.assertRaises(ConsumerError) as error:
            self.extract_zip(path)
        if code:
            self.assertEqual(error.exception.code, code)
        self.assertEqual((self.source / 'unchanged').read_bytes(), b'unchanged')

    def reject_tar(self, data, code=None):
        with self.assertRaises(ConsumerError) as error:
            archive.extract_bounded_cloud_tar(self.file(data), self.root())
        if code:
            self.assertEqual(error.exception.code, code)
        self.assertEqual((self.source / 'unchanged').read_bytes(), b'unchanged')

    def test_positive_zip_checksum_modes_and_zip64_local(self):
        for zip64 in (False, True):
            entries = [('payload.exe', b'payload'), ('evidence/a.json', b'{}')]
            sums = ''.join(hashlib.sha256(data).hexdigest() + '  ' + name + '\n' for name, data in entries)
            root = self.extract_zip(self.zip(entries + [('SHA256SUMS.txt', sums.encode())], zip64=zip64))
            self.assertEqual(set(archive.verify_checksum_inventory(root)), {'payload.exe', 'evidence/a.json'})
            self.assertTrue(all((root.path / name).stat().st_mode & 0o777 == 0o600 for name in root.files()))

    def test_zip64_eocd_within_bounds(self):
        path = self.zip([('payload.exe', b'payload')])
        data = path.read_bytes()
        values = list(struct.unpack('<4s4H2IH', data[-22:]))
        count, size, offset = values[4:7]
        end64 = struct.pack('<4sQ2H2I4Q', b'PK\x06\x06', 44, 45, 45, 0, 0, count, count, size, offset)
        locator = struct.pack('<4sIQI', b'PK\x06\x07', 0, len(data) - 22, 1)
        values[3:7] = [0xffff, 0xffff, 0xffffffff, 0xffffffff]
        result = self.extract_zip(self.file(data[:-22] + end64 + locator + struct.pack('<4s4H2IH', *values)))
        self.assertEqual(result.read('payload.exe'), b'payload')

    def test_streaming_zip_data_descriptor(self):
        class Unseekable(io.BytesIO):
            def seekable(self):
                return False
            def seek(self, *args):
                raise io.UnsupportedOperation()
        stream = Unseekable()
        with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as target:
            target.writestr('payload.exe', b'payload')
        self.assertEqual(self.extract_zip(self.file(stream.getvalue())).read('payload.exe'), b'payload')

    def test_zip_paths_duplicates_aliases_and_collisions(self):
        names = ['/absolute', '../up', 'evidence/../up', 'C:/drive', '//unc/a', 'evidence/a:b',
                 'evidence/back\\slash', 'evidence/double//a', 'evidence/./a', 'evidence/new\nline',
                 'unknown.exe', 'evidence/' + 'x' * 1024]
        for name in names:
            with self.subTest(name=name):
                self.reject_zip(self.zip([(name, b'blocked')]))
        pairs = [('evidence/a', 'evidence/a'), ('evidence/A', 'evidence/a'),
                 ('evidence/é', 'evidence/e\u0301'), ('evidence/file', 'evidence/file/child'),
                 ('evidence/UP/one', 'evidence/up/two')]
        for left, right in pairs:
            with self.subTest(left=left, right=right):
                self.reject_zip(self.zip([(left, b'x'), (right, b'y')]))

    def test_zip_symlink_device_and_unsupported_compression(self):
        for mode in (stat.S_IFLNK, stat.S_IFCHR, stat.S_IFIFO, stat.S_IFSOCK, stat.S_IFBLK):
            info = zipfile.ZipInfo('payload.exe')
            info.create_system = 3
            info.external_attr = (mode | 0o777) << 16
            self.reject_zip(self.zip([(info, b'blocked')]), 'zip_special_member')
        self.reject_zip(self.zip([('payload.exe', b'data')], zipfile.ZIP_BZIP2), 'unsupported_zip_member')

    def test_zip_encryption_crc_and_contradictory_sizes(self):
        original = self.zip([('payload.exe', b'payload')], zipfile.ZIP_STORED).read_bytes()
        central = original.index(b'PK\x01\x02')
        for offset, format_, value in ((6, '<H', 1), (central + 8, '<H', 1),
                                       (14, '<I', 1234), (18, '<I', 999)):
            data = bytearray(original)
            struct.pack_into(format_, data, offset, value)
            self.reject_zip(self.file(data))
        data = bytearray(original)
        data[30 + len('payload.exe')] ^= 1
        self.reject_zip(self.file(data), 'invalid_zip')

    def test_zip_limits_checked_before_library_allocation(self):
        original = self.zip([('payload.exe', b'x')]).read_bytes()
        for offset, format_, value in ((-12, '<I', archive.DIRECTORY_LIMIT + 1),
                                       (-14, '<H', archive.ENTRY_LIMIT + 1)):
            data = bytearray(original)
            struct.pack_into(format_, data, len(data) + offset, value)
            with patch.object(archive.zipfile, 'ZipFile', side_effect=AssertionError('parser reached')):
                self.reject_zip(self.file(data))
        central = original.index(b'PK\x01\x02')
        data = bytearray(original)
        struct.pack_into('<H', data, central + 28, archive.PATH_LIMIT + 1)
        with patch.object(archive.zipfile, 'ZipFile', side_effect=AssertionError('parser reached')):
            self.reject_zip(self.file(data))

    def test_zip_count_ratio_and_absolute_size_limits(self):
        path = self.zip([('payload.exe', b'payload'), ('evidence/a', b'x')])
        with patch.object(archive, 'ENTRY_LIMIT', 1):
            self.reject_zip(path)
        with patch.object(archive, 'FILE_LIMIT', 4):
            self.reject_zip(path)
        with patch.object(archive, 'TOTAL_LIMIT', 4):
            self.reject_zip(path)
        with patch.object(archive, 'RATIO_LIMIT', 1):
            self.reject_zip(self.zip([('payload.exe', b'x' * 1000)]))

    def test_zip_hidden_prefix_suffix_comment_and_second_archive(self):
        raw = self.zip([('payload.exe', b'payload')]).read_bytes()
        for data in (b'prefix' + raw, raw + b'junk', raw + raw, raw[:-2] + b'\x04\x00junk'):
            self.reject_zip(self.file(data))

    def test_checksums_exact_coverage_grammar_and_hash(self):
        digest = hashlib.sha256(b'payload').hexdigest()
        values = [digest + '  payload.exe\n', digest + ' *payload.exe\n', digest.upper() + '  payload.exe\n',
                  digest + '  ../outside\n', digest + '  payload.exe\n' * 2, '# comment\n',
                  digest + '  payload.exe', '0' * 64 + '  payload.exe\n', digest + '  absent\n']
        for index, text in enumerate(values):
            root = self.extract_zip(self.zip([('payload.exe', b'payload'), ('SHA256SUMS.txt', text.encode())]))
            if index == 0:
                archive.verify_checksum_inventory(root)
            else:
                with self.subTest(index=index), self.assertRaises(ConsumerError):
                    archive.verify_checksum_inventory(root)
        root = self.extract_zip(self.zip([('payload.exe', b'payload'), ('evidence/extra', b'extra'),
                                         ('SHA256SUMS.txt', values[0].encode())]))
        with self.assertRaises(ConsumerError):
            archive.verify_checksum_inventory(root)

    def test_positive_cloud_manifest_elf_and_nonexecutable_modes(self):
        data, expected = synthetic_tar()
        root = self.root()
        actual = archive.extract_bounded_cloud_tar(self.file(gzip.compress(data)), root)
        self.assertEqual(actual, expected)
        self.assertEqual(set(root.files()), archive.CLOUD_MEMBERS)
        self.assertTrue(all((root.path / name).stat().st_mode & 0o777 == 0o600 for name in root.files()))

    def test_tar_extensions_rejected_before_body_handler_or_allocation(self):
        for type_ in (tarfile.XHDTYPE, tarfile.XGLTYPE, tarfile.GNUTYPE_LONGNAME,
                      tarfile.GNUTYPE_LONGLINK, tarfile.GNUTYPE_SPARSE, tarfile.SOLARIS_XHDTYPE):
            info = tarfile.TarInfo('manifest.json')
            info.type = type_
            info.size = 2**40
            data = gzip.compress(info.tobuf(format=tarfile.GNU_FORMAT))
            with (patch.object(tarfile.TarInfo, '_proc_pax', side_effect=AssertionError('PAX body read')),
                 patch.object(tarfile.TarInfo, '_proc_gnulong', side_effect=AssertionError('GNU body read')),
                 patch.object(tarfile.TarInfo, '_proc_sparse', side_effect=AssertionError('sparse body read'))):
                self.reject_tar(data, 'tar_extension_or_special')

    def test_tar_special_modes_duplicate_missing_and_wrong_name(self):
        for type_ in (tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.CHRTYPE, tarfile.BLKTYPE, tarfile.FIFOTYPE, tarfile.DIRTYPE):
            info = tarfile.TarInfo('manifest.json')
            info.type = type_
            self.reject_tar(gzip.compress(info.tobuf()), 'tar_extension_or_special')
        for name in ('../up', '/abs', 'bin/../up', 'manifest.JSON', 'bin/other'):
            raw, _ = synthetic_tar([(name, b'data')])
            self.reject_tar(gzip.compress(raw))
        raw, _ = synthetic_tar([('README.md', b'one'), ('README.md', b'two')])
        self.reject_tar(gzip.compress(raw), 'duplicate_archive_member')
        raw, _ = synthetic_tar([('README.md', b'one')])
        self.reject_tar(gzip.compress(raw), 'tar_member_inventory')
        info = tarfile.TarInfo('manifest.json')
        info.size = 2**30
        info.mode = 0o644
        self.reject_tar(gzip.compress(info.tobuf()), 'tar_member_metadata')
        info.size = 1
        info.mode = 0o755
        self.reject_tar(gzip.compress(info.tobuf() + b'x' + b'\0' * 1023), 'tar_member_metadata')

    def test_gzip_crc_trailer_truncation_concatenation_and_tar_trailing(self):
        raw, _ = synthetic_tar()
        data = gzip.compress(raw)
        bad_crc = bytearray(data)
        bad_crc[-8] ^= 1
        for payload in (data[:-1], data[:-8], bytes(bad_crc), data + gzip.compress(b'other'), data + b'junk',
                        gzip.compress(raw + b'nonpadding'), gzip.compress(raw + raw), gzip.compress(raw[:1024])):
            self.reject_tar(payload)

    def test_gzip_reader_rejects_unbounded_and_oversize_reads(self):
        data, _ = synthetic_tar()
        with self.file(gzip.compress(data)).open('rb') as raw:
            reader = archive._GzipReader(raw)
            for size in (-1, None, archive.CHUNK + 1, True):
                with self.subTest(size=size), self.assertRaises(ConsumerError):
                    reader.read(size)
        with patch.object(archive, 'TAR_TOTAL_LIMIT', 100):
            self.reject_tar(gzip.compress(data), 'tar_expansion_limit')

    def test_cloud_wrong_binary_record_hash_and_elf(self):
        raw, _ = synthetic_tar()
        with tarfile.open(fileobj=io.BytesIO(raw)) as source:
            entries = [(item.name, source.extractfile(item).read()) for item in source]
        for fault in ('bool', 'hash', 'elf'):
            changed = []
            for name, data in entries:
                if name == 'manifest.json' and fault in {'bool', 'hash'}:
                    manifest = json.loads(data)
                    record = manifest['binaries'][archive.BINS[0]]
                    record['size' if fault == 'bool' else 'sha256'] = True if fault == 'bool' else '0' * 64
                    data = json.dumps(manifest).encode()
                if name == 'bin/' + archive.BINS[0] and fault == 'elf':
                    data = b'not ELF' + data[7:]
                changed.append((name, data))
            bad, _ = synthetic_tar(changed)
            self.reject_tar(gzip.compress(bad))

    def test_deflated_member_cannot_hide_trailing_stream(self):
        original = self.zip([('payload.exe', b'payload')]).read_bytes()
        central = original.index(b'PK\x01\x02')
        hidden = b'PK\x03\x04hidden archive bytes'
        data = bytearray(original[:central] + hidden + original[central:])
        original_size = struct.unpack_from('<I', original, 18)[0]
        struct.pack_into('<I', data, 18, original_size + len(hidden))
        struct.pack_into('<I', data, central + len(hidden) + 20, original_size + len(hidden))
        struct.pack_into('<I', data, len(data) - 6, central + len(hidden))
        self.reject_zip(self.file(data), 'zip_hidden_data')

    def test_raw_nul_invalid_utf8_and_unknown_extra_rejected(self):
        original = self.zip([('payload.exe', b'payload')]).read_bytes()
        central = original.index(b'PK\x01\x02')
        data = bytearray(original)
        data[30] = data[central + 46] = 0
        self.reject_zip(self.file(data), 'unsafe_path')
        data = bytearray(original)
        data[30] = data[central + 46] = 0xff
        struct.pack_into('<H', data, 6, 0x800)
        struct.pack_into('<H', data, central + 8, 0x800)
        self.reject_zip(self.file(data), 'invalid_zip')
        info = zipfile.ZipInfo('payload.exe')
        info.extra = struct.pack('<HH', 0x7075, 1) + b'\x01'
        with patch.object(archive.zipfile, 'ZipFile', wraps=zipfile.ZipFile) as parser:
            path = self.zip([(info, b'data')])
            calls = parser.call_count
            self.reject_zip(path, 'unsupported_zip_extra')
            self.assertEqual(parser.call_count, calls)

    def test_tar_read_sizes_bounded_and_huge_pax_stops_at_header(self):
        original_read = archive._GzipReader.read
        requests = []
        totals = []
        def checked_read(reader, size):
            self.assertIs(type(size), int)
            self.assertGreaterEqual(size, 0)
            self.assertLessEqual(size, archive.CHUNK)
            requests.append(size)
            data = original_read(reader, size)
            totals.append(reader.total)
            return data
        info = tarfile.TarInfo('manifest.json')
        info.type = tarfile.XHDTYPE
        info.size = 2**40
        with patch.object(archive._GzipReader, 'read', checked_read):
            self.reject_tar(gzip.compress(info.tobuf(format=tarfile.GNU_FORMAT)), 'tar_extension_or_special')
        self.assertEqual(requests, [512])
        self.assertEqual(totals, [512])
        requests.clear()
        raw, _ = synthetic_tar()
        with patch.object(archive._GzipReader, 'read', checked_read):
            archive.extract_bounded_cloud_tar(self.file(gzip.compress(raw)), self.root())
        self.assertTrue(requests)

    def test_tar_invalid_header_after_members_does_not_look_like_eof(self):
        raw, _ = synthetic_tar()
        with tarfile.open(fileobj=io.BytesIO(raw)) as source:
            members = source.getmembers()
        end = max(m.offset_data + (m.size + 511) // 512 * 512 for m in members)
        corrupted = raw[:end] + b'X' * 512 + raw[end + 512:]
        self.reject_tar(gzip.compress(corrupted), 'invalid_tar_header')

    def test_subprocess_and_system_execution_absent(self):
        import subprocess
        raw, _ = synthetic_tar()
        with (patch.object(subprocess, 'run', side_effect=AssertionError('executed')),
              patch.object(subprocess, 'Popen', side_effect=AssertionError('executed')),
              patch.object(os, 'system', side_effect=AssertionError('executed'))):
            self.extract_zip(self.zip([('payload.exe', b'not executable')]))
            archive.extract_bounded_cloud_tar(self.file(gzip.compress(raw)), self.root())


if __name__ == '__main__':
    unittest.main()
