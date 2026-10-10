#!/usr/bin/env python3
"""Synthetic adversarial parser fixtures; these do not replace actual DEB replay."""
import gzip
import hashlib
import io
import random
import struct
import tarfile
import unittest
from unittest.mock import patch

import desktop_glib_deb as deb
from exact_build_audit import EvidenceError

VERSION = "0.6.0-rc.4"
OFFSET, IMAGE_SIZE = 4400, 12288


def replace(data, offset, value):
    return data[:offset] + value + data[offset + len(value):]


def elf(marker=deb.UNK, offset=OFFSET):
    blob = bytearray(IMAGE_SIZE)
    blob[:16] = b"\x7fELF\x02\x01\x01" + bytes(9)
    struct.pack_into("<HHIQQQIHHHHHH", blob, 16, 3, 62, 1, 0x400200, 64, 0, 0, 64, 56, 3, 0, 0, 0)
    for i, fields in enumerate(((1, 5, 0, 0x400000, 0x400000, 4096, 4096, 4096),
                                (1, 4, 4096, 0x401000, 0x401000, 4096, 4096, 4096),
                                (1, 6, 8192, 0x402000, 0x402000, 4096, 6144, 4096))):
        struct.pack_into("<IIQQQQQQ", blob, 64 + 56 * i, *fields)
    blob[offset:offset + len(marker)] = marker
    blob[6000:6000 + len(deb.DEB)] = deb.DEB
    return bytes(blob)


def ph(blob, index, **changes):
    fields = dict(zip(("type", "flags", "offset", "vaddr", "paddr", "filesz", "memsz", "align"), struct.unpack_from("<IIQQQQQQ", blob, 64 + 56 * index)))
    fields.update(changes)
    return replace(blob, 64 + 56 * index, struct.pack("<IIQQQQQQ", *fields.values()))


def transformed(blob):
    return blob.replace(deb.UNK, deb.DEB, 1)


def tar(entries, extra_dirs=()):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w", format=tarfile.GNU_FORMAT) as archive:
        for name in extra_dirs:
            info = tarfile.TarInfo(name)
            info.type, info.mode = tarfile.DIRTYPE, 0o755
            archive.addfile(info)
        for name, body in entries:
            info = tarfile.TarInfo(name)
            info.size, info.mode, info.mtime = len(body), 0o755 if name == deb.BINARY else 0o644, 1727000000
            archive.addfile(info, io.BytesIO(body))
    return stream.getvalue()


def header_change(blob, offset, value):
    blob = replace(blob, offset, value)
    checksum = sum(blob[:148]) + 256 + sum(blob[156:512])
    return replace(blob, 148, f"{checksum:06o}\0 ".encode())


def tar_mode(blob, name, mode):
    pos = 0
    while blob[pos:pos + 512] != bytes(512):
        if blob[pos:pos + 100].split(b"\0", 1)[0].rstrip(b"/") == name.encode():
            return blob[:pos] + header_change(blob[pos:], 100, f"{mode:07o}\0".encode())
        pos += 512 + (int(blob[pos + 124:pos + 136].rstrip(b"\0 "), 8) + 511) // 512 * 512
    raise AssertionError("fixture member missing: " + name)


def ar(entries):
    result = b"!<arch>\n"
    for name, body in entries:
        result += name.encode().ljust(16, b" ") + b"1727000000  " + b"0     0     " + b"100644  " + str(len(body)).encode().ljust(10, b" ") + b"`\n"
        result += body + (b"\n" if len(body) % 2 else b"")
    return result


def control():
    return (f"Package: coding-tools-mcp\nVersion: {VERSION}\nArchitecture: amd64\nInstalled-Size: 25\n"
            "Maintainer: Coding Tools MCP Contributors\nSection: devel\nPriority: optional\n"
            "Depends: libgtk-3-0\nDescription: Desktop workspace\n Long description\n .\n").encode()


