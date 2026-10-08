"""Bounded standard ZIP/TAR readers; artifact bytes are data, never programs."""
from __future__ import annotations
import hashlib
import os
import re
import stat
import struct
import tarfile
import unicodedata
import zipfile
import zlib

from rc_consumer_io import (CHUNK, FILE_LIMIT, JSON_LIMIT, PATH_LIMIT, ConsumerError,
                            PrivateRoot, _check_budget, hash_file, json_file, need, open_file, safe_relative)

ZIP_LIMIT = 2 * 1024**3
DIRECTORY_LIMIT = 8 * 1024**2
ENTRY_LIMIT = 4096
TOTAL_LIMIT = 4 * 1024**3
RATIO_LIMIT = 1000
EXTRA_LIMIT = 4096
TAR_MEMBER_LIMIT = 256 * 1024**2 - 1
TAR_TOTAL_LIMIT = 4 * TAR_MEMBER_LIMIT + 2 * 1024**2 + 20 * 1024
BINS = ('coding-tools-gateway', 'coding-tools-agent', 'coding-tools-control-gateway', 'coding-tools-mcp-gateway')
CLOUD_MEMBERS = {*(f'bin/{name}' for name in BINS), 'manifest.json', 'README.md'}


def _at(stream, offset, length):
    need(type(length) is int and 0 <= length <= DIRECTORY_LIMIT and offset >= 0, 'archive_read_limit')
    stream.seek(offset)
    data = stream.read(length)
    need(len(data) == length, 'truncated_zip')
    return data


def _extras(data):
    result = {}
    while data:
        need(len(data) >= 4, 'invalid_zip_extra')
        kind, size = struct.unpack('<HH', data[:4])
        need(kind in {1, 0x5455, 0x7875} and kind not in result and size <= len(data) - 4,
             'unsupported_zip_extra')
        result[kind] = data[4:4 + size]
        data = data[4 + size:]
    return result


def _directory_guard(stream):
    size = os.fstat(stream.fileno()).st_size
    need(22 <= size <= ZIP_LIMIT, 'zip_size_limit')
    end = size - 22
    record = struct.unpack('<4s4H2IH', _at(stream, end, 22))
    sig, disk, cd_disk, count_disk, count, cd_size, cd_offset, comment = record
    need(sig == b'PK\x05\x06' and disk == cd_disk == comment == 0, 'zip_end_record')
    if end >= 20 and _at(stream, end - 20, 4) == b'PK\x06\x07':
        _, disk64, offset64, disks = struct.unpack('<4sIQI', _at(stream, end - 20, 20))
        need(disk64 == 0 and disks == 1 and offset64 + 56 == end - 20, 'zip64_end_record')
        values = struct.unpack('<4sQ2H2I4Q', _at(stream, offset64, 56))
        sig64, length, _, version, disk64, cd_disk64, n_disk, n, length_cd, start_cd = values
        need(sig64 == b'PK\x06\x06' and length == 44 and version <= 45
             and disk64 == cd_disk64 == 0 and n_disk == n, 'zip64_end_record')
        for old, sentinel, actual in ((count, 0xffff, n), (count_disk, 0xffff, n),
                                       (cd_size, 0xffffffff, length_cd), (cd_offset, 0xffffffff, start_cd)):
            need(old in {sentinel, actual}, 'contradictory_zip64_metadata')
        count = count_disk = n
        cd_size, cd_offset, end = length_cd, start_cd, offset64
    need(0 < count == count_disk <= ENTRY_LIMIT and 0 < cd_size <= DIRECTORY_LIMIT
         and cd_offset + cd_size == end, 'zip_directory_limit')
    position = cd_offset
    # Guard actual count and variable metadata before ZipFile allocates ZipInfos.
    for _ in range(count):
        need(position + 46 <= end, 'zip_directory_count')
        header = struct.unpack(zipfile.structCentralDir, _at(stream, position, 46))
        need(header[0] == b'PK\x01\x02', 'zip_directory_header')
        name_len, extra_len, comment_len = header[12:15]
        need(0 < name_len <= PATH_LIMIT and extra_len <= EXTRA_LIMIT and comment_len == 0
             and position + 46 + name_len + extra_len <= end, 'zip_metadata_limit')
        _extras(_at(stream, position + 46 + name_len, extra_len))
        position += 46 + name_len + extra_len
    need(position == end, 'zip_directory_count')
    return {'count': count, 'offset': cd_offset, 'size': cd_size}


