#!/usr/bin/env python3
"""Bounded data-only proof of the pinned Tauri desktop ELF -> DEB transform.

No extraction, installation, subprocesses, executable loading, or normalization.
Archive formats outside the reviewed pinned producer contract fail closed.
"""
import hashlib
import re
import struct
import zlib

from exact_build_audit import EvidenceError, digest, need

MAX_DEB = MAX_MEMBER = MAX_ELF = 256 * 1024 * 1024
MAX_TAR, MAX_CONTROL, MAX_ENTRIES, MAX_PATH = 512 * 1024 * 1024, 1024 * 1024, 4096, 1024
CHUNK, PAGE, U64 = 65536, 4096, (1 << 64) - 1
UNK, DEB = b"__TAURI_BUNDLE_TYPE_VAR_UNK", b"__TAURI_BUNDLE_TYPE_VAR_DEB"
BINARY = "usr/bin/coding-tools-mcp-desktop"
DATA_FILES = {BINARY, "usr/share/applications/Coding Tools MCP.desktop"} | {
    f"usr/share/icons/hicolor/{size}/apps/coding-tools-mcp-desktop.png"
    for size in ("32x32", "128x128", "256x256@2")}
DATA_DIRS = {name[:i] for name in DATA_FILES for i, char in enumerate(name) if char == "/"}


def number(raw, base=8, limit=U64, empty=False):
    value = raw.rstrip(b"\0 ").lstrip(b" ")
    need((empty and not value) or re.fullmatch(b"[0-7]+" if base == 8 else b"[0-9]+", value), "invalid_archive_number")
    result = int(value or b"0", base)
    need(result <= limit, "archive_number_overflow")
    return result


def ar_members(data):
    need(type(data) is bytes and 8 <= len(data) <= MAX_DEB and data[:8] == b"!<arch>\n", "invalid_ar")
    result, pos = {}, 8
    for name in ("debian-binary", "control.tar.gz", "data.tar.gz"):
        header = data[pos:pos + 60]
        need(len(header) == 60 and header[:16] == name.encode().ljust(16, b" ") and header[58:] == b"`\n", "invalid_ar_header")
        for start, end, base, limit in ((16, 28, 10, U64), (28, 34, 10, 2**32-1), (34, 40, 10, 2**32-1), (40, 48, 8, 0o177777), (48, 58, 10, MAX_MEMBER)):
            field = header[start:end]
            need(re.fullmatch((b"[0-7]+" if base == 8 else b"[0-9]+") + b" *", field), "invalid_ar_field")
            number(field, base, limit)
        size = number(header[48:58], 10, MAX_MEMBER)
        mode = number(header[40:48])
        need(not mode & 0o6000 and mode & 0o170000 in (0, 0o100000), "unsafe_ar_mode")
        pos += 60
        need(pos + size <= len(data), "truncated_ar_member")
        result[name], pos = data[pos:pos + size], pos + size
        if size % 2:
            need(data[pos:pos + 1] == b"\n", "invalid_ar_padding")
            pos += 1
    need(pos == len(data) and result["debian-binary"] == b"2.0\n", "unexpected_ar_content")
    return result


def gunzip(data, budget):
    need(type(budget) is int and 0 <= budget <= MAX_TAR and len(data) <= MAX_MEMBER, "invalid_gzip_budget")
    decoder, output = zlib.decompressobj(16 + zlib.MAX_WBITS), bytearray()
    try:
        for offset in range(0, len(data), CHUNK):
            pending = data[offset:offset + CHUNK]
            need(not decoder.eof, "trailing_gzip_stream")
            while pending:
                block = decoder.decompress(pending, min(CHUNK, budget - len(output) + 1))
                need(len(block) <= budget - len(output), "gzip_expansion_limit")
                output.extend(block)
                pending = decoder.unconsumed_tail
                need(not decoder.unused_data, "trailing_gzip_stream")
        need(decoder.eof and not decoder.unused_data and not decoder.unconsumed_tail, "truncated_gzip")
    except zlib.error as exc:
        raise EvidenceError("invalid_gzip") from exc
    return bytes(output)


def cstring(raw):
    value, separator, tail = raw.partition(b"\0")
    need(not separator or not any(tail), "nonzero_tar_string_padding")
    return value