def fixture(payload=None, fields=None, entries=None, extra_dirs=()):
    files = {name: b"synthetic-icon-or-desktop" for name in sorted(deb.DATA_FILES)}
    files[deb.BINARY] = transformed(elf()) if payload is None else payload
    if entries is not None:
        files = dict(entries)
    sums = b"".join(hashlib.md5(body, usedforsecurity=False).hexdigest().encode() + b"  " + name.encode() + b"\n" for name, body in files.items())
    return tar([("control", control() if fields is None else fields), ("md5sums", sums)]), tar(list(files.items()), extra_dirs)


def package(control_tar=None, data_tar=None, **kwargs):
    c, d = fixture(**kwargs)
    return ar([("debian-binary", b"2.0\n"), ("control.tar.gz", gzip.compress(c if control_tar is None else control_tar, mtime=0)), ("data.tar.gz", gzip.compress(d if data_tar is None else data_tar, mtime=0))])


class DebTests(unittest.TestCase):
    def assertReject(self, function, *args):
        with self.assertRaises(EvidenceError):
            function(*args)

    def test_complete_exact_contract(self):
        compiled, packed = elf(), package(extra_dirs=tuple(sorted(deb.DATA_DIRS)))
        result = deb.verify_deb(compiled, packed, VERSION)
        self.assertEqual(result, {"prebundle_sha256": hashlib.sha256(compiled).hexdigest(), "prebundle_size": IMAGE_SIZE,
                                 "payload_sha256": hashlib.sha256(transformed(compiled)).hexdigest(), "payload_size": IMAGE_SIZE,
                                 "marker_offset": OFFSET, "package_sha256": hashlib.sha256(packed).hexdigest(), "package_size": len(packed),
                                 "control": {"Package": "coding-tools-mcp", "Version": VERSION, "Architecture": "amd64"}, "payload_path": deb.BINARY})

    def test_exact_reviewed_modes_positive(self):
        c, d = fixture(extra_dirs=tuple(sorted(deb.DATA_DIRS)))
        for blob in (c, d):
            with tarfile.open(fileobj=io.BytesIO(blob), mode="r:") as archive:
                for item in archive:
                    self.assertEqual(item.mode, 0o755 if item.isdir() or item.name == deb.BINARY else 0o644)
        deb.verify_deb(elf(), package(c, d), VERSION)

    def test_wrong_reviewed_file_and_directory_modes_rejected(self):
        c, d = fixture(extra_dirs=tuple(sorted(deb.DATA_DIRS)))
        cases = [("data", deb.BINARY, mode) for mode in (0o644, 0, 0o111, 0o700, 0o1755, 0o4755)]
        cases += [("data", name, mode) for name in deb.DATA_FILES - {deb.BINARY} for mode in (0o755, 0o664, 0o1644, 0o2644)]
        cases += [("data", name, mode) for name in deb.DATA_DIRS for mode in (0o644, 0o700, 0o777, 0o2755)]
        cases += [("control", name, mode) for name in ("control", "md5sums") for mode in (0o755, 0o664, 0o1644, 0o4644)]
        for section, name, mode in cases:
            bad_c, bad_d = (tar_mode(c, name, mode), d) if section == "control" else (c, tar_mode(d, name, mode))
            with self.subTest(section=section, name=name, mode=oct(mode)):
                self.assertReject(deb.verify_deb, elf(), package(bad_c, bad_d), VERSION)

    def test_preexisting_deb_literals_unchanged(self):
        compiled = replace(elf(), 6100, deb.DEB)
        self.assertEqual(deb.verify_marker_transform(compiled, transformed(compiled))["marker_offset"], OFFSET)
        self.assertEqual(transformed(compiled).count(deb.DEB), 3)

    def test_tar_entry_order_is_not_significant(self):
        c, d = fixture()
        files, _, _ = deb.tar_members(d)
        self.assertEqual(deb.verify_deb(elf(), package(c, tar(list(reversed(list(files.items()))))), VERSION)["payload_size"], IMAGE_SIZE)

    def test_exact_boundary_limits_and_gzip_chunking(self):
        packed = package()
        with patch.object(deb, "MAX_DEB", len(packed)):
            deb.verify_deb(elf(), packed, VERSION)
        for size in (0, 1, 511, 512, 65535, 65536, 65537, 200000):
            raw = b"x" * size
            for chunk in (1, 7, 65536):
                with self.subTest(size=size, chunk=chunk), patch.object(deb, "CHUNK", chunk):
                    self.assertEqual(deb.gunzip(gzip.compress(raw), size), raw)

    def test_ar_missing_extra_duplicate_reordered_members(self):
        entries = list(deb.ar_members(package()).items())
        for bad in (entries[:-1], entries + [entries[-1]], [entries[1], entries[0], entries[2]], [entries[0], entries[0], entries[2]], [entries[0], ("other.tar.gz", entries[1][1]), entries[2]]):
            with self.subTest(names=[x[0] for x in bad]):
                self.assertReject(deb.ar_members, ar(bad))

    def test_ar_magic_identity_truncation_and_trailing_bytes(self):
        packed = package()
        for bad in (b"", packed[:7], packed[:-1], b"X" + packed[1:], packed + b"\0", packed + b"other", replace(packed, 68, b"1.0\n")):
            self.assertReject(deb.ar_members, bad)

    def test_ar_fields_reject_nondecimal_extended_and_malformed(self):
        packed = package()
        changes = ((8, b"debian-binary/   "), (8, b"#1/12           "), (8, b"//              "), (24, b"-1          "),
                   (36, b"1\0    "), (42, b" 1    "), (48, b"100x44  "), (48, b"104644  "), (48, b"020644  "), (56, b"9999999999"),
                   (56, b"1.5       "), (56, b"-1        "), (56, b"\0         "), (66, b"x\n"))
        for offset, value in changes:
            with self.subTest(offset=offset, value=value):
                self.assertReject(deb.ar_members, replace(packed, offset, value))

    def test_ar_padding_must_be_newline(self):
        packed = ar([("debian-binary", b"2.0\n"), ("control.tar.gz", b"a"), ("data.tar.gz", b"b")])
        self.assertReject(deb.ar_members, replace(packed, 133, b"\0"))

    def test_gzip_truncation_crc_wrong_format_and_extra_streams(self):
        compressed = gzip.compress(b"x" * 4096, mtime=0)
        for bad in (b"", b"not gzip", compressed[:-1], compressed[:10], compressed + b"\0", compressed + gzip.compress(b""), replace(compressed, len(compressed) - 8, b"BAD!")):
            self.assertReject(deb.gunzip, bad, 4096)
        self.assertReject(deb.gunzip, compressed, 4095)

    def test_gzip_trailing_data_at_later_chunk(self):
        compressed = gzip.compress(b"x")
        with patch.object(deb, "CHUNK", len(compressed)):
            self.assertReject(deb.gunzip, compressed + b"tail", 100)

    def test_input_and_expansion_caps(self):
        packed, (c, d) = package(), fixture()
        for name, value in (("MAX_DEB", len(packed) - 1), ("MAX_MEMBER", 100), ("MAX_TAR", len(c) + len(d) - 1), ("MAX_CONTROL", 32), ("MAX_ELF", IMAGE_SIZE - 1), ("MAX_PATH", 10)):
            with self.subTest(name=name), patch.object(deb, name, value):
                self.assertReject(deb.verify_deb, elf(), packed, VERSION)
        for bad in (True, 2.0, -1, deb.MAX_TAR + 1):
            self.assertReject(deb.gunzip, gzip.compress(b""), bad)

    def test_tar_path_aliases_escape_and_encoding(self):
        good = tar([("ok", b"x")])
        for name in (b"/abs", b"../bad", b"a/../b", b"./ok", b"a//b", b"a/./b", b"a\\b", b"a/", b"a\nb", b"\xff", b"", b"C:\\bad"):
            with self.subTest(name=name):
                self.assertReject(deb.tar_members, header_change(good, 0, name.ljust(100, b"\0")))

    def test_tar_duplicate_file_directory_and_canonical_name(self):
        for entries, dirs in (([("ok", b"a"), ("ok", b"b")], ()), ([("ok", b"a")], ("ok",)), ([], ("ok", "ok/"))):
            self.assertReject(deb.tar_members, tar(entries, dirs))

    def test_tar_links_special_pax_longname_sparse_rejected(self):
        good = tar([("ok", b"x")])
        for kind in (b"1", b"2", b"3", b"4", b"6", b"7", b"x", b"g", b"L", b"K", b"S", b"X", b"z"):
            with self.subTest(kind=kind):
                self.assertReject(deb.tar_members, header_change(good, 156, kind))
        self.assertReject(deb.tar_members, header_change(good, 157, b"target"))
        self.assertReject(deb.tar_members, header_change(good, 482, b"1"))
        self.assertReject(deb.tar_members, header_change(good, 386, b"1"))

    def test_tar_magic_checksum_numbers_and_privilege_bits(self):
        good = tar([("ok", b"x")])
        for offset, value in ((257, b"ustar\0"), (100, b"0004644\0"), (100, b"0002644\0"), (100, b"0020644\0"),
                              (108, b"-000001\0"), (124, b"77777777777\0"), (136, b"\x80" + bytes(11)), (124, b"0000000000x\0"),
                              (124, b"\0" + b"0000000001\0"), (369, b"00000000001\0"), (483, b"00000000001\0"), (500, b"x")):
            with self.subTest(offset=offset, value=value):
                self.assertReject(deb.tar_members, header_change(good, offset, value))
        self.assertReject(deb.tar_members, replace(good, 1, b"x"))
        self.assertReject(deb.tar_members, header_change(good, 265, b"a\0b"))

    def test_tar_trailer_and_data_padding_all_checked(self):
        good = tar([("ok", b"x")])
        for bad in (good[:512], good[:1024], good[:1536], good[:-1], good + b"x", good + b"x" + bytes(511),
                    replace(good, 1024 + 700, b"x"), replace(good, 513, b"x")):
            self.assertReject(deb.tar_members, bad)
        self.assertReject(deb.tar_members, header_change(good, 156, b"5"))
        self.assertEqual(deb.tar_members(good[:2048])[0], {"ok": b"x"})

    def test_tar_member_and_entry_limits(self):
        good = tar([("one", b"1"), ("two", b"2")])
        self.assertReject(deb.tar_members, good, 1)
        self.assertEqual(deb.tar_members(good, 2)[2], 2)
        for value in (-1, True, 1.0, deb.MAX_ENTRIES + 1):
            self.assertReject(deb.tar_members, good, value)
        with patch.object(deb, "MAX_MEMBER", 0):
            self.assertReject(deb.tar_members, good)

    def test_cumulative_control_data_entry_budget(self):
        packed = package(extra_dirs=tuple(sorted(deb.DATA_DIRS)))
        count = 2 + len(deb.DATA_FILES) + len(deb.DATA_DIRS)
        with patch.object(deb, "MAX_ENTRIES", count):
            deb.verify_deb(elf(), packed, VERSION)
        with patch.object(deb, "MAX_ENTRIES", count - 1):
            self.assertReject(deb.verify_deb, elf(), packed, VERSION)

    def test_cumulative_control_data_expansion_exact_boundary(self):
        c, d = fixture()
        packed = package(c, d)
        with patch.object(deb, "MAX_TAR", len(c) + len(d)):
            deb.verify_deb(elf(), packed, VERSION)
        with patch.object(deb, "MAX_TAR", len(c) + len(d) - 1):
            self.assertReject(deb.verify_deb, elf(), packed, VERSION)

    def test_tar_required_numeric_and_unused_device_fields(self):
        good = tar([("ok", b"x")])
        for offset, value in ((108, bytes(8)), (116, bytes(8)), (136, bytes(12)), (329, b"0000001\0"), (337, b"0000001\0")):
            self.assertReject(deb.tar_members, header_change(good, offset, value))

    def test_expansion_bomb_rejected_before_large_output(self):
        bomb = gzip.compress(bytes(2 * 1024 * 1024))
        with patch.object(deb, "CHUNK", 19):
            self.assertReject(deb.gunzip, bomb, 1000)

    def test_binary_api_immutable_bytes_required(self):
        for value in (bytearray(package()), memoryview(package()), "not bytes", None):
            self.assertReject(deb.verify_deb, elf(), value, VERSION)

    def test_seeded_malformed_package_never_raises_unclassified_exception(self):
        rng, packed = random.Random(85), package()
        for _ in range(150):
            at = rng.randrange(len(packed))
            mutated = replace(packed, at, bytes([packed[at] ^ (1 << rng.randrange(8))]))
            try:
                deb.verify_deb(elf(), mutated, VERSION)
            except EvidenceError:
                pass

    def test_control_identity_version_arch_and_exact_fields(self):
        good = control()
        variants = [good.replace(b"coding-tools-mcp\n", b"coding-tools-mcp-desktop\n"), good.replace(b"amd64", b"arm64"),
                    good.replace(VERSION.encode(), b"0.7.0"), good.replace(b"devel", b"games"), good.replace(b"optional", b"required"),
                    good.replace(b"Coding Tools MCP Contributors", b"Other"), good + b"Architecture: amd64\n", good + b"architecture: amd64\n",
                    good + b"Pre-Depends: other\n", good + b"\nPackage: other\n", good[:-1], b" x\n" + good,
                    good.replace(b"Version: ", b"Version:"), good.replace(b"Installed-Size: 25", b"Installed-Size: -1"),
                    good.replace(b"25", b"9" * 21), good.replace(b"25", b"1.5"), good.replace(b"25", b"18446744073709551616"), good + b"\xff\n", good + b"\0\n", good.replace(b"\n", b"\r\n")]
        for value in variants:
            with self.subTest(value=value):
                self.assertReject(deb.verify_deb, elf(), package(fields=value), VERSION)
        for version in (VERSION + "\n", "", True, 1, "../rc"):
            self.assertReject(deb.verify_deb, elf(), package(), version)

    def test_control_missing_extra_scripts_and_directories(self):
        for c in (tar([("control", control())]), tar([("control", control()), ("md5sums", b"x"), ("postinst", b"echo bad")]),
                  tar([("control", control()), ("md5sums", b"x")], ("extra",))):
            self.assertReject(deb.verify_deb, elf(), package(control_tar=c), VERSION)

    def test_control_description_continuation_control_characters(self):
        for value in (b"\x01", b"\t", b"\x7f"):
            self.assertReject(deb.verify_deb, elf(), package(fields=control() + b" " + value + b"\n"), VERSION)

    def test_data_missing_extra_wrong_binary_empty_and_directory(self):
        _, d = fixture()
        files = deb.tar_members(d)[0]
        for name in deb.DATA_FILES:
            self.assertReject(deb.verify_deb, elf(), package(entries=[item for item in files.items() if item[0] != name]), VERSION)
        for name in ("usr/bin/extra", "usr/bin/coding-tools-mcp", "usr/share/doc/extra"):
            self.assertReject(deb.verify_deb, elf(), package(entries=list(files.items()) + [(name, b"other")]), VERSION)
        self.assertReject(deb.verify_deb, elf(), package(payload=b""), VERSION)
        self.assertReject(deb.verify_deb, elf(), package(payload=transformed(elf())[:-1]), VERSION)
        self.assertReject(deb.verify_deb, elf(), package(extra_dirs=("unexpected",)), VERSION)

    def test_md5_inventory_digest_duplicates_and_malformed_lines(self):
        c, _ = fixture()
        files = deb.tar_members(c)[0]
        sums = files["md5sums"]
        for bad in (sums[:-1], sums + sums.splitlines(keepends=True)[0], sums.replace(b"  ", b" ", 1), b"0" * 32 + sums[32:],
                    sums + b"0" * 32 + b"  other\n", b"", sums.splitlines(keepends=True)[0]):
            self.assertReject(deb.verify_deb, elf(), package(control_tar=tar([("control", control()), ("md5sums", bad)])), VERSION)

    def test_elf_identity_headers_and_architecture(self):
        compiled = elf()
        changes = ((0, b"BAD!"), (4, b"\x01"), (5, b"\x02"), (6, b"\x02"), (7, b"\xff"), (8, b"\x01"),
                   (16, struct.pack("<H", 1)), (18, struct.pack("<H", 183)), (20, struct.pack("<I", 0)),
                   (24, struct.pack("<Q", 0)), (32, struct.pack("<Q", 1)), (32, struct.pack("<Q", deb.U64)),
                   (48, struct.pack("<I", 1)), (52, struct.pack("<H", 63)), (54, struct.pack("<H", 55)),
                   (56, struct.pack("<H", 0)), (56, struct.pack("<H", 65535)))
        for offset, value in changes:
            bad = replace(compiled, offset, value)
            with self.subTest(offset=offset, value=value):
                self.assertReject(deb.verify_marker_transform, bad, transformed(bad))
        for bad in (b"", compiled[:63], compiled[:200], bytearray(compiled)):
            self.assertReject(deb.elf_layout, bad)

    def test_elf_segment_overflows_ranges_sizes_alignment(self):
        for changes in ({"filesz": 4097, "memsz": 4096}, {"offset": deb.U64}, {"filesz": 13000, "memsz": 13000},
                        {"vaddr": deb.U64, "align": 1}, {"paddr": deb.U64}, {"align": 3}, {"vaddr": 0x401001},
                        {"flags": 12}, {"memsz": deb.U64}, {"type": 0}):
            bad = ph(elf(), 1, **changes)
            with self.subTest(changes=changes):
                self.assertReject(deb.verify_marker_transform, bad, transformed(bad))

    def test_elf_section_header_ranges_alignment_and_overflows(self):
        good = replace(elf(), 40, struct.pack("<Q", 11520))
        good = replace(good, 58, struct.pack("<HHH", 64, 2, 0))
        good = replace(good, 11584, struct.pack("<IIQQQQIIQQ", 0, 1, 0, 0, 7000, 8, 0, 0, 1, 0))
        deb.verify_marker_transform(good, transformed(good))
        changes = ((40, struct.pack("<Q", deb.U64)), (40, struct.pack("<Q", 64)), (58, struct.pack("<H", 63)),
                   (60, struct.pack("<H", 65535)), (62, struct.pack("<H", 2)), (11600, struct.pack("<Q", deb.U64)),
                   (11608, struct.pack("<Q", IMAGE_SIZE)), (11632, struct.pack("<Q", 3)), (11640, struct.pack("<Q", 3)))
        for offset, value in changes:
            bad = replace(good, offset, value)
            self.assertReject(deb.verify_marker_transform, bad, transformed(bad))
        self.assertReject(deb.elf_layout, replace(elf(), 60, struct.pack("<H", 1)))

    def test_extended_section_numbering_is_not_silently_accepted(self):
        bad = replace(elf(), 40, struct.pack("<Q", 11520))
        bad = replace(bad, 58, struct.pack("<HHH", 64, 1, 0))
        bad = replace(bad, 11520 + 32, struct.pack("<Q", 2))
        self.assertReject(deb.elf_layout, bad)

    def test_exec_and_linux_abi_positive(self):
        good = replace(replace(elf(), 7, b"\x03"), 16, struct.pack("<H", 2))
        deb.verify_marker_transform(good, transformed(good))
        good = ph(good, 1, align=0)
        deb.verify_marker_transform(good, transformed(good))

    def test_seeded_elf_header_mutations_never_raise_unclassified_exception(self):
        rng, compiled = random.Random(86), elf()
        for _ in range(200):
            at = rng.randrange(232)
            mutated = replace(compiled, at, bytes([compiled[at] ^ (1 << rng.randrange(8))]))
            try:
                deb.verify_marker_transform(mutated, transformed(mutated))
            except EvidenceError:
                pass

    def test_marker_absent_duplicate_wrong_source_or_target(self):
        for bad in (elf(b"x" * len(deb.UNK)), elf(deb.DEB), replace(elf(), 6100, deb.UNK)):
            self.assertReject(deb.verify_marker_transform, bad, transformed(bad))
        for bad in (elf(), elf(b"__TAURI_BUNDLE_TYPE_VAR_APP"), transformed(elf()) + b"junk", transformed(elf())[:-1],
                    replace(transformed(elf()), 6100, deb.UNK), bytearray(transformed(elf()))):
            self.assertReject(deb.verify_marker_transform, elf(), bad)

    def test_marker_byte_changes_shift_and_two_ranges(self):
        payload = transformed(elf())
        for bad in (replace(payload, 8000, b"x"), replace(payload, 6000, b"x"), replace(replace(payload, OFFSET, bytes(len(deb.DEB))), OFFSET + 1, deb.DEB),
                    replace(replace(payload, 2000, b"x"), 2100, b"y")):
            self.assertReject(deb.verify_marker_transform, elf(), bad)

    def test_marker_writable_unreadable_and_not_file_backed(self):
        for changes in ({"flags": 6}, {"flags": 0}, {"filesz": 304}, {"filesz": 320}, {"offset": 8192}, {"memsz": 100, "filesz": 100}):
            bad = ph(elf(), 1, **changes)
            self.assertReject(deb.verify_marker_transform, bad, transformed(bad))
        for offset in (8180, 9000):
            bad = elf(offset=offset)
            self.assertReject(deb.verify_marker_transform, bad, transformed(bad))

    def test_marker_duplicate_readonly_partial_and_writable_file_mappings(self):
        for flags, offset, size in ((4, 4096, 4096), (6, 4096, 4096), (4, OFFSET + 5, 10), (6, OFFSET + 5, 10)):
            bad = ph(elf(), 2, flags=flags, offset=offset, filesz=size, memsz=size, align=1)
            self.assertReject(deb.verify_marker_transform, bad, transformed(bad))

    def test_marker_writable_virtual_alias_including_bss(self):
        for size in (1024, 0):
            bad = ph(elf(), 2, vaddr=0x401000, filesz=size)
            self.assertReject(deb.verify_marker_transform, bad, transformed(bad))

    def test_writable_file_page_alias_before_or_after_declared_interval(self):
        for offset in (4608, 4100):
            bad = ph(elf(), 2, offset=offset, vaddr=0x403000 + offset % 4096, filesz=32, memsz=32)
            with self.assertRaisesRegex(EvidenceError, "^writable_marker_page_alias$"):
                deb.verify_marker_transform(bad, transformed(bad))

    def test_writable_virtual_page_alias_without_file_overlap(self):
        for filesz in (32, 0):
            bad = ph(elf(), 2, offset=8704, vaddr=0x401200, filesz=filesz, memsz=32)
            with self.assertRaisesRegex(EvidenceError, "^writable_marker_page_alias$"):
                deb.verify_marker_transform(bad, transformed(bad))

    def test_empty_and_overflowing_page_ranges(self):
        self.assertEqual(deb.mapped_pages((0, 0)), (0, 0))
        self.assertEqual(deb.mapped_pages((4096, 8192)), (4096, 8192))
        self.assertEqual(deb.mapped_pages((4097, 8193)), (4096, 12288))
        self.assertReject(deb.mapped_pages, (deb.U64 - 1, deb.U64))

    def test_marker_appended_or_header_bytes_cannot_prove_mapping(self):
        bad = elf(b"x" * len(deb.UNK)) + deb.UNK
        self.assertReject(deb.verify_marker_transform, bad, transformed(bad))
        bad = elf(offset=64)
        self.assertReject(deb.verify_marker_transform, bad, transformed(bad))


if __name__ == "__main__":
    unittest.main()