def inspect_zip_directory(zip_path):
    """Inspect bounded EOCD/ZIP64/central records before constructing ZipFile."""
    with open_file(zip_path) as stream:
        return _directory_guard(stream)


class _Names:
    def __init__(self):
        self.paths = {}
        self.explicit = set()

    def add(self, original, directory=False):
        name = safe_relative(original, directory=directory)
        parts = name.split('/')
        for index in range(1, len(parts) + 1):
            path = '/'.join(parts[:index])
            is_dir = index < len(parts) or directory
            key = unicodedata.normalize('NFC', path).casefold()
            need(key not in self.paths or self.paths[key] == (path, is_dir), 'archive_path_collision')
            self.paths[key] = path, is_dir
        need(key not in self.explicit, 'duplicate_archive_member')
        self.explicit.add(key)
        return name


def _local_records(stream, infos, central_offset):
    position = 0
    ordered = sorted(infos, key=lambda item: item.header_offset)
    for index, info in enumerate(ordered):
        need(info.header_offset == position, 'zip_hidden_data')
        values = struct.unpack('<4s5H3I2H', _at(stream, position, 30))
        sig, version, flags, method, _, _, crc, compressed, expanded, name_len, extra_len = values
        need(sig == b'PK\x03\x04' and version <= 45 and flags == info.flag_bits
             and method == info.compress_type and 0 < name_len <= PATH_LIMIT
             and extra_len <= EXTRA_LIMIT, 'zip_local_header')
        raw_name = _at(stream, position + 30, name_len)
        name = raw_name.decode('utf-8' if flags & 0x800 else 'cp437')
        need(name == info.orig_filename, 'zip_local_name')
        extras = _extras(_at(stream, position + 30 + name_len, extra_len))
        if expanded == 0xffffffff or compressed == 0xffffffff:
            data = extras.get(1, b'')
            for field in ('expanded', 'compressed'):
                if (expanded if field == 'expanded' else compressed) == 0xffffffff:
                    need(len(data) >= 8, 'zip64_local_header')
                    value = struct.unpack('<Q', data[:8])[0]
                    data = data[8:]
                    if field == 'expanded':
                        expanded = value
                    else:
                        compressed = value
        position += 30 + name_len + extra_len + info.compress_size
        next_offset = ordered[index + 1].header_offset if index + 1 < len(ordered) else central_offset
        if flags & 8:
            need(crc in {0, info.CRC} and compressed in {0, info.compress_size}
                 and expanded in {0, info.file_size}, 'zip_local_sizes')
            length = next_offset - position
            need(length in {12, 16, 20, 24}, 'zip_descriptor_size')
            descriptor = _at(stream, position, length)
            if length in {16, 24}:
                need(descriptor[:4] == b'PK\x07\x08', 'zip_descriptor_header')
                descriptor = descriptor[4:]
            actual = struct.unpack('<III' if len(descriptor) == 12 else '<IQQ', descriptor)
            need(actual == (info.CRC, info.compress_size, info.file_size), 'zip_descriptor_values')
            position = next_offset
        else:
            need((crc, compressed, expanded) == (info.CRC, info.compress_size, info.file_size), 'zip_local_sizes')
        need(position == next_offset, 'zip_hidden_data')
    need(position == central_offset, 'zip_hidden_data')


def _deflate_integrity(stream, info):
    """ZipExtFile may stop at output size; independently check compressed EOF."""
    if info.compress_type == zipfile.ZIP_STORED:
        need(info.compress_size == info.file_size, 'zip_stored_size')
        return
    header = _at(stream, info.header_offset, 30)
    name_len, extra_len = struct.unpack('<HH', header[26:30])
    stream.seek(info.header_offset + 30 + name_len + extra_len)
    decoder = zlib.decompressobj(-zlib.MAX_WBITS)
    remaining, expanded = info.compress_size, 0
    while remaining:
        data = stream.read(min(CHUNK, remaining))
        need(bool(data), 'truncated_zip')
        remaining -= len(data)
        while data:
            output = decoder.decompress(data, CHUNK)
            data = decoder.unconsumed_tail
            expanded += len(output)
            need(expanded <= info.file_size, 'zip_expansion_limit')
            need(not decoder.unused_data and not (decoder.eof and (data or remaining)), 'zip_hidden_data')
    need(decoder.eof and expanded == info.file_size, 'zip_deflate_eof')