def tar_members(data, budget=None):
    if budget is None:
        budget = MAX_ENTRIES
    need(type(budget) is int and 0 <= budget <= MAX_ENTRIES and len(data) <= MAX_TAR and len(data) % 512 == 0, "invalid_tar_bounds")
    files, dirs, names, pos = {}, set(), set(), 0
    while pos + 512 <= len(data):
        header = data[pos:pos + 512]
        if header == bytes(512):
            need(len(data) - pos >= 1024 and not any(memoryview(data)[pos:]), "invalid_tar_trailer")
            return files, dirs, len(names)
        need(len(names) < budget and header[257:265] == b"ustar  \0", "unsupported_tar_header")
        need(number(header[148:156]) == sum(header[:148]) + 8 * 32 + sum(header[156:]), "invalid_tar_checksum")
        kind = header[156:157]
        need(kind in (b"0", b"\0", b"5") and not any(header[157:257]), "unsupported_tar_entry")
        for start, end in ((108, 116), (116, 124), (136, 148), (329, 337), (337, 345), (345, 357), (357, 369)):
            number(header[start:end], empty=start >= 329)
        need(number(header[329:337], empty=True) == number(header[337:345], empty=True) == 0, "unexpected_tar_device_number")
        need(number(header[369:381], empty=True) == 0 and not any(header[381:483]) and number(header[483:495], empty=True) == 0 and not any(header[495:]), "unsupported_tar_extension")
        cstring(header[265:297]); cstring(header[297:329])
        mode, size = number(header[100:108], limit=0o177777), number(header[124:136], limit=MAX_MEMBER)
        need(not mode & 0o6000 and (mode & 0o170000) in (0, 0o040000 if kind == b"5" else 0o100000), "unsafe_tar_mode")
        raw = cstring(header[:100])
        if kind == b"5" and raw.endswith(b"/"):
            raw = raw[:-1]
        need(0 < len(raw) <= MAX_PATH and b"\\" not in raw and all(part not in (b"", b".", b"..") for part in raw.split(b"/")) and all(c >= 32 and c != 127 for c in raw), "unsafe_tar_path")
        try:
            name = raw.decode("utf-8", errors="strict")
        except UnicodeError as exc:
            raise EvidenceError("invalid_tar_path_encoding") from exc
        need(mode == (0o755 if kind == b"5" or name == BINARY else 0o644), "unexpected_tar_mode")
        need(name not in names, "duplicate_tar_path")
        names.add(name)
        pos += 512
        end, padded = pos + size, pos + (size + 511) // 512 * 512
        need(padded <= len(data) and not any(memoryview(data)[end:padded]), "invalid_tar_member_padding")
        if kind == b"5":
            need(size == 0, "nonempty_tar_directory")
            dirs.add(name)
        else:
            files[name] = data[pos:end]
        pos = padded
    raise EvidenceError("missing_tar_trailer")


def control_identity(data, version):
    need(0 < len(data) <= MAX_CONTROL and data.endswith(b"\n") and b"\r" not in data and b"\0" not in data, "invalid_control")
    try:
        lines = data.decode("utf-8", errors="strict").split("\n")[:-1]
    except UnicodeError as exc:
        raise EvidenceError("invalid_control_encoding") from exc
    fields, last = {}, None
    for line in lines:
        need(all(ord(c) >= 32 and ord(c) != 127 for c in line), "invalid_control_character")
        if line.startswith(" "):
            need(last == "Description", "invalid_control_continuation")
            fields[last] += "\n" + line
            continue
        key, separator, value = line.partition(": ")
        need(separator and re.fullmatch(r"[A-Za-z][A-Za-z-]*", key) and key.lower() not in {k.lower() for k in fields} and value and all(ord(c) >= 32 for c in value), "invalid_control_field")
        fields[key], last = value, key
    expected = {"Package": "coding-tools-mcp", "Version": version, "Architecture": "amd64", "Maintainer": "Coding Tools MCP Contributors", "Section": "devel", "Priority": "optional"}
    need(all(fields.get(k) == v for k, v in expected.items()), "wrong_control_identity")
    need(set(fields) <= set(expected) | {"Installed-Size", "Homepage", "Depends", "Description"} and "Description" in fields, "unexpected_control_fields")
    need(re.fullmatch(r"[0-9]+", fields.get("Installed-Size", "")) and len(fields["Installed-Size"]) <= 20 and int(fields["Installed-Size"]) <= U64, "invalid_installed_size")
    return {key: fields[key] for key in ("Package", "Version", "Architecture")}


def deb_payload(package, version):
    need(type(version) is str and re.fullmatch(r"[0-9][0-9A-Za-z.+:~\-]{0,127}", version), "invalid_expected_version")
    members = ar_members(package)
    control_tar = gunzip(members["control.tar.gz"], MAX_TAR)
    control, dirs, count = tar_members(control_tar)
    need(set(control) == {"control", "md5sums"} and not dirs, "unexpected_control_files")
    identity = control_identity(control["control"], version)
    data_tar = gunzip(members["data.tar.gz"], MAX_TAR - len(control_tar))
    files, dirs, _ = tar_members(data_tar, MAX_ENTRIES - count)
    need(set(files) == DATA_FILES and dirs <= DATA_DIRS, "unexpected_data_files")
    need(0 < len(control["md5sums"]) <= MAX_CONTROL and control["md5sums"].endswith(b"\n"), "invalid_md5sums")
    sums = {}
    for line in control["md5sums"].split(b"\n")[:-1]:
        match = re.fullmatch(rb"([0-9a-f]{32})  (.+)", line)
        need(match is not None, "invalid_md5sums")
        path = match[2]
        need(path not in sums, "duplicate_md5_path")
        sums[path] = match[1]
    need(set(sums) == {name.encode() for name in files}, "wrong_md5_inventory")
    need(all(sums[name.encode()] == hashlib.md5(body, usedforsecurity=False).hexdigest().encode() for name, body in files.items()), "wrong_md5_digest")
    return files[BINARY], identity