def extract_bounded_zip(zip_path, destination: PrivateRoot, allowed_root_names):
    """Caller authenticates the entire ZIP against API digest before this call."""
    need(isinstance(destination, PrivateRoot) and not destination.files(), 'extraction_root_not_empty')
    allowed = set(allowed_root_names) | {'packaging-report.json', 'SHA256SUMS.txt'}
    need(all(safe_relative(name) == name and '/' not in name for name in allowed), 'invalid_root_allowlist')
    try:
        with open_file(zip_path) as stream:
            directory = _directory_guard(stream)
            with zipfile.ZipFile(stream, 'r') as archive:
                infos = archive.infolist()
                need(len(infos) == directory['count'] and archive.start_dir == directory['offset'], 'zip_directory_count')
                names, records, total = _Names(), [], 0
                for info in infos:
                    is_dir = info.is_dir()
                    name = names.add(info.orig_filename, is_dir)
                    need((name.startswith('evidence/') or (name == 'evidence' and is_dir)
                          or (name in allowed and not is_dir)), 'zip_root_allowlist')
                    mode = info.external_attr >> 16
                    kind = stat.S_IFMT(mode)
                    need(kind in ({0, stat.S_IFDIR} if is_dir else {0, stat.S_IFREG})
                         and not (info.external_attr & 0xffff & ~0x37)
                         and (not info.external_attr & 0x10 or is_dir), 'zip_special_member')
                    need(info.flag_bits & ~0x80e == 0 and info.compress_type in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}
                         and info.extract_version <= 45 and info.volume == 0, 'unsupported_zip_member')
                    need(0 <= info.file_size <= FILE_LIMIT and 0 <= info.compress_size <= ZIP_LIMIT
                         and info.file_size <= max(1, info.compress_size) * RATIO_LIMIT, 'zip_expansion_limit')
                    need(not is_dir or info.file_size == 0, 'zip_directory_payload')
                    total += info.file_size
                    need(total <= TOTAL_LIMIT, 'zip_expansion_limit')
                    records.append((info, name, is_dir))
                _local_records(stream, infos, directory['offset'])
                for info in infos:
                    _deflate_integrity(stream, info)
                expanded_total = 0
                for info, name, is_dir in records:
                    with archive.open(info) as source:
                        if is_dir:
                            need(source.read(1) == b'', 'zip_directory_payload')
                            destination.mkdir(name)
                            continue
                        with destination.open(name, 'xb') as output:
                            size = 0
                            while data := source.read(CHUNK):
                                size += len(data)
                                expanded_total += len(data)
                                need(size <= info.file_size and size <= FILE_LIMIT and expanded_total <= TOTAL_LIMIT,
                                     'zip_expansion_limit')
                                output.write(data)
                            need(size == info.file_size, 'zip_member_size')
        return destination.files()
    except (OSError, zipfile.BadZipFile, NotImplementedError, UnicodeError, zlib.error, struct.error):
        raise ConsumerError('invalid_zip') from None


def verify_checksum_inventory(root: PrivateRoot, *, deadline=None, check_active=None):
    budget = {} if deadline is None and check_active is None else dict(deadline=deadline, check_active=check_active)
    _check_budget(deadline, check_active)
    files = set(root.files())
    _check_budget(deadline, check_active)
    need('SHA256SUMS.txt' in files, 'missing_checksum_inventory')
    try:
        text = root.read('SHA256SUMS.txt', JSON_LIMIT).decode('utf-8')
    except UnicodeError:
        raise ConsumerError('invalid_checksum_inventory') from None
    _check_budget(deadline, check_active)
    need(text.endswith('\n') and '\r' not in text, 'invalid_checksum_inventory')
    entries, names = {}, _Names()
    for line in text[:-1].split('\n'):
        _check_budget(deadline, check_active)
        match = re.fullmatch(r'([0-9a-f]{64})  (.+)', line)
        need(match is not None, 'invalid_checksum_inventory')
        name = names.add(match[2])
        need(name != 'SHA256SUMS.txt', 'invalid_checksum_inventory')
        entries[name] = match[1]
    _check_budget(deadline, check_active)
    need(set(entries) == files - {'SHA256SUMS.txt'}, 'checksum_coverage')
    for name, expected in entries.items():
        _check_budget(deadline, check_active)
        need(hash_file(root.path / name, **budget) == expected, 'checksum_mismatch')
    _check_budget(deadline, check_active)
    return entries


class _GzipReader:
    """Single gzip member, zlib-verified CRC/trailer, bounded each allocation."""
    def __init__(self, raw):
        self.raw = raw
        self.size = os.fstat(raw.fileno()).st_size
        need(0 < self.size <= FILE_LIMIT, 'gzip_size_limit')
        self.decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
        self.pending = b''
        self.total = 0
        self.finished = False

    def read(self, size):
        need(type(size) is int and 0 <= size <= CHUNK, 'archive_read_limit')
        output = bytearray()
        while len(output) < size and not self.finished:
            if not self.pending:
                self.pending = self.raw.read(CHUNK)
                need(bool(self.pending), 'truncated_gzip')
            data = self.decoder.decompress(self.pending, size - len(output))
            self.pending = self.decoder.unconsumed_tail
            output.extend(data)
            self.total += len(data)
            need(self.total <= TAR_TOTAL_LIMIT and self.total <= self.size * RATIO_LIMIT, 'tar_expansion_limit')
            if self.decoder.eof:
                need(not self.decoder.unused_data and not self.pending and not self.raw.read(1), 'gzip_trailing_data')
                self.finished = True
        return bytes(output)


class _GuardedTarInfo(tarfile.TarInfo):
    @classmethod
    def fromtarfile(cls, archive):
        try:
            return super().fromtarfile(archive)
        except tarfile.EOFHeaderError:
            archive.consumer_zero_header = True
            raise
        except (tarfile.InvalidHeaderError, tarfile.EmptyHeaderError, tarfile.TruncatedHeaderError):
            raise ConsumerError('invalid_tar_header') from None

    def _proc_member(self, archive):
        # This runs before stdlib dispatch to PAX/GNU/sparse body readers.
        need(self.type in {tarfile.REGTYPE, tarfile.AREGTYPE}, 'tar_extension_or_special')
        need(safe_relative(self.name) in CLOUD_MEMBERS and not self.linkname, 'tar_member_allowlist')
        limit = TAR_MEMBER_LIMIT if self.name.startswith('bin/') else 1024**2 - 1
        need(0 < self.size <= limit and self.mode == (0o755 if self.name.startswith('bin/') else 0o644), 'tar_member_metadata')
        return super()._proc_member(archive)


def extract_bounded_cloud_tar(tar_path, destination: PrivateRoot):
    need(isinstance(destination, PrivateRoot) and not destination.files(), 'extraction_root_not_empty')
    try:
        with open_file(tar_path) as raw:
            gzip = _GzipReader(raw)
            with tarfile.open(fileobj=gzip, mode='r|', tarinfo=_GuardedTarInfo, bufsize=512) as archive:
                names = _Names()
                found = set()
                for member in archive:
                    name = names.add(member.name)
                    found.add(name)
                    need(len(found) <= len(CLOUD_MEMBERS), 'tar_member_count')
                    source = archive.extractfile(member)
                    need(source is not None, 'tar_member_missing')
                    with source, destination.open(name, 'xb') as output:
                        size = 0
                        while data := source.read(CHUNK):
                            size += len(data)
                            need(size <= member.size, 'tar_member_size')
                            output.write(data)
                        need(size == member.size, 'tar_member_size')
                need(found == CLOUD_MEMBERS and getattr(archive, 'consumer_zero_header', False), 'tar_member_inventory')
                padding = 0
                while data := archive.fileobj.read(CHUNK):
                    padding += len(data)
                    need(not any(data), 'tar_trailing_data')
                need(padding >= 512 and padding % 512 == 0 and gzip.finished, 'tar_incomplete_padding')
        need(set(destination.files()) == CLOUD_MEMBERS, 'tar_member_inventory')
        manifest = json_file(destination.path / 'manifest.json')
        records = manifest.get('binaries')
        need(type(records) is dict and set(records) == set(BINS), 'cloud_binary_inventory')
        for name in BINS:
            record = records[name]
            need(type(record) is dict and type(record.get('size')) is int and record['size'] > 0
                 and type(record.get('sha256')) is str and re.fullmatch('[0-9a-f]{64}', record['sha256']), 'cloud_binary_record')
            with destination.open('bin/' + name) as binary:
                header = binary.read(20)
                need(os.fstat(binary.fileno()).st_size == record['size'], 'cloud_binary_size')
            need(len(header) == 20 and header[:6] == b'\x7fELF\x02\x01'
                 and int.from_bytes(header[18:20], 'little') == 62, 'cloud_binary_elf')
            need(hash_file(destination.path / 'bin' / name) == record['sha256'], 'cloud_binary_digest')
        return manifest
    except (OSError, tarfile.TarError, zlib.error, UnicodeError):
        raise ConsumerError('invalid_cloud_archive') from None