def checked_range(start, size, limit, code):
    need(0 <= start <= limit and 0 <= size <= limit - start, code)
    return start, start + size


def overlap(a, b):
    return a[0] < b[1] and b[0] < a[1]


def mapped_pages(interval):
    """Linux amd64 PT_LOAD mmap/protection includes the boundary 4KiB pages."""
    if interval[0] == interval[1]:
        return (0, 0)
    end = (interval[1] + PAGE - 1) // PAGE * PAGE
    need(end <= U64, "page_mapping_overflow")
    return (interval[0] // PAGE * PAGE, end)


def elf_layout(data):
    need(type(data) is bytes and 64 <= len(data) <= MAX_ELF, "invalid_elf_size")
    ident = data[:16]
    need(ident[:7] == b"\x7fELF\x02\x01\x01" and ident[7] in (0, 3) and not any(ident[8:]), "invalid_elf_ident")
    kind, machine, version, entry, phoff, shoff, flags, ehsize, phsize, phnum, shsize, shnum, shstr = struct.unpack_from("<HHIQQQIHHHHHH", data, 16)
    need(kind in (2, 3) and machine == 62 and version == 1 and flags == 0 and ehsize == 64, "invalid_elf_header")
    need(phsize == 56 and 0 < phnum <= MAX_ENTRIES and phoff >= 64, "invalid_program_table")
    headers = [(0, 64), checked_range(phoff, phsize * phnum, len(data), "invalid_program_table")]
    need(shnum <= MAX_ENTRIES and ((shoff == 0 and shnum == 0 and shstr == 0 and shsize in (0, 64)) or (shoff >= 64 and shnum > 0 and shsize == 64 and shstr < shnum)), "invalid_section_table")
    if shnum:
        section_table = checked_range(shoff, shsize * shnum, len(data), "invalid_section_table")
        need(not any(overlap(section_table, h) for h in headers), "overlapping_elf_headers")
        headers.append(section_table)
        need(data[shoff:shoff + shsize] == bytes(64), "unsupported_extended_section_zero")
        for i in range(shnum):
            _, typ, _, addr, off, size, _, _, align, entsize = struct.unpack_from("<IIQQQQIIQQ", data, shoff + i * shsize)
            checked_range(addr, size, U64, "section_address_overflow")
            checked_range(off, 0 if typ == 8 else size, len(data), "invalid_section_range")
            need((align <= 1 or align & (align - 1) == 0) and (entsize == 0 or size % entsize == 0), "invalid_section_alignment")
    loads = []
    for i in range(phnum):
        typ, perms, off, addr, physical, size, memsize, align = struct.unpack_from("<IIQQQQQQ", data, phoff + i * phsize)
        file_range = checked_range(off, size, len(data), "invalid_segment_range")
        address = checked_range(addr, memsize, U64, "segment_address_overflow")
        checked_range(physical, memsize, U64, "segment_address_overflow")
        need(size <= memsize and perms & ~7 == 0 and (align <= 1 or (align & (align - 1) == 0 and off % align == addr % align)), "invalid_segment_layout")
        if typ == 1:
            loads.append((file_range, address, perms))
    need(any(perms & 1 and address[0] <= entry < address[1] for _, address, perms in loads), "invalid_elf_entry")
    return loads, headers


def verify_marker_transform(compiled: bytes, payload: bytes) -> dict:
    loads, headers = elf_layout(compiled)
    need(type(payload) is bytes and len(compiled) == len(payload) and compiled.count(UNK) == 1 and payload.count(UNK) == 0, "invalid_marker_count_or_length")
    offset = compiled.index(UNK)
    marker = (offset, offset + len(UNK))
    need(not any(overlap(marker, header) for header in headers), "marker_in_elf_header")
    mapped = [load for load in loads if overlap(marker, load[0])]
    need(len(mapped) == 1, "ambiguous_marker_mapping")
    file_range, address, perms = mapped[0]
    need(file_range[0] <= marker[0] and marker[1] <= file_range[1] and perms & 4 and not perms & 2, "marker_not_readonly_load")
    virtual = (address[0] + offset - file_range[0], address[0] + marker[1] - file_range[0])
    need(not any(perms & 2 and overlap(virtual, address) for _, address, perms in loads), "writable_marker_alias")
    need(not any(perms & 2 and (overlap(marker, mapped_pages(file_range)) or overlap(virtual, mapped_pages(address))) for file_range, address, perms in loads), "writable_marker_page_alias")
    need(payload == compiled[:offset] + DEB + compiled[offset + len(UNK):], "unexpected_payload_change")
    elf_layout(payload)
    return {"prebundle_sha256": digest(compiled), "prebundle_size": len(compiled), "payload_sha256": digest(payload), "payload_size": len(payload), "marker_offset": offset}


def verify_deb(compiled: bytes, package: bytes, version: str) -> dict:
    payload, identity = deb_payload(package, version)
    return {**verify_marker_transform(compiled, payload), "package_sha256": digest(package), "package_size": len(package), "control": identity, "payload_path": BINARY}
